"""P9 script-coverage audit: every script item -> a status with evidence.

Reads a pipeline JOB DIRECTORY (the durable artifacts, never live
objects) and reports, for every scene, camera directive, spoken line,
compiled action, unsupported action, expression, prop, audio cue, and
location constraint in the source script:

  IMPLEMENTED            evidence shows the item rendered as specified
  PARTIALLY_IMPLEMENTED  rendered, but with a fallback, default, or
                         partial staging (the detail names it)
  UNSUPPORTED            the engine explicitly reports it unsupported
                         (compiler category, no staging requirement)
  FAILED                 required but not rendered, or no evidence
                         artifact exists to show it rendered

No silent omission: an item with no evidence artifact is FAILED with
evidence_quality "missing" and the absent artifact named — it is never
assumed rendered. Frame ranges are [start, end) at the job fps. This
audit checks COVERAGE (did the item reach the render?), never creative
quality — a rendered item can still look bad; that is Creative QA's
verdict, not this report's.

Artifacts consumed (all optional; absence is reported, never fatal):
  scene_package.json, frames/motion_report.json, camera_accounting.json,
  action_events.json, subtitles.json, timeline.json, audio_plan.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

STATUSES = ("IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "UNSUPPORTED", "FAILED")

HELD_STATES = {"GRASPED", "ATTACHED_TO_HAND", "IN_USE", "TRANSFERRED"}


def _load(job_dir: Path, name: str):
    path = job_dir / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _frames(start_sec, end_sec, fps, total_frames):
    if start_sec is None or end_sec is None:
        return None
    lo = max(0, int(float(start_sec) * fps))
    hi = min(total_frames, int(round(float(end_sec) * fps)))
    return [lo, max(lo, hi)]


def _item(category, item_id, label, status, detail, *,
          evidence_quality="artifact", frame_range=None, scene=None,
          refs=None):
    assert status in STATUSES, status
    return {
        "category": category, "id": item_id, "label": label,
        "status": status, "detail": detail,
        "evidence_quality": evidence_quality,
        "frame_range": frame_range, "scene": scene,
        "refs": refs or [],
    }


def _fallback_ids(shot_reports):
    """action_ids that fell back to idle/legacy dispatch, per shot."""
    out = {}
    for rep in shot_reports:
        fb = rep.get("action_dispatch_fallback") or []
        ids = set()
        for entry in fb:
            if isinstance(entry, str):
                ids.add(entry)
            elif isinstance(entry, dict):
                aid = entry.get("action_id") or entry.get("id")
                if aid:
                    ids.add(aid)
        if ids:
            out[rep.get("index")] = ids
    return out


def _audit_scenes(package, shot_reports, have_motion):
    scenes = package.get("scenes") or []
    rendered = {r.get("scene") for r in shot_reports}
    items = []
    for scene in scenes:
        number = scene.get("number")
        if not have_motion:
            items.append(_item(
                "scene", f"SC{number}", scene.get("title") or f"Scene {number}",
                "FAILED", "no motion_report.json artifact; rendering "
                          "unverified", evidence_quality="missing",
                scene=number))
        elif number in rendered:
            items.append(_item(
                "scene", f"SC{number}", scene.get("title") or f"Scene {number}",
                "IMPLEMENTED", "at least one rendered shot",
                scene=number))
        else:
            items.append(_item(
                "scene", f"SC{number}", scene.get("title") or f"Scene {number}",
                "FAILED", "no rendered shot for this scene", scene=number))
    return items


def _audit_directives(package, accounting, have_accounting):
    directives = package.get("shot_directives") or []
    items = []
    entries = {}
    if isinstance(accounting, dict):
        for entry in accounting.get("entries", []) or []:
            key = entry.get("directive_id") or entry.get("shot_id")
            if key:
                entries[key] = entry
    for directive in directives:
        did = directive.get("shot_id")
        label = (f"{did} {directive.get('shot_type') or ''} "
                 f"{directive.get('camera_angle') or ''}").strip()
        if not have_accounting:
            items.append(_item(
                "camera_directive", did, label, "FAILED",
                "no camera_accounting.json artifact (pre-recovery job); "
                "directive coverage unverified",
                evidence_quality="missing",
                scene=directive.get("scene")))
            continue
        entry = entries.get(did)
        if entry is None:
            items.append(_item(
                "camera_directive", did, label, "FAILED",
                "directive absent from camera accounting",
                scene=directive.get("scene")))
            continue
        status = entry.get("status")
        frame_range = entry.get("frame_range")
        if status == "rendered":
            items.append(_item(
                "camera_directive", did, label, "IMPLEMENTED",
                f"rendered by shot(s) {entry.get('shot_indices')}",
                frame_range=frame_range, scene=directive.get("scene"),
                refs=[f"shot:{i}" for i in entry.get("shot_indices") or []]))
        elif status == "type_defaulted":
            items.append(_item(
                "camera_directive", did, label, "PARTIALLY_IMPLEMENTED",
                "rendered with a defaulted shot type; the directive's "
                "own type did not drive the shot",
                frame_range=frame_range, scene=directive.get("scene")))
        else:
            items.append(_item(
                "camera_directive", did, label, "FAILED",
                "directive drove no shot (not_rendered)",
                frame_range=frame_range, scene=directive.get("scene")))
    return items


def _audit_lines(package, subtitles, fps, total_frames):
    subs = {}
    if isinstance(subtitles, list):
        for entry in subtitles:
            if isinstance(entry, dict):
                subs[entry.get("line_index")] = entry
    items = []
    # Package scene lines carry no line_index; subtitle entries are
    # keyed by the flat 1-based line order across scenes.
    flat_index = 0
    for scene in package.get("scenes") or []:
        for line in scene.get("lines") or []:
            flat_index += 1
            idx = flat_index
            lid = line.get("line_id") or f"line_{idx}"
            entry = subs.get(idx)
            if entry is None:
                items.append(_item(
                    "spoken_line", lid,
                    _norm(line.get("text"))[:80], "FAILED",
                    "no subtitle entry for this line",
                    evidence_quality=("missing" if subtitles is None
                                      else "artifact"),
                    scene=scene.get("number")))
                continue
            rendered_text = _norm(" ".join(entry.get("phrases") or []))
            windows = entry.get("windows") or []
            frame_range = None
            if windows:
                frame_range = _frames(windows[0].get("start"),
                                      windows[-1].get("end"),
                                      fps, total_frames)
            if rendered_text == _norm(line.get("text")):
                items.append(_item(
                    "spoken_line", lid, _norm(line.get("text"))[:80],
                    "IMPLEMENTED", "subtitle text verbatim",
                    frame_range=frame_range, scene=scene.get("number")))
            else:
                items.append(_item(
                    "spoken_line", lid, _norm(line.get("text"))[:80],
                    "FAILED",
                    "subtitle text differs from the script line",
                    frame_range=frame_range, scene=scene.get("number")))
    return items


def _audit_actions(action_data, shot_reports, fps, total_frames,
                   have_action_events):
    items = []
    if not have_action_events:
        return [_item(
            "action_event", "(all)", "compiled actions", "FAILED",
            "no action_events.json artifact (pre-recovery job); action "
            "coverage unverified", evidence_quality="missing")]
    dispatched: dict[str, list] = {}
    for rep in shot_reports:
        for aid in rep.get("action_event_ids") or []:
            dispatched.setdefault(aid, []).append(rep.get("index"))
    fallbacks = _fallback_ids(shot_reports)
    fallback_all = set().union(*fallbacks.values()) if fallbacks else set()
    events = action_data.get("events") or []
    for event in events:
        aid = event.get("action_id")
        label = (f"{event.get('action_type')} "
                 f"{event.get('actor_id') or ''}").strip()
        frame_range = _frames(event.get("start_time"),
                              event.get("end_time"), fps, total_frames)
        refs = [f"shot:{i}" for i in dispatched.get(aid, [])]
        if aid in dispatched:
            if aid in fallback_all:
                items.append(_item(
                    "action_event", aid, label, "PARTIALLY_IMPLEMENTED",
                    "dispatched but fell back to idle/legacy pose in "
                    "at least one shot", frame_range=frame_range,
                    refs=refs))
            else:
                items.append(_item(
                    "action_event", aid, label, "IMPLEMENTED",
                    "dispatched by the primitive/prop system",
                    frame_range=frame_range, refs=refs))
            continue
        if event.get("overflow"):
            reason = ("compiled with overflow=True: the directive's span "
                      "was too short, the event overran it and rendered "
                      "in no shot")
        elif event.get("span_source") == "estimated":
            reason = ("span_source=estimated: the owning directive "
                      "drives no shot, so the event's times are "
                      "phantoms and it rendered nowhere")
        else:
            reason = "compiled but dispatched by no shot"
        items.append(_item(
            "action_event", aid, label, "FAILED", reason,
            frame_range=frame_range, refs=refs))
    for unsup in action_data.get("unsupported") or []:
        items.append(_item(
            "unsupported_action",
            unsup.get("action_id") or unsup.get("id") or "(unknown)",
            _norm(unsup.get("source_text") or unsup.get("text") or "")[:80],
            "UNSUPPORTED",
            f"compiler category {unsup.get('category')}: "
            f"{unsup.get('reason') or unsup.get('detail') or ''}".strip(),
            evidence_quality="artifact"))
    return items


def _audit_expressions(package):
    try:
        from .expression_library import EXPRESSIONS, interpret, \
            interpret_detailed
    except Exception:  # noqa: BLE001 - static check unavailable
        return [_item(
            "expression", "(all)", "expression mappings", "FAILED",
            "expression_library unavailable for the static mapping "
            "check", evidence_quality="missing")]
    try:
        from .product_renderer import LEGACY_MOOD_TO_EXPRESSION
    except Exception:  # noqa: BLE001 - legacy check unavailable
        LEGACY_MOOD_TO_EXPRESSION = {}
    items = []
    for scene in package.get("scenes") or []:
        for line in scene.get("lines") or []:
            text = (line.get("expression") or "").strip()
            if not text:
                continue
            lid = line.get("line_id") or f"line_{line.get('line_index')}"
            try:
                label = interpret(text)
                negated = bool(interpret_detailed(text).get("negated"))
            except Exception as exc:  # noqa: BLE001 - report, don't crash
                items.append(_item(
                    "expression", lid, text, "FAILED",
                    f"interpretation raised: {exc}",
                    evidence_quality="static",
                    scene=scene.get("number")))
                continue
            if label is not None and label in EXPRESSIONS:
                items.append(_item(
                    "expression", lid, text, "IMPLEMENTED",
                    f"maps to '{label}'"
                    + (" (negation-aware)" if negated else "")
                    + "; static mapping only — face rendering is not "
                      "frame-verified by this audit",
                    evidence_quality="static",
                    scene=scene.get("number")))
                continue
            legacy = LEGACY_MOOD_TO_EXPRESSION.get(text.strip().lower(),
                                                   text.strip().lower())
            if legacy in EXPRESSIONS:
                items.append(_item(
                    "expression", lid, text, "IMPLEMENTED",
                    f"maps to '{legacy}' via the legacy mood table; "
                    f"static mapping only",
                    evidence_quality="static",
                    scene=scene.get("number")))
                continue
            items.append(_item(
                "expression", lid, text, "PARTIALLY_IMPLEMENTED",
                "no library or legacy mapping; the face falls back "
                "to a text-derived expression, so the requested "
                "expression is not honored",
                evidence_quality="static",
                scene=scene.get("number")))
    return items


def _audit_props(package, action_data, shot_reports, have_action_events):
    props = package.get("props") or []
    scene_props = set()
    for scene in package.get("scenes") or []:
        for pid in scene.get("props") or []:
            scene_props.add(pid)
    event_props = set()
    if have_action_events and action_data:
        for event in action_data.get("events") or []:
            if event.get("prop_id"):
                event_props.add(event.get("prop_id"))
    drawn: dict[str, set] = {}
    for rep in shot_reports:
        for entry in rep.get("prop_draws") or []:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                drawn.setdefault(entry[0], set()).add(entry[1])
    items = []
    for prop in props:
        pid = prop.get("id")
        label = prop.get("name") or pid
        states = drawn.get(pid, set())
        held = states & HELD_STATES
        if held:
            items.append(_item(
                "prop", pid, label, "IMPLEMENTED",
                f"drawn in held state(s): {sorted(held)}"))
        elif states:
            items.append(_item(
                "prop", pid, label, "PARTIALLY_IMPLEMENTED",
                f"drawn only in resting state(s): {sorted(states)}; "
                f"never held"))
        elif pid in event_props:
            items.append(_item(
                "prop", pid, label, "FAILED",
                "manipulating events exist but the prop was drawn in "
                "no shot"))
        elif pid in scene_props:
            items.append(_item(
                "prop", pid, label, "FAILED",
                "declared in a scene's props but drawn in no shot"))
        else:
            items.append(_item(
                "prop", pid, label, "UNSUPPORTED",
                "no staging requirement: no manipulating events and "
                "no scene lists it"))
    return items


def _audit_cues(audio_plan, fps, total_frames):
    if audio_plan is None:
        return [_item(
            "audio_cue", "(all)", "audio cues", "FAILED",
            "no audio_plan.json artifact; cue coverage unverified",
            evidence_quality="missing")]
    resolution = audio_plan.get("v1_cue_resolution") or {}
    cues = resolution.get("cues") or []
    items = []
    for cue in cues:
        cid = cue.get("cue_id") or "(unknown)"
        trigger = cue.get("trigger") or {}
        frame_range = None
        if trigger.get("start") is not None:
            frame_range = _frames(trigger.get("start"),
                                  trigger.get("end") or trigger.get("start"),
                                  fps, total_frames)
        reasons = "; ".join(cue.get("reasons") or [])
        if cue.get("render") == "rendered":
            items.append(_item(
                "audio_cue", cid, cue.get("name") or cid, "IMPLEMENTED",
                reasons or "rendered", frame_range=frame_range,
                scene=cue.get("scene_number")))
        else:
            items.append(_item(
                "audio_cue", cid, cue.get("name") or cid, "FAILED",
                reasons or f"render status: {cue.get('render')}",
                frame_range=frame_range, scene=cue.get("scene_number")))
    return items


def _audit_locations(package, shot_reports, have_motion):
    locations = package.get("v1_locations") or []
    # v1_locations entries carry `id` and no scene list; map them via
    # each scene's trait block (scene location v1_location.location_id).
    id_to_scenes: dict[str, list] = {}
    for scene in package.get("scenes") or []:
        loc = scene.get("location") or {}
        v1_loc = loc.get("v1_location") or {}
        lid = v1_loc.get("location_id") or v1_loc.get("id")
        if lid:
            id_to_scenes.setdefault(lid, []).append(scene.get("number"))
    if not locations:
        locations = [{"id": (s.get("location") or {}).get("setting")
                      or f"scene_{s.get('number')}"}
                     for s in package.get("scenes") or []]
    by_scene: dict[int, list] = {}
    for rep in shot_reports:
        by_scene.setdefault(rep.get("scene"), []).append(rep)
    items = []
    for loc in locations:
        lid = loc.get("id") or loc.get("location_id") or "(unknown)"
        scenes = id_to_scenes.get(lid, [])
        reps = [r for n in scenes for r in by_scene.get(n, [])]
        archetypes = {r.get("environment_archetype") for r in reps
                      if r.get("environment_archetype")}
        map_reports = [r for r in reps if r.get("map_report")]
        if not scenes:
            items.append(_item(
                "location", lid, loc.get("name") or lid, "FAILED",
                "no scene's trait block references this location",
                scene=None))
        elif not have_motion:
            items.append(_item(
                "location", lid, loc.get("name") or lid, "FAILED",
                "no motion_report.json artifact; location staging "
                "unverified", evidence_quality="missing",
                scene=scenes[0] if scenes else None))
        elif map_reports:
            items.append(_item(
                "location", lid, loc.get("name") or lid, "IMPLEMENTED",
                "map rendered via map_renderer",
                scene=scenes[0] if scenes else None))
        elif archetypes and archetypes != {"GENERIC_NEUTRAL"}:
            items.append(_item(
                "location", lid, loc.get("name") or lid, "IMPLEMENTED",
                f"staged as {sorted(archetypes)}",
                scene=scenes[0] if scenes else None))
        elif archetypes:
            items.append(_item(
                "location", lid, loc.get("name") or lid,
                "PARTIALLY_IMPLEMENTED",
                "staged only as GENERIC_NEUTRAL fallback; no "
                "distinctive environment",
                scene=scenes[0] if scenes else None))
        elif reps:
            items.append(_item(
                "location", lid, loc.get("name") or lid,
                "PARTIALLY_IMPLEMENTED",
                "shots rendered but carry no environment archetype "
                "(pre-W2 job); distinctive staging unverified",
                scene=scenes[0] if scenes else None))
        else:
            items.append(_item(
                "location", lid, loc.get("name") or lid, "FAILED",
                "no rendered shot for this location's scene(s)",
                scene=scenes[0] if scenes else None))
    return items


def audit_coverage(job_dir) -> dict:
    """Audit one job directory. Returns the machine-readable report."""
    job_dir = Path(job_dir)
    package = _load(job_dir, "scene_package.json") or {}
    motion = _load(job_dir, "frames/motion_report.json")
    shot_reports = (motion or {}).get("shots", []) or []
    fps = int((motion or {}).get("fps") or 24)
    total_frames = int((motion or {}).get("total_frames") or 0)
    accounting = _load(job_dir, "camera_accounting.json")
    if accounting is None and isinstance(motion, dict):
        accounting = motion.get("camera_accounting")
    action_data = _load(job_dir, "action_events.json")
    subtitles = _load(job_dir, "subtitles.json")
    audio_plan = _load(job_dir, "audio_plan.json")

    artifacts = {}
    for name in ("scene_package.json", "frames/motion_report.json",
                 "camera_accounting.json", "action_events.json",
                 "subtitles.json", "timeline.json", "audio_plan.json"):
        artifacts[name] = (job_dir / name).exists()

    items = []
    items.extend(_audit_scenes(package, shot_reports, motion is not None))
    items.extend(_audit_directives(package, accounting, accounting is not None))
    items.extend(_audit_lines(package, subtitles, fps, total_frames))
    items.extend(_audit_actions(action_data, shot_reports, fps,
                                total_frames, action_data is not None))
    items.extend(_audit_expressions(package))
    items.extend(_audit_props(package, action_data, shot_reports,
                              action_data is not None))
    items.extend(_audit_cues(audio_plan, fps, total_frames))
    items.extend(_audit_locations(package, shot_reports, motion is not None))

    summary: dict[str, dict[str, int]] = {}
    for item in items:
        bucket = summary.setdefault(item["category"], {})
        bucket[item["status"]] = bucket.get(item["status"], 0) + 1
    totals = {status: sum(1 for i in items if i["status"] == status)
              for status in STATUSES}
    return {
        "audit": "P9 script coverage",
        "job_dir": str(job_dir),
        "fps": fps,
        "total_frames": total_frames,
        "artifacts_present": artifacts,
        "summary": summary,
        "totals": totals,
        "items": items,
    }
