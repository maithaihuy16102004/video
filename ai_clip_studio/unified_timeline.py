"""Unified production timeline (directive section 9).

One authoritative clock for the whole production: integer frame indices
(24 fps) and integer audio sample indices (48 kHz) are authoritative;
seconds are derived and must never accumulate drift.

The pipeline builds the schedule in the order stages produce their
tracks (shots + lines after TTS measurement, actions after the
authoritative compile, SFX/ambience/music after cue resolution,
subtitles after splitting), then FREEZES it. After the freeze, any
mutation attempt raises: downstream modules must not move spoken-line
placement or any interval. A scheduling conflict requires an explicit
rebuild of the builder, never a silent overwrite.

Validation enforced by the builder:
* the shots track tiles [0, total) contiguously in FRAME space -- no
  gaps, no overlaps;
* narration/dialogue line ids are unique and their frame spans never
  overlap (spoken lines are sequential; the pause beat separates them);
* every interval's frame/sample indices derive from one rounding rule
  (round-half-up), applied to the same input seconds.

The frozen schedule is persisted as unified_timeline.json in the job
dir and is the reference Technical QA compares the rendered MP4
against: the media is built on the shot clock (+ tail), NOT on the
pre-plan Timeline estimate (the 0.612 s Zeus false failure).

Sprint section 8: the frozen schedule carries a version and a
SHA-256 checksum over its canonical content. Every downstream
dict-shaped artifact references the frozen schedule via its
``timeline_ref`` (version + checksum); list-shaped artifacts
(subtitles, animation plan, semantic records) cannot carry a dict
key, so their timeline linkage is the unified timeline's own tracks
plus the job record. ``stamp_timeline_refs`` writes the references;
``check_timeline_refs`` verifies them (used by the MP4 verifier).
A schedule version increments only on an explicit rebuild; the
pipeline freezes once per job, so production timelines are
version 1 -- a rebuild is a new builder with version + 1, never a
silent overwrite of the frozen schedule.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .semantic_contracts import FrozenSchedule, TimelineInterval

FPS = 24
SAMPLE_RATE = 48000
TAIL_SEC = 0.5

# Tracks on which intervals must never overlap (exclusive resources).
_EXCLUSIVE_TRACKS = frozenset({"narration", "dialogue", "shots"})


class SchedulingConflict(ValueError):
    """Two intervals disagree about the schedule. Rebuild explicitly."""


def sec_to_frame(seconds: float, fps: int = FPS) -> int:
    """Round-half-up conversion. One rule, used by every track."""
    return int(math.floor(float(seconds) * fps + 0.5))


def sec_to_sample(seconds: float, sample_rate: int = SAMPLE_RATE) -> int:
    return int(math.floor(float(seconds) * sample_rate + 0.5))


@dataclass(frozen=True)
class UnifiedTimeline:
    """The frozen schedule + per-interval payloads + media totals."""

    schedule: FrozenSchedule
    payloads: dict[str, dict[str, Any]]
    total_frames: int
    total_samples: int
    fps: int = FPS
    sample_rate: int = SAMPLE_RATE
    tail_sec: float = TAIL_SEC
    version: int = 1

    @property
    def total_sec(self) -> float:
        """Media duration: the frame count the renderer produces."""
        return self.total_frames / self.fps

    def track(self, name: str) -> tuple[tuple[TimelineInterval, dict], ...]:
        """(interval, payload) pairs on one track, in schedule order."""
        return tuple(
            (interval, self.payloads.get(interval.interval_id, {}))
            for interval in self.schedule.intervals(name))

    def narration_complete(self, expected_ids: list[str]) -> bool:
        return self.schedule.narration_complete(expected_ids)

    def _content_dict(self) -> dict[str, Any]:
        """The schedule content the checksum covers (everything
        except the version + checksum themselves)."""
        return {
            "fps": self.fps,
            "sample_rate": self.sample_rate,
            "tail_sec": self.tail_sec,
            "total_frames": self.total_frames,
            "total_samples": self.total_samples,
            "total_sec": self.total_sec,
            "intervals": [
                {
                    "track": i.track,
                    "interval_id": i.interval_id,
                    "start_frame": i.start_frame,
                    "end_frame": i.end_frame,
                    "start_sample": i.start_sample,
                    "end_sample": i.end_sample,
                    "start_sec": i.start_sec,
                    "end_sec": i.end_sec,
                    "payload": self.payloads.get(i.interval_id, {}),
                }
                for i in self.schedule.intervals()],
        }

    @property
    def checksum(self) -> str:
        """SHA-256 over the canonical JSON of the frozen content.
        Identical schedules hash identically; any moved, added or
        removed interval changes the hash."""
        canonical = json.dumps(
            self._content_dict(), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        blob = self._content_dict()
        blob["timeline_version"] = self.version
        blob["checksum"] = self.checksum
        return blob


class UnifiedTimelineBuilder:
    """Mutable until freeze(). Appends validate immediately."""

    def __init__(self, *, fps: int = FPS, sample_rate: int = SAMPLE_RATE,
                 tail_sec: float = TAIL_SEC, version: int = 1) -> None:
        self._fps = fps
        self._sample_rate = sample_rate
        self._tail_sec = tail_sec
        self._version = version
        self._schedule = FrozenSchedule()
        self._payloads: dict[str, dict[str, Any]] = {}
        self._seen_ids: set[str] = set()
        self._shot_end_frame = 0
        self._shot_count = 0
        self._frozen = False

    # -- conversion ---------------------------------------------------

    def _interval(self, track: str, interval_id: str, start_sec: float,
                  end_sec: float) -> TimelineInterval:
        return TimelineInterval(
            track=track, interval_id=interval_id,
            start_frame=sec_to_frame(start_sec, self._fps),
            end_frame=sec_to_frame(end_sec, self._fps),
            start_sample=sec_to_sample(start_sec, self._sample_rate),
            end_sample=sec_to_sample(end_sec, self._sample_rate),
            fps=self._fps, sample_rate=self._sample_rate)

    def _add(self, interval: TimelineInterval,
             payload: dict[str, Any]) -> None:
        if self._frozen:
            raise SchedulingConflict(
                "schedule is frozen; rebuild explicitly")
        if interval.interval_id in self._seen_ids:
            raise SchedulingConflict(
                f"duplicate interval id {interval.interval_id!r}")
        if interval.track in _EXCLUSIVE_TRACKS:
            # Spoken lines share one voice: narration and dialogue
            # overlap checks span BOTH speech tracks.
            others = list(self._schedule.intervals(interval.track))
            if interval.track in ("narration", "dialogue"):
                other_track = ("dialogue" if interval.track == "narration"
                               else "narration")
                others += list(self._schedule.intervals(other_track))
            for other in others:
                if (interval.start_frame < other.end_frame
                        and other.start_frame < interval.end_frame):
                    raise SchedulingConflict(
                        f"{interval.track} overlap: "
                        f"{interval.interval_id} "
                        f"[{interval.start_frame}, {interval.end_frame}) "
                        f"vs {other.interval_id} "
                        f"[{other.start_frame}, {other.end_frame})")
        self._seen_ids.add(interval.interval_id)
        self._payloads[interval.interval_id] = dict(payload)
        self._schedule.add(interval)

    # -- track appends ------------------------------------------------

    def add_shot(self, shot_id: str, start_sec: float, end_sec: float,
                 payload: dict[str, Any] | None = None) -> None:
        """Shots must tile contiguously: each shot starts exactly
        where the previous one ended, in frame space."""
        interval = self._interval("shots", f"shot:{shot_id}",
                                  start_sec, end_sec)
        if interval.start_frame != self._shot_end_frame:
            raise SchedulingConflict(
                f"shot {shot_id} starts at frame "
                f"{interval.start_frame}, expected "
                f"{self._shot_end_frame} (shots must tile)")
        self._shot_end_frame = interval.end_frame
        self._shot_count += 1
        self._add(interval, payload or {})

    def add_line(self, line_index: int, kind: str, start_sec: float,
                 end_sec: float, payload: dict[str, Any] | None = None
                 ) -> None:
        track = "narration" if kind == "narration" else "dialogue"
        self._add(self._interval(track, f"line:{line_index}",
                                 start_sec, end_sec),
                  payload or {})

    def add_action(self, action_id: str, start_sec: float,
                   end_sec: float, payload: dict[str, Any] | None = None
                   ) -> None:
        self._add(self._interval("actions", f"action:{action_id}",
                                 start_sec, end_sec),
                  payload or {})

    def add_prop_interaction(self, action_id: str, start_sec: float,
                             end_sec: float,
                             payload: dict[str, Any] | None = None
                             ) -> None:
        self._add(self._interval(
            "prop_interactions", f"prop:{action_id}",
            start_sec, end_sec), payload or {})

    def add_expression(self, expression_id: str, start_sec: float,
                       end_sec: float,
                       payload: dict[str, Any] | None = None) -> None:
        self._add(self._interval("expressions", f"expr:{expression_id}",
                                 start_sec, end_sec),
                  payload or {})

    def add_sfx(self, segment_id: str, start_sec: float, end_sec: float,
                payload: dict[str, Any] | None = None) -> None:
        self._add(self._interval("sfx", f"sfx:{segment_id}",
                                 start_sec, end_sec),
                  payload or {})

    def add_bed(self, bed_id: str, track: str, start_sec: float,
                end_sec: float, payload: dict[str, Any] | None = None
                ) -> None:
        if track not in ("ambience", "music"):
            raise SchedulingConflict(
                f"bed track must be ambience/music, got {track!r}")
        self._add(self._interval(track, f"bed:{bed_id}",
                                 start_sec, end_sec),
                  payload or {})

    def add_subtitle(self, window_id: str, start_sec: float,
                     end_sec: float, payload: dict[str, Any] | None = None
                     ) -> None:
        self._add(self._interval("subtitles", f"sub:{window_id}",
                                 start_sec, end_sec),
                  payload or {})

    def add_camera_cut(self, shot_id: str, at_sec: float,
                       payload: dict[str, Any] | None = None) -> None:
        """A cut is the first frame of the new shot (1-frame interval;
        TimelineInterval requires end > start)."""
        frame = sec_to_frame(at_sec, self._fps)
        interval = TimelineInterval(
            track="camera_cuts", interval_id=f"cut:{shot_id}",
            start_frame=frame, end_frame=frame + 1,
            start_sample=sec_to_sample(at_sec, self._sample_rate),
            end_sample=sec_to_sample(at_sec, self._sample_rate) + 1,
            fps=self._fps, sample_rate=self._sample_rate)
        self._add(interval, payload or {})

    def add_end_card(self, start_sec: float, end_sec: float,
                     payload: dict[str, Any] | None = None) -> None:
        self._add(self._interval("end_cards", "end_card",
                                 start_sec, end_sec),
                  payload or {})

    # -- draft totals (before freeze) ---------------------------------

    @property
    def draft_total_sec(self) -> float:
        """Shots + tail, from the shot track as built so far. The
        mixer uses this: the same value stage 8 computed as
        sum(shot durations) + 0.5, now from one place."""
        return (self._shot_end_frame / self._fps) + self._tail_sec

    # -- freeze --------------------------------------------------------

    def freeze(self, *, expected_line_ids: list[str] | None = None
               ) -> UnifiedTimeline:
        if self._shot_count == 0:
            raise SchedulingConflict("cannot freeze: no shots")
        if expected_line_ids is not None:
            if not self._schedule.narration_complete(expected_line_ids):
                raise SchedulingConflict(
                    "narration incomplete: every spoken line must "
                    "appear exactly once")
        tail_frames = sec_to_frame(self._tail_sec, self._fps)
        total_frames = self._shot_end_frame + tail_frames
        total_samples = sec_to_sample(
            total_frames / self._fps, self._sample_rate)
        self._schedule.freeze()
        self._frozen = True
        return UnifiedTimeline(
            schedule=self._schedule, payloads=dict(self._payloads),
            total_frames=total_frames, total_samples=total_samples,
            fps=self._fps, sample_rate=self._sample_rate,
            tail_sec=self._tail_sec, version=self._version)


def seed_builder(builder: UnifiedTimelineBuilder, shots: list[dict],
               timeline_entries: list[dict],
               compiled_events: list[dict] | None = None
               ) -> list[str]:
    """Add the shot, line, action and prop-interaction tracks from the
    measured job artifacts. Returns the expected line ids for the
    freeze-time narration-completeness check. The caller adds SFX,
    beds and subtitles, then freezes."""
    clock = 0.0
    for index, shot in enumerate(shots):
        duration = float(shot.get("duration") or 0.0)
        shot_id = shot.get("shot_id") or shot.get("id") or f"shot_{index}"
        builder.add_shot(
            shot_id, clock, clock + duration,
            {"index": index, "scene": shot.get("scene"),
             "kind": shot.get("kind"),
             "shot_type": shot.get("shot_type")})
        if index > 0:
            builder.add_camera_cut(
                shot_id, clock,
                {"from_index": index - 1, "to_index": index})
        if shot.get("kind") == "end_card":
            builder.add_end_card(clock, clock + duration,
                                 {"shot_index": index})
        clock += duration
    expected: list[str] = []
    for entry in timeline_entries:
        builder.add_line(
            entry["line_index"], entry.get("kind", "dialogue"),
            float(entry["start"]), float(entry["end"]),
            {"speaker": entry.get("speaker"),
             "text": entry.get("text"),
             "duration": entry.get("duration")})
        expected.append(f"line:{entry['line_index']}")
    for event in compiled_events or []:
        start = float(event.get("start_time") or 0.0)
        end = float(event.get("end_time") or 0.0)
        if end <= start:
            continue
        payload = {"verb": event.get("action_type"),
                   "actor_id": event.get("actor_id"),
                   "shot_id": event.get("shot_id"),
                   "prop_id": event.get("prop_id")}
        builder.add_action(event["action_id"], start, end, payload)
        if event.get("prop_id"):
            builder.add_prop_interaction(event["action_id"], start, end,
                                         payload)
    return expected


def build_unified_timeline(shots: list[dict],
                           timeline_entries: list[dict],
                           compiled_events: list[dict] | None = None,
                           *, tail_sec: float = TAIL_SEC,
                           version: int = 1,
                           ) -> UnifiedTimeline:
    """One-shot construction from the measured job artifacts: the shot
    plan (re-timed with real TTS durations), the line entries (starts
    assigned by _assign_line_starts), and the compiled events (real
    spans from stage 7a). SFX/subtitle tracks are added by the caller
    through the builder when they exist."""
    builder = UnifiedTimelineBuilder(tail_sec=tail_sec, version=version)
    expected = seed_builder(builder, shots, timeline_entries,
                            compiled_events)
    return builder.freeze(expected_line_ids=expected)


# --- Timeline references (sprint section 8) ------------------------------

# Dict-shaped job artifacts that must reference the frozen schedule.
# Written by the pipeline (stamp_timeline_refs) and verified by the
# MP4 verifier (check_timeline_refs). List-shaped artifacts are
# excluded by shape (see the module docstring).
STAMPED_ARTIFACTS = (
    "scene_package.json",
    "timeline.json",
    "action_events.json",
    "scene_graph.json",
    "audio_plan.json",
    "world25d_spec.json",
    "camera_accounting.json",
    "renderer_info.json",
    "frames/motion_report.json",
    "foley_sync.json",
    "coverage_audit.json",
    "action_trace.json",
    "isolation_audit.json",
    "contact_audit.json",
    "mp4_verification.json",
)

# Artifacts that exist before the freeze (stamped in the first pass,
# right after freezing) vs after the render (second pass).
PRE_FREEZE_ARTIFACTS = (
    "scene_package.json",
    "timeline.json",
    "action_events.json",
    "scene_graph.json",
    "audio_plan.json",
    "world25d_spec.json",
)
POST_RENDER_ARTIFACTS = (
    "camera_accounting.json",
    "renderer_info.json",
    "frames/motion_report.json",
    "foley_sync.json",
)


def timeline_ref(unified) -> dict[str, Any]:
    """The reference downstream artifacts carry: version + checksum.

    Accepts a UnifiedTimeline or its to_dict()/JSON form."""
    if isinstance(unified, dict):
        return {
            "timeline_version": unified.get("timeline_version"),
            "timeline_checksum": unified.get("checksum"),
        }
    return {
        "timeline_version": unified.version,
        "timeline_checksum": unified.checksum,
    }


def stamp_timeline_refs(job_dir, ref: dict,
                        names=STAMPED_ARTIFACTS) -> dict[str, str]:
    """Write ``{"timeline_ref": ref}`` into each named dict-shaped
    JSON artifact. Returns one outcome per name: "stamped",
    "missing" (artifact absent -- not an error here; the caller
    stamps in passes as artifacts appear), "skipped_non_dict", or
    "error: ...". Never raises on an individual file: a stamp
    problem surfaces at MP4 verification as a missing reference."""
    job_dir = Path(job_dir)
    outcomes: dict[str, str] = {}
    for name in names:
        path = job_dir / name
        if not path.exists():
            outcomes[name] = "missing"
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            outcomes[name] = f"error: {exc}"
            continue
        if not isinstance(blob, dict):
            outcomes[name] = "skipped_non_dict"
            continue
        blob["timeline_ref"] = dict(ref)
        try:
            path.write_text(json.dumps(blob, indent=2,
                                       ensure_ascii=False),
                            encoding="utf-8")
        except OSError as exc:
            outcomes[name] = f"error: {exc}"
            continue
        outcomes[name] = "stamped"
    return outcomes


def check_timeline_refs(job_dir, unified_dict: dict,
                        names=STAMPED_ARTIFACTS) -> dict:
    """Verify every EXISTING stamped artifact references this frozen
    schedule. Returns {"skipped", "reason", "failures", "checked"}.

    Skipped (not failed) when the frozen schedule predates checksums
    -- old job dirs cannot gain references retroactively. A missing
    artifact is not a failure here (absence is the coverage audit's
    concern); a present artifact with a missing or mismatched
    reference fails."""
    job_dir = Path(job_dir)
    expected = timeline_ref(unified_dict)
    if expected["timeline_checksum"] is None:
        return {"skipped": True,
                "reason": "unified timeline predates checksums",
                "failures": [], "checked": []}
    failures = []
    checked = []
    for name in names:
        path = job_dir / name
        if not path.exists():
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(blob, dict):
            continue
        checked.append(name)
        ref = blob.get("timeline_ref")
        if ref is None:
            failures.append(f"{name}: missing timeline_ref")
        elif ref != expected:
            failures.append(
                f"{name}: timeline_ref mismatch (got {ref}, "
                f"expected {expected})")
    return {"skipped": False, "reason": "",
            "failures": failures, "checked": checked}
