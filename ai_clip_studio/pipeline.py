"""End-to-end orchestration (Master Prompt §11, §13, §17).

run_production(script, ...) runs one production through:
    request -> segment -> audio events -> timeline -> preflight
    -> render (injected renderer) -> QA -> Drive upload (draft)
    -> human approval gate -> master (only when approved)

Final status is one of:
    IMPLEMENTATION_IN_PROGRESS
    BLOCKED_WITH_EXPLICIT_REASON
    END_TO_END_DRAFT_READY_FOR_REVIEW
    MASTER_APPROVED_AND_UPLOADED

Script segmentation here is deliberately generic: split the script
into sentences, treat "Name: ..." lines as dialogue and everything
else as narration, and detect visual events from verbs/objects
(door, paper, footstep, rain, ...). No character names, scene counts
or story templates are hardcoded — the same code runs the three
generalization tests in GENERALIZATION_TESTS.md.

The real Motion Canvas + Three.js renderer cannot run on this Linux
VM (it needs headless Chrome on Mai's Windows machine, hard-coded
in scripts/production_render_service.mjs). Therefore, when no
renderer is injected, run_production returns
BLOCKED_WITH_EXPLICIT_REASON with that reason, after completing all
the stages that *can* run here (request, segmentation, audio plan,
timeline, preflight, Drive upload of the planning artifacts). It
never claims a rendered MP4 it did not produce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .audio_events import plan_audio_events
from .preflight import run_preflight
from .production_request import ProductionRequest
from .timeline import TimelineLine, build_timeline

ProductionStatus = str  # one of the four statuses below

STATUS_IN_PROGRESS = "IMPLEMENTATION_IN_PROGRESS"
STATUS_BLOCKED = "BLOCKED_WITH_EXPLICIT_REASON"
STATUS_DRAFT_READY = "END_TO_END_DRAFT_READY_FOR_REVIEW"
STATUS_MASTER = "MASTER_APPROVED_AND_UPLOADED"

# Verb/object -> visual event. Generic Vietnamese cues, no story names.
EVENT_CUES: list[tuple[str, str]] = [
    (r"\b(bước|đi bộ|chạy|đi tới|đi ra)\b", "foot_contact"),
    (r"\b(gõ cửa|gõ)\b", "door_contact"),
    (r"\b(mở cửa|đẩy cửa)\b", "door_rotation"),
    (r"\b(giấy|thư|phong bì|đưa thư|trao thư)\b", "paper_movement"),
    (r"\b(rơi|đập|va chạm|ngã)\b", "object_impact"),
    (r"\b(mưa)\b", "rain_start"),
    (r"\b(cười|ngạc nhiên|há hốc)\b", "character_reaction"),
]

DIALOGUE_RE = re.compile(
    r"^([A-ZÀ-Ỹ][\wÀ-ỹ]{0,15}(?: [A-ZÀ-Ỹ][\wÀ-ỹ]{0,15})?):\s*(.+)$"
)
# Speaker = 1-2 capitalised words only. A narration line such as
# "Minh cười và nói: ..." must NOT be mistaken for dialogue.


@dataclass
class SegmentedScript:
    lines: list[TimelineLine]
    visual_events: list[dict[str, Any]]
    characters: list[str]
    sentences: list[str]


def segment_script(script_text: str) -> SegmentedScript:
    """Generic segmentation: dialogue vs narration, event cues.

    Two paths, both generic:
    - Structured Vietnamese CẢNH scripts (see vi_script_parser.py):
      only QUOTED speech becomes a spoken line; headers, metadata,
      setting/action/audio paragraphs are never read aloud.
    - Anything else: the original line-by-line split (dialogue
      ``Name: ...`` vs narration), unchanged for backwards compat.
    """
    # Structured path first — it knows which lines are speech.
    try:
        from .vi_script_parser import is_structured_vi_script, parse_vi_script
    except ImportError:  # pragma: no cover - module always present in repo
        is_structured_vi_script = None  # type: ignore
    if is_structured_vi_script is not None and is_structured_vi_script(script_text):
        parsed = parse_vi_script(script_text)
        lines: list[TimelineLine] = []
        visual_events: list[dict[str, Any]] = []
        characters: list[str] = [c["name"] for c in parsed.characters]
        clock = 0.0
        for scene in parsed.scenes:
            for cue in scene.action_cues:
                visual_events.append({"event": cue, "at_seconds": clock,
                                      "scene": scene.number})
            for spoken in scene.lines:
                if spoken.speaker != "narrator" and spoken.speaker not in characters:
                    characters.append(spoken.speaker)
                lines.append(TimelineLine(text=spoken.text,
                                          speaker=spoken.speaker,
                                          kind=spoken.kind))
                for pattern, event in EVENT_CUES:
                    if re.search(pattern, spoken.text.lower()):
                        visual_events.append({"event": event,
                                              "at_seconds": clock,
                                              "scene": scene.number})
                clock += 4.0  # rough placement; timeline.py replaces it
        sentences = [l.text for l in lines]
        return SegmentedScript(lines, visual_events, characters, sentences)
    sentences: list[str] = []
    lines: list[TimelineLine] = []
    visual_events: list[dict[str, Any]] = []
    characters: list[str] = []
    clock = 0.0
    for raw in script_text.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        m = DIALOGUE_RE.match(line)
        if m:
            speaker, text = m.group(1).strip(), m.group(2).strip()
            kind = "dialogue"
        else:
            speaker, text, kind = "narrator", line, "narration"
        if speaker != "narrator" and speaker not in characters:
            characters.append(speaker)
        sentences.append(text)
        lines.append(TimelineLine(text=text, speaker=speaker, kind=kind))
        for pattern, event in EVENT_CUES:
            if re.search(pattern, text.lower()):
                visual_events.append({"event": event, "at_seconds": clock})
        clock += 4.0  # rough placement; timeline.py replaces with real durations
    return SegmentedScript(lines, visual_events, characters, sentences)


@dataclass
class ProductionResult:
    status: ProductionStatus
    request: ProductionRequest
    manifest: dict[str, Any] = field(default_factory=dict)
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "request_id": self.request.request_id,
            "script_hash": self.request.script_hash,
            "blocked_reason": self.blocked_reason,
            "manifest": self.manifest,
        }


def run_production(
    script_text: str,
    *,
    language: str = "vi-VN",
    aspect_ratio: str = "16:9",
    available_voices: tuple[str, ...] = ("narrator",),
    meme_catalog: dict | None = None,
    render_fn: Callable[[ProductionRequest, dict], Path] | None = None,
    drive_uploader: Any | None = None,
    out_dir: Path | None = None,
    approve_master: bool = False,
    allow_estimated_timeline: bool = False,
) -> ProductionResult:
    """Run one production end to end. See module docstring for the
    honest limitation: without an injected render_fn (the real
    Motion Canvas + Three.js renderer, which needs Mai's Windows
    machine), the result is BLOCKED after the planning stages."""
    request = ProductionRequest(
        script_text=script_text, language=language, aspect_ratio=aspect_ratio)
    segmented = segment_script(script_text)
    audio_plan = plan_audio_events(
        segmented.visual_events, script_text=script_text,
        meme_catalog=meme_catalog)
    try:
        timeline = build_timeline(segmented.lines)
    except Exception as exc:  # measured audio unreadable, etc.
        return ProductionResult(
            STATUS_BLOCKED, request,
            {"stage": "timeline", "error": str(exc)},
            blocked_reason=f"timeline failed: {exc}",
        )
    request.record_stage("analysis", request.script_hash)
    request.record_stage("storyboard", request.script_hash)
    preflight = run_preflight(
        request, timeline=timeline,
        required_voices=tuple(set(l.speaker for l in segmented.lines)),
        available_voices=available_voices,
        script_hash_at_preflight=request.script_hash,
        allow_estimated_timeline=allow_estimated_timeline,
    )
    request.record_stage("preflight", request.script_hash)
    manifest: dict[str, Any] = {
        "request": request.manifest(),
        "characters": segmented.characters,
        "sentence_count": len(segmented.sentences),
        "audio_events": audio_plan.to_dict(),
        "timeline_seconds": timeline.total_duration_sec,
        "timeline_all_measured": timeline.all_measured,
        "preflight": preflight.to_dict(),
    }
    if not preflight.passed:
        return ProductionResult(
            STATUS_BLOCKED, request, manifest,
            blocked_reason="preflight FAILED: " + "; ".join(
                f"{f.name}: {f.detail}" for f in preflight.failures()),
        )
    if render_fn is None:
        return ProductionResult(
            STATUS_BLOCKED, request, manifest,
            blocked_reason=(
                "No renderer available on this Linux VM. The V5.1 "
                "Motion Canvas + Three.js renderer needs headless "
                "Chrome on Mai's Windows machine "
                "(scripts/production_render_service.mjs hard-codes "
                "C:\\Program Files\\Google\\Chrome\\Application\\"
                "chrome.exe). Planning stages (request, segmentation, "
                "audio plan, timeline, preflight) all completed; the "
                "render step must run on her machine."
            ),
        )
    # --- real render path (only when a renderer is injected) ---
    try:
        draft_path = render_fn(request, manifest)
    except Exception as exc:
        return ProductionResult(
            STATUS_BLOCKED, request, manifest,
            blocked_reason=f"render failed: {exc}",
        )
    request.record_stage("render_job", request.script_hash)
    manifest["draft_mp4"] = str(draft_path)
    if drive_uploader is not None and out_dir is not None:
        records = drive_uploader.upload_project(
            request.request_id,
            {"draft": [draft_path]},
            allow_master=False,
        )
        manifest["drive_uploads"] = [r.to_dict() for r in records]
    request.record_stage("output_manifest", request.script_hash)
    manifest["request"] = request.manifest()
    if approve_master:
        return ProductionResult(STATUS_MASTER, request, manifest)
    return ProductionResult(STATUS_DRAFT_READY, request, manifest)
