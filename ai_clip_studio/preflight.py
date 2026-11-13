"""Preflight validation (Master Prompt §3, §9).

Runs BEFORE any render: script hash, assets, voices, timeline and
output configuration. Returns PASS/FAIL with a reason for every
failed check — a failed preflight blocks the render, it never warns
and continues.

Upstream status (see AUDIT.md): partial. There is a frontend
`PreflightPanel.tsx` (350 lines) with proof screenshots, a
`test_episode01_preflight.py`, and capability validation inside
`v5_story_director.py` (`validate_capability`, animation pacing,
depth sorting, prop parenting, subtitle wrap, camera composition).
There is no single standalone preflight module that checks the hash
chain + assets + voices + timeline + output config together and
returns one verdict. This module is that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .action_compiler import (
    UnauthorizedStoryChange, compile_actions, detect_conflicts)
from .production_errors import ACTOR_RESOLUTION_FAILED
from .production_request import ProductionRequest
from .prop_system import ForbiddenPropTransition, SemanticPropTracker
from .scene_graph import (
    GraphValidationError, build_scene_graph, validate_or_raise)
from .timeline import Timeline
from .trait_derivation import PROP_KINDS


@dataclass
class PreflightCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PreflightResult:
    passed: bool
    checks: list[PreflightCheck] = field(default_factory=list)

    def failures(self) -> list[PreflightCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


def run_preflight(
    request: ProductionRequest,
    *,
    timeline: Timeline | None = None,
    asset_paths: Iterable[Path] = (),
    available_voices: Iterable[str] = (),
    required_voices: Iterable[str] = (),
    output_width: int = 1920,
    output_height: int = 1080,
    fps: int = 24,
    loudness_lufs: float = -14.0,
    script_hash_at_preflight: str | None = None,
    allow_estimated_timeline: bool = False,
) -> PreflightResult:
    """Validate everything a render depends on. No side effects."""
    checks: list[PreflightCheck] = []

    # 1. Script hash chain.
    if script_hash_at_preflight is not None:
        checks.append(PreflightCheck(
            "script_hash",
            script_hash_at_preflight == request.script_hash,
            "hash matches the ProductionRequest" if script_hash_at_preflight == request.script_hash
            else "script changed since submission — re-run analysis",
        ))
    else:
        checks.append(PreflightCheck(
            "script_hash", bool(request.script_text.strip()),
            "script present" if request.script_text.strip() else "empty script",
        ))

    # 2. Language / output configuration.
    checks.append(PreflightCheck(
        "language", request.language == "vi-VN",
        f"language={request.language} (must be vi-VN for publishing)",
    ))
    checks.append(PreflightCheck(
        "output_config",
        (output_width, output_height) == (1920, 1080) and fps == 24,
        f"{output_width}x{output_height}@{fps}fps (must be 1920x1080@24)",
    ))
    checks.append(PreflightCheck(
        "loudness", -15.5 <= loudness_lufs <= -13.0,
        f"loudness {loudness_lufs} LUFS (target -14)",
    ))

    # 3. Assets exist.
    missing = [str(p) for p in asset_paths if not Path(p).exists()]
    checks.append(PreflightCheck(
        "assets", not missing,
        "all assets present" if not missing else f"missing assets: {missing}",
    ))

    # 4. Voices available in the registry.
    available = set(available_voices)
    missing_voices = [v for v in required_voices if v not in available]
    checks.append(PreflightCheck(
        "voices", not missing_voices,
        "all required voices available" if not missing_voices
        else f"voices not in registry: {missing_voices}",
    ))

    # 5. Timeline: must exist, must cover the voice, must be measured.
    if timeline is None:
        checks.append(PreflightCheck("timeline", False, "no timeline built"))
    else:
        checks.append(PreflightCheck(
            "timeline_duration",
            timeline.total_duration_sec > 0,
            f"total {timeline.total_duration_sec:.2f}s",
        ))
        checks.append(PreflightCheck(
            "timeline_measured",
            timeline.all_measured or allow_estimated_timeline,
            "durations measured from real TTS audio"
            if timeline.all_measured
            else "durations are ESTIMATED — allowed only for planning, "
                 "measure real TTS before rendering",
        ))

    passed = all(c.passed for c in checks)
    return PreflightResult(passed=passed, checks=checks)


def semantic_preflight_checks(package: dict) -> list[PreflightCheck]:
    """Semantic conflict checks (directive §4) for a real package.

    Compiles the package's actions (estimated spans -- binding is
    by shot/scene id, not time) and runs detect_conflicts over
    every level available before rendering: R1 cue-vs-event, R2
    rain-vs-no-rain, R3 parser-vs-event. R4 (staging) and R5
    (renderer primitives) need render-time records, so they are
    enforced at render time instead (the renderer's rest
    assignment + ground rule, and the action dispatch); they are
    named here so the coverage gap is explicit, never silent.

    Fails when: the compile raises UnauthorizedStoryChange (an
    unresolved mandatory conflict -- wired as a preflight
    failure, never a crash); any record's fails_preflight is
    true; or an R3 record exists (the compiler emitted a verb
    the parser's resolution forbids -- staging it would stage
    the wrong story, so resolution alone does not clear it).
    Resolved R1/R2 records pass with the resolution counted in
    the detail. An ordinary compile failure also fails: the
    semantic safety net could not be validated.
    """
    try:
        return _semantic_preflight_checks_inner(package)
    except UnauthorizedStoryChange as exc:  # pragma: no cover
        return [PreflightCheck(
            "semantic_conflicts", False,
            f"UnauthorizedStoryChange: {exc}"[:300])]
    except Exception as exc:  # noqa: BLE001 - preflight must report
        return [PreflightCheck(
            "semantic_preflight", False,
            f"{type(exc).__name__}: {exc}"[:300])]


def _semantic_preflight_checks_inner(package: dict
                                     ) -> list[PreflightCheck]:
    cue_records = [r for s in (package.get("scenes") or [])
                   for r in (s.get("cue_records") or [])]
    sem_sink: list = []
    con_sink: list = []
    try:
        events, unsupported = compile_actions(
            package, inferred_cues=cue_records or None,
            semantic_sink=sem_sink, conflict_sink=con_sink)
    except UnauthorizedStoryChange as exc:
        return [PreflightCheck(
            "semantic_conflicts", False,
            f"UnauthorizedStoryChange: {exc}"[:300])]
    except Exception as exc:  # noqa: BLE001 - see docstring
        return [PreflightCheck(
            "semantic_compile", False,
            f"{type(exc).__name__}: {exc}"[:300])]
    records = detect_conflicts(
        semantic_actions=sem_sink, cue_records=cue_records,
        compiled_events=events, unsupported=unsupported)
    failing = [r for r in records
               if r.fails_preflight or r.level_a == "parser"]
    if failing:
        detail = "; ".join(r.description for r in failing)[:400]
        return [PreflightCheck(
            "semantic_conflicts", False,
            f"{len(failing)} blocking semantic conflict(s): {detail}")]
    resolved = len(records)
    conflict_check = PreflightCheck(
        "semantic_conflicts", True,
        f"{resolved} conflict record(s), all resolved, 0 blocking; "
        f"{len(events)} events, {len(sem_sink)} semantic actions "
        f"(R1-R3 checked; R4/R5 enforced at render time)")
    # Canonical scene graph: structural validation over the same
    # compile outputs. A broken graph fails preflight alongside
    # the conflict check.
    try:
        graph = build_scene_graph(
            package, events, semantic_actions=sem_sink,
            unsupported=unsupported)
        validate_or_raise(graph)
    except GraphValidationError as exc:
        return [conflict_check, PreflightCheck(
            "scene_graph", False,
            f"GraphValidationError: {exc}"[:300])]
    validation = graph["validation"]
    checks = [conflict_check, PreflightCheck(
        "scene_graph", True,
        f"{len(graph['scenes'])} scenes, {len(graph['shots'])} shots, "
        f"{len(graph['events'])} events, "
        f"{len(graph['semantic_actions'])} semantic actions, "
        f"{len(validation['warnings'])} warning(s)")]
    # Prop-state timelines (directive section 7): a prop taken from
    # a pocket cannot then be picked up from the ground in the same
    # scene without an intervening release. Checked per scene --
    # cross-scene carry-over is the scene graph's concern, and a
    # fresh scene may re-introduce a prop in a fresh state.
    props = package.get("props") or []
    by_scene: dict = {}
    for event in events:
        by_scene.setdefault(event.get("scene_number"), []).append(event)
    contradictions: list[str] = []
    for scene_no in sorted(by_scene, key=lambda x: (x is None, x)):
        try:
            SemanticPropTracker(props, by_scene[scene_no])
        except ForbiddenPropTransition as exc:
            contradictions.append(f"scene {scene_no}: {exc}")
    if contradictions:
        checks.append(PreflightCheck(
            "prop_states", False,
            "; ".join(contradictions)[:400]))
    else:
        checks.append(PreflightCheck(
            "prop_states", True,
            f"{len(by_scene)} scene(s), no prop-state contradiction"))
    # Prop kinds (directive section 8): an unknown mandatory prop
    # fails preflight -- the renderer must never silently draw a
    # generic fallback for a script-declared prop. "generic" is
    # the unclassified fallback kind: a script prop that resolved
    # to it has no renderable identity, so it fails here too.
    unknown = [(p.get("id") or p.get("name"), p.get("kind"))
               for p in props
               if (p.get("kind") or "") not in PROP_KINDS
               or p.get("kind") == "generic"]
    if unknown:
        detail = "; ".join(
            f"{pid} (kind {kind!r})" for pid, kind in unknown)[:300]
        checks.append(PreflightCheck(
            "prop_kinds", False,
            f"unknown prop kind(s), no renderer support: {detail}"))
    else:
        checks.append(PreflightCheck(
            "prop_kinds", True,
            f"{len(props)} prop(s), all kinds renderable"))
    # Actor resolution (sprint section 6): a classified action
    # with no resolvable actor fails preflight -- the pipeline
    # must never stage an action for a character it cannot name.
    no_actor = [u for u in unsupported
                if u.get("category") == "NO_ACTOR"]
    if no_actor:
        first = no_actor[0]
        checks.append(PreflightCheck(
            "actor_resolution", False,
            (f"[{ACTOR_RESOLUTION_FAILED}] {len(no_actor)} "
             f"action(s) with no resolvable actor; first: "
             f"{first.get('action_id')}: "
             f"{first.get('directive_text')!r}")[:300]))
    else:
        checks.append(PreflightCheck(
            "actor_resolution", True,
            f"{len(events)} event(s), every classified action "
            f"resolved to an actor"))
    return checks
