"""Source-to-render action trace (integration sprint section 4).

Reads a pipeline JOB DIRECTORY (durable artifacts only, never live
objects) and traces every mandatory action through eight stages:

  script -> semantic_parser -> adapter -> scene_graph -> compiler
  -> planner -> renderer -> video

with the actual frame range each action renders in. No mandatory
action may disappear silently: every compiled event and every
unsupported entry appears exactly once. A compiled event missing
from a downstream stage is a GAP naming the stage; an unsupported
entry carries its classification handling (section 6) -- listed,
never dropped.

Frame ranges are [start, end) at the job fps. This report checks
TRACEABILITY (did the action survive each stage with evidence?),
never creative quality -- a traced action can still look bad; that
is Creative QA's verdict, not this report's.

Artifacts consumed (all optional; absence is reported, never fatal):
  scene_package.json, semantic_actions.json, scene_graph.json,
  action_events.json, timeline.json, camera_accounting.json,
  frames/motion_report.json, draft.mp4.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

STAGES = ("script", "semantic_parser", "adapter", "scene_graph",
          "compiler", "planner", "renderer", "video")

TRACE_VERSION = 1


def _load(job_dir: Path, name: str):
    path = job_dir / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _frames(start_sec, end_sec, fps, total_frames):
    if start_sec is None or end_sec is None:
        return None
    lo = max(0, int(float(start_sec) * fps))
    hi = min(total_frames, int(round(float(end_sec) * fps))) \
        if total_frames else int(round(float(end_sec) * fps))
    return [lo, max(lo, hi)]


def _stage(present, evidence, **detail):
    record = {"present": bool(present), "evidence": evidence}
    record.update(detail)
    return record


def _scene_haystacks(package):
    """Normalized searchable text per scene number: the scene's
    action_text plus the action_text of the package's shots in
    that scene (directive sentences live in both)."""
    haystacks = {}
    for scene in package.get("scenes") or []:
        number = scene.get("number")
        haystacks[number] = _norm(scene.get("action_text"))
    for shot in package.get("shots") or []:
        number = shot.get("scene")
        text = _norm(shot.get("action_text"))
        if number in haystacks and text:
            haystacks[number] += " " + text
    return haystacks


def _adapter_shot_ids(package):
    ids = set()
    for directive in package.get("shot_directives") or []:
        if directive.get("shot_id"):
            ids.add(directive["shot_id"])
    for shot in package.get("shots") or []:
        for key in ("shot_id", "id", "directive_shot_id"):
            if shot.get(key):
                ids.add(shot[key])
    return ids


def _graph_event_ids(graph):
    events = graph.get("events") or {}
    if isinstance(events, dict):
        return set(events)
    return {e.get("action_id") for e in events if e.get("action_id")}


def _graph_semantic_ids(graph):
    sem = graph.get("semantic_actions") or {}
    if isinstance(sem, dict):
        return set(sem)
    ids = set()
    for record in sem:
        for key in ("action_id", "source_directive_id"):
            if record.get(key):
                ids.add(record[key])
    return ids


def _shot_spans(timeline):
    """(start, end, event_ids, index, action_text, scene) per shot.

    Uses the persisted start_sec when present, else the cumulative
    clock over durations."""
    spans = []
    clock = 0.0
    for index, shot in enumerate(timeline.get("shots") or []):
        duration = float(shot.get("duration") or 0.0)
        start = shot.get("start_sec")
        start = float(start) if start is not None else clock
        spans.append((start, start + duration,
                      list(shot.get("event_ids") or []), index,
                      _norm(shot.get("action_text")),
                      shot.get("scene")))
        clock = start + duration
    return spans


def _camera_frame_ranges(accounting):
    ranges = {}
    if isinstance(accounting, dict):
        for entry in accounting.get("entries", []) or []:
            key = entry.get("directive_id") or entry.get("shot_id")
            frame_ranges = entry.get("frame_ranges") or \
                entry.get("frame_range")
            if key and frame_ranges:
                ranges[key] = frame_ranges
    return ranges


def build_action_trace(job_dir) -> dict:
    """Trace every mandatory action in one job directory."""
    job_dir = Path(job_dir)
    package = _load(job_dir, "scene_package.json") or {}
    sem_actions = _load(job_dir, "semantic_actions.json")
    graph = _load(job_dir, "scene_graph.json") or {}
    action_data = _load(job_dir, "action_events.json") or {}
    timeline = _load(job_dir, "timeline.json") or {}
    motion = _load(job_dir, "frames/motion_report.json")
    accounting = _load(job_dir, "camera_accounting.json")
    fps = int((motion or {}).get("fps") or 24)
    total_frames = int((motion or {}).get("total_frames") or 0)
    draft_exists = (job_dir / "draft.mp4").exists()

    artifacts = {}
    for name in ("scene_package.json", "semantic_actions.json",
                 "scene_graph.json", "action_events.json",
                 "timeline.json", "camera_accounting.json",
                 "frames/motion_report.json", "draft.mp4"):
        artifacts[name] = (job_dir / name).exists()

    haystacks = _scene_haystacks(package)
    adapter_ids = _adapter_shot_ids(package)
    graph_ids = _graph_event_ids(graph)
    graph_sem_ids = _graph_semantic_ids(graph)
    graph_unsupported = {u.get("action_id")
                         for u in graph.get("unsupported") or []}
    sem_pairs = set()
    if isinstance(sem_actions, list):
        for record in sem_actions:
            sem_pairs.add((_norm(record.get("source_shot_id")),
                           _norm(record.get("source_text"))))
    spans = _shot_spans(timeline)
    cam_ranges = _camera_frame_ranges(accounting)

    shot_reports = (motion or {}).get("shots", []) or []
    dispatched: dict[str, list] = {}
    fallback_ids: set[str] = set()
    for rep in shot_reports:
        for aid in rep.get("action_event_ids") or []:
            dispatched.setdefault(aid, []).append(rep.get("index"))
        for entry in rep.get("action_dispatch_fallback") or []:
            aid = entry if isinstance(entry, str) else entry.get(
                "action_id") or entry.get("id")
            if aid:
                fallback_ids.add(aid)

    events = action_data.get("events") or []
    unsupported = action_data.get("unsupported") or []
    classification = action_data.get("unsupported_classification")
    if not classification:
        try:
            from .production_errors import classify_unsupported
            classification = classify_unsupported(unsupported, package)
        except Exception:  # noqa: BLE001 - unclassified, not fatal
            classification = {"entries": [], "counts": {},
                              "warnings": []}
    handling_by_id = {}
    for entry in classification.get("entries") or []:
        handling_by_id[entry.get("action_id")] = entry

    items = []
    gaps = []
    for event in events:
        items.append(_trace_event(
            event, haystacks, adapter_ids, graph_ids, graph_sem_ids,
            sem_pairs, spans, dispatched, fallback_ids, fps,
            total_frames, draft_exists, gaps))
    for entry in unsupported:
        items.append(_trace_unsupported(
            entry, haystacks, adapter_ids, graph_unsupported,
            graph_sem_ids, sem_pairs, spans, cam_ranges,
            handling_by_id.get(entry.get("action_id")), fps,
            total_frames))

    summary = {
        "events": len(events),
        "unsupported": len(unsupported),
        "traced": sum(1 for i in items if i["status"] == "TRACED"),
        "gaps": {},
        "unsupported_by_class": {},
        "gap_items": [g["action_id"] for g in gaps],
    }
    for item in items:
        if item["status"].startswith("GAP_AT_"):
            stage = item["status"][len("GAP_AT_"):]
            summary["gaps"][stage] = summary["gaps"].get(stage, 0) + 1
        elif item["status"].startswith("UNSUPPORTED_"):
            klass = item["status"][len("UNSUPPORTED_"):]
            summary["unsupported_by_class"][klass] = \
                summary["unsupported_by_class"].get(klass, 0) + 1
    return {
        "trace_version": TRACE_VERSION,
        "job_dir": str(job_dir),
        "fps": fps,
        "total_frames": total_frames,
        "artifacts_present": artifacts,
        "summary": summary,
        "gaps": gaps,
        "items": items,
    }


def _trace_event(event, haystacks, adapter_ids, graph_ids,
                 graph_sem_ids, sem_pairs, spans, dispatched,
                 fallback_ids, fps, total_frames, draft_exists,
                 gaps):
    aid = event.get("action_id")
    text = event.get("directive_text") or ""
    normed = _norm(text)
    shot_id = event.get("shot_id")
    scene_no = event.get("scene_number")
    stages = {}

    haystack = haystacks.get(scene_no, "")
    stages["script"] = _stage(
        bool(normed) and normed in haystack,
        "directive sentence found in the scene's action_text"
        if normed in haystack and normed else
        "directive sentence not found in the scene package text",
        shot_id=shot_id, scene_number=scene_no)

    sem_hit = (aid in graph_sem_ids or
               (_norm(shot_id), normed) in sem_pairs)
    stages["semantic_parser"] = _stage(
        sem_hit,
        "semantic action record with this id/text"
        if sem_hit else
        "no semantic action record for this directive",
        source="scene_graph" if aid in graph_sem_ids
        else "semantic_actions.json")

    stages["adapter"] = _stage(
        shot_id in adapter_ids,
        f"shot {shot_id} present in the adapted package"
        if shot_id in adapter_ids else
        f"shot {shot_id} absent from the adapted package")

    stages["scene_graph"] = _stage(
        aid in graph_ids,
        "event present in the canonical scene graph"
        if aid in graph_ids else
        "event absent from the canonical scene graph")

    stages["compiler"] = _stage(
        True, "compiled event record",
        action_type=event.get("action_type"),
        actor_id=event.get("actor_id"),
        start_time=event.get("start_time"),
        end_time=event.get("end_time"))

    start = event.get("start_time")
    end = event.get("end_time")
    strong = [s[3] for s in spans if aid in s[2]]
    overlap = [s[3] for s in spans
               if start is not None and end is not None
               and float(start) < s[1] and float(end) > s[0]]
    planned = strong or overlap
    stages["planner"] = _stage(
        bool(planned),
        ("event_ids membership in timeline shot(s)"
         if strong else
         "time-span overlap with timeline shot(s)"
         if overlap else
         "no timeline shot carries or overlaps this event"),
        shot_indices=planned,
        match="event_ids" if strong else "overlap" if overlap else None)

    shot_indices = dispatched.get(aid, [])
    fell_back = aid in fallback_ids
    stages["renderer"] = _stage(
        bool(shot_indices),
        ("dispatched by the primitive/prop system"
         + (" (fell back to idle/legacy pose in at least one shot)"
            if fell_back else ""))
        if shot_indices else
        "dispatched by no shot in the motion report",
        shot_indices=shot_indices, fell_back=fell_back)

    frame_range = _frames(start, end, fps, total_frames)
    in_video = bool(shot_indices and draft_exists and frame_range
                    and frame_range[1] > frame_range[0]
                    and (not total_frames
                         or frame_range[0] < total_frames))
    stages["video"] = _stage(
        in_video,
        ("rendered frames in draft.mp4"
         if in_video else
         "no dispatched frames in the rendered video"),
        frame_range=frame_range, draft_exists=draft_exists)

    status = "TRACED"
    for stage in STAGES:
        if not stages[stage]["present"]:
            status = f"GAP_AT_{stage}"
            gaps.append({"action_id": aid, "stage": stage,
                         "shot_id": shot_id, "scene_number": scene_no,
                         "directive_text": text,
                         "evidence": stages[stage]["evidence"]})
            break
    return {
        "action_id": aid, "kind": "event",
        "action_type": event.get("action_type"),
        "actor_id": event.get("actor_id"),
        "target_id": event.get("target_id"),
        "prop_id": event.get("prop_id"),
        "directive_text": text,
        "shot_id": shot_id, "scene_number": scene_no,
        "notes": event.get("notes"),
        "stages": stages, "frame_range": frame_range,
        "frame_range_source": "event_span" if frame_range else None,
        "status": status,
    }


def _trace_unsupported(entry, haystacks, adapter_ids, graph_unsupported,
                       graph_sem_ids, sem_pairs, spans, cam_ranges,
                       classified, fps, total_frames):
    aid = entry.get("action_id") or entry.get("id")
    text = entry.get("directive_text") or entry.get("text") or ""
    normed = _norm(text)
    shot_id = entry.get("shot_id")
    scene_no = entry.get("scene_number")
    handling_class = (classified or {}).get("handling_class",
                                            "UNCLASSIFIED")
    handling = (classified or {}).get(
        "handling", "no classification record; listed, unstaged")
    stages = {}

    haystack = haystacks.get(scene_no, "")
    stages["script"] = _stage(
        bool(normed) and normed in haystack,
        "directive sentence found in the scene's action_text"
        if normed in haystack and normed else
        "directive sentence not found in the scene package text",
        shot_id=shot_id, scene_number=scene_no)

    sem_hit = (aid in graph_sem_ids or
               (_norm(shot_id), normed) in sem_pairs)
    stages["semantic_parser"] = _stage(
        sem_hit,
        "semantic action record present (informational: "
        "unsupported entries need none)"
        if sem_hit else
        "no semantic action record (expected for unmapped "
        "sentences)")

    stages["adapter"] = _stage(
        shot_id in adapter_ids,
        f"shot {shot_id} present in the adapted package"
        if shot_id in adapter_ids else
        f"shot {shot_id} absent from the adapted package")

    stages["scene_graph"] = _stage(
        aid in graph_unsupported,
        "entry present in the scene graph's unsupported list"
        if aid in graph_unsupported else
        "entry absent from the scene graph's unsupported list")

    stages["compiler"] = _stage(
        True, "compiler reported unsupported (never staged)",
        category=entry.get("category"),
        reason=entry.get("reason") or entry.get("detail"))

    # The planner/renderer/video stages never see an unsupported
    # sentence; that is the classification's verdict, not a gap.
    # The frame range comes from the owning shot, so the sentence
    # stays located in the rendered video.
    frame_range = None
    frame_source = None
    for start, end, _ids, _idx, action_text, scene in spans:
        if scene == scene_no and normed and normed in action_text:
            frame_range = _frames(start, end, fps, total_frames)
            frame_source = "owning_shot"
            break
    if frame_range is None and shot_id in cam_ranges:
        ranges = cam_ranges[shot_id]
        first = ranges[0] if ranges and isinstance(ranges[0], list) \
            else ranges
        if isinstance(first, list) and len(first) == 2:
            frame_range = [int(first[0]), int(first[1])]
            frame_source = "camera_accounting"
    stages["planner"] = _stage(
        False, f"not staged: {handling}")
    stages["renderer"] = _stage(
        False, f"not staged: {handling}")
    stages["video"] = _stage(
        False, f"not staged: {handling}",
        frame_range=frame_range)
    return {
        "action_id": aid, "kind": "unsupported",
        "category": entry.get("category"),
        "directive_text": text,
        "shot_id": shot_id, "scene_number": scene_no,
        "stages": stages, "frame_range": frame_range,
        "frame_range_source": frame_source,
        "status": f"UNSUPPORTED_{handling_class}",
        "handling_class": handling_class,
        "handling": handling,
    }


__all__ = ["STAGES", "TRACE_VERSION", "build_action_trace"]
