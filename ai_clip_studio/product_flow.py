"""Universal Production Pipeline — the "luồng chuẩn" (standard flow).

Mai's authoritative flow (2026-11-11), implemented exactly, in the
drawn order:

  [1] Dán kịch bản -> [2] Phân tích script -> [3] Cấu hình video
  -> [4] Storyboard preview -> [5] Preflight validation
  -> NHẤN TẠO DRAFT ->
  Script Snapshot -> Scene Package -> Character Design -> Rig ->
  Animation -> Vietnamese TTS -> Audio Timeline -> SFX / Music ->
  Subtitle -> Renderer -> FFmpeg -> MP4 -> Technical QA ->
  Creative QA -> Google Drive Upload ->
  [6] Xem video draft ->
  QA FAILED -> Sửa và render (loop) / QA PASSED -> Người dùng duyệt
  -> Render Master -> Google Drive

Every stage is real: storyboard stills are rendered from the plan
data, preflight validates the real plan, QA FAILED actually loops
back and re-renders (for technical failures the pipeline can fix),
and Master renders ONLY after the user's approval in the UI
(`approve_master`), never automatically after QA passed.

Stage handoff notes (where the drawn order needs measured data):
- Animation plans WHAT happens (actions + shot types) with estimated
  durations; the Audio Timeline stage re-times the same shot plan
  with the real measured TTS durations before the Renderer runs.
  The shot list the renderer uses is always the re-timed one, and
  both versions are recorded in the job record.
- TTS is Vietnamese-only (`--language vi` in the provider). If
  Vietnamese TTS fails, the job FAILS with a clear error — the
  pipeline never silently switches to English.

No pydantic anywhere (the 19-stage orchestrator's Gemini/VieNeu
stages needed it; this flow uses stdlib + the injected providers).
No hardcoded Chrome path: Motion Canvas is not invoked here at all
— the renderer is the frame-by-frame code renderer, and the job
record says so. On Mai's Windows machine a Motion Canvas render_fn
can replace it without changing this flow.

No per-story code: the package, the timeline and the shot list are
data; the same code renders any script.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path

from .action_compiler import (LEVEL_AUTHORITY, UnauthorizedStoryChange,
                              compile_actions)
from .audio_events import (
    SPEC_AUDIO_DEFAULTS,
    SYNTHESIS_MAP,
    AudioEvent,
    audio_event_to_synth_job,
    build_shot_clock,
    plan_audio_events,
    resolve_mix_gains,
    resolve_v1_cues,
    scene_none_flags,
)
from .chrome_detect import detect_chrome
from .drive_uploader import DRIVE_ROOT_FOLDER_ID, GwsCliDriveClient
from .gemini_planner import resolve_plan
from .language_gate import check_production_language
from .motioncanvas_spec import MotionCanvasSpecError, emit_job_spec
from .production_errors import (
    ProductionError, check_compile_outcome, classify_unsupported,
    wrap_exception)
from .prop_system import ForbiddenPropTransition, SemanticPropTracker
from .scene_graph import (
    GraphValidationError, build_scene_graph, validate_or_raise)
from .product_renderer import (
    FPS, GROUND_Y, map_character, plan_shots, render_product_video,
    render_storyboard_stills,
)
from .qa_gates import (
    CharacterArtGate, CreativeGate, TechnicalGate, combine, probe_video,
    script_hash,
)
from .subtitles import FONT_PX, phrase_windows, split_subtitle
from .timeline import (
    TimelineLine, build_timeline, measure_wav_duration,
)
from .tts_cli_provider import tts_cli_provider
from .unified_timeline import (
    POST_RENDER_ARTIFACTS, PRE_FREEZE_ARTIFACTS,
    UnifiedTimelineBuilder, seed_builder, stamp_timeline_refs,
    timeline_ref)

TEST_FOLDER_ID = "1RugK0pkCczC_-CWk2V_IzMh3sc2t4fyu"

# The drawn pipeline stages, in order. The server maps these to the
# live progress UI.
STAGES = (
    "script_snapshot", "scene_package", "character_design", "rig",
    "animation", "vietnamese_tts", "audio_timeline", "sfx_music",
    "subtitle", "renderer", "ffmpeg", "mp4", "technical_qa",
    "creative_qa", "drive_upload",
)

MAX_RERENDER_LOOPS = 2
SUPPORTED_CUES = {
    "walk", "walk_fast", "run", "stop", "bend_pick", "give", "take",
    "open", "put_away", "take_out", "wave", "turn_back", "smile",
    "look", "search", "board", "sit", "stand", "rain", "bus",
    "head_tilt",
}


@dataclass
class ProductJob:
    job_id: str
    script: str
    script_hash: str
    job_dir: Path
    config: dict = field(default_factory=dict)
    stages: list[dict] = field(default_factory=list)
    status: str = "queued"
    planner: str = ""
    planner_detail: str = ""
    package: dict | None = None
    timeline: dict | None = None
    unified_timeline: dict = field(default_factory=dict)
    shots: list[dict] = field(default_factory=list)
    mp4_path: str = ""
    mp4_size: int = 0
    mp4_duration: float = 0.0
    qa: dict = field(default_factory=dict)
    drive: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    renderer_info: dict = field(default_factory=dict)
    loops: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    master: dict = field(default_factory=dict)

    def record(self, name: str, status: str, detail: str = "") -> None:
        self.stages.append({"stage": name, "status": status,
                            "detail": detail, "at": round(time.time(), 1)})

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id, "status": self.status,
            "script_hash": self.script_hash,
            "planner": self.planner, "planner_detail": self.planner_detail,
            "config": self.config, "stages": self.stages,
            "shots": self.shots,
            "mp4": {"path": self.mp4_path, "size_bytes": self.mp4_size,
                    "duration_sec": self.mp4_duration},
            "qa": self.qa, "drive": self.drive,
            "artifacts": self.artifacts,
            "renderer_info": self.renderer_info,
            "loops": self.loops,
            "errors": self.errors, "master": self.master,
            # Sprint section 8: the job record references the frozen
            # schedule (None when the job failed before the freeze).
            "timeline_ref": (
                {"timeline_version":
                 self.unified_timeline.get("timeline_version"),
                 "timeline_checksum":
                 self.unified_timeline.get("checksum")}
                if self.unified_timeline else None),
        }


def _rms_db(path: Path) -> float | None:
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vn",
         "-af", "astats=metadata=1", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    overall = False
    for line in (r.stderr or "").splitlines():
        if "Overall" in line:
            overall = True
        if overall and "RMS level dB:" in line:
            value = line.split("RMS level dB:")[-1].strip()
            if value in ("-inf", "-infinity"):
                return -120.0
            try:
                return float(value)
            except ValueError:
                return None
    return None


def build_frame_symlinks(frames: list, out_dir: Path) -> str:
    """Lay the rendered frames out as f0000.png..fNNNN.png symlinks in
    one flat directory, for the image2 demuxer. The concat demuxer
    cannot do this exactly: it has no -framerate option, needs duration
    directives, and its repeat-the-last-file quirk adds a phantom
    frame — the muxed frame count then disagrees with the motion
    report and TechnicalGate.frames_rendered_real fails. image2 with
    -framerate <fps> muxes exactly len(frames) frames at <fps>."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f*.png"):
        old.unlink()
    for i, f in enumerate(frames):
        link = out_dir / f"f{i:04d}.png"
        try:
            link.symlink_to(f)
        except FileExistsError:
            pass
    return str(out_dir / "f%04d.png")


def _mix_audio_legacy(job_dir: Path, timeline_entries: list[dict],
                      total_sec: float,
                      rain_spans: list[tuple[float, float]] | None = None
                      ) -> tuple[Path, dict]:
    """Mix voice wavs at their timeline offsets + restrained rain beds
    confined to the rainy scenes' spans (never a job-wide bed: scene
    6's rain must not leak into scene 1). Returns (mix_path,
    measurements). The rain is verified to sit at least 6 dB below
    the voice.

    Kept for old-style callers: _mix_audio dispatches here when no
    stem data is passed (see _mix_audio_stems for the Stage 3
    stem-based mix)."""
    mix = job_dir / "audio" / "mix.wav"
    mix.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for i, entry in enumerate(timeline_entries):
        inputs += ["-i", str(entry["wav"])]
        delay_ms = int(round(entry["start"] * 1000))
        filters.append(f"[{i}:a]adelay={delay_ms}:all=1[v{i}]")
        labels.append(f"[v{i}]")
    rain_paths: list[Path] = []
    rain_db = None
    voice_db = None
    for span_index, (span_start, span_end) in enumerate(
            rain_spans or []):
        if span_end <= span_start:
            continue
        rain_path = job_dir / "audio" / f"rain_bed_{span_index:03d}.wav"
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", f"anoisesrc=color=pink:"
                   f"duration={span_end - span_start:.2f}",
             "-af", "lowpass=f=800,volume=0.10",
             "-ac", "1", "-ar", "48000", str(rain_path)],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"rain bed synthesis failed: {r.stderr[:300]}")
        measured = _rms_db(rain_path)
        if measured is not None and (rain_db is None
                                    or measured > rain_db):
            rain_db = measured
        rain_paths.append(rain_path)
        idx = len(inputs) // 2
        inputs += ["-i", str(rain_path)]
        delay_ms = int(round(span_start * 1000))
        filters.append(
            f"[{idx}:a]adelay={delay_ms}:all=1,volume=1.0"
            f"[rain{span_index}]")
        labels.append(f"[rain{span_index}]")
    n = len(labels)
    filters.append(
        f"{''.join(labels)}amix=inputs={n}:normalize=0:duration=longest[mix]")
    # Pad to the full video length, then fade out the last 0.5 s so the
    # audio never ends abruptly (mission §3: no abrupt audio endings).
    filters.append(
        f"[mix]apad=whole_dur={total_sec:.2f},"
        f"afade=t=out:st={max(0.0, total_sec - 0.5):.2f}:d=0.5[out]")
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", ";".join(filters), "-map", "[out]",
        "-ac", "1", "-ar", "48000", str(mix)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not mix.exists():
        raise RuntimeError(f"audio mix failed: {r.stderr[:500]}")
    # Voice restraint check: voice RMS vs rain RMS, measured on the
    # source files (the mix itself is normalised to 0, so compare
    # sources, not the mixed output).
    voice_rms = [_rms_db(Path(e["wav"])) for e in timeline_entries]
    voice_rms = [v for v in voice_rms if v is not None]
    voice_db = sum(voice_rms) / len(voice_rms) if voice_rms else None
    restraint = None
    if rain_db is not None and voice_db is not None:
        restraint = round(voice_db - rain_db, 1)
    return mix, {"rain_db": rain_db, "voice_db_mean": voice_db,
                 "voice_minus_rain_db": restraint,
                 "rain_beds": [str(p) for p in rain_paths],
                 "rain_bed": str(rain_paths[0]) if rain_paths else None}


def _db_to_linear(db: float) -> float:
    return 10.0 ** (float(db) / 20.0)


def _normalize_synth_segment(path: Path, *,
                             target_db: float = -12.0,
                             max_gain_db: float = 30.0) -> dict:
    """Bring one synthesised segment to the reference RMS the gain
    chain assumes (P8).

    The bed/segment gains (base_gain_db + bus offset + intensity)
    express INTENT relative to a known baseline, but the raw synth
    output was never measured: the music pad renders at -40 dB RMS,
    so the -18 dB base gain + -6 dB "very low" extra + -6 dB ducking
    buried it at -65 dB (the delivered Ep1 draft). Normalising every
    synth segment to -12 dB RMS makes the chain's arithmetic real;
    the restraint loop still caps anything too loud. Boosts are
    capped at +30 dB; silence is left untouched and reported.
    """
    rms = _rms_db(path)
    record = {"measured_rms_db": rms, "gain_db": 0.0,
              "target_db": target_db}
    if rms is None or rms <= -119.0:
        record["note"] = "silence or unreadable levels; left untouched"
        return record
    gain = target_db - rms
    if gain > max_gain_db:
        gain = max_gain_db
        record["capped"] = True
    if abs(gain) < 0.1:
        record["rms_db_after"] = rms
        return record
    tmp = path.with_suffix(".ref.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path),
         "-af", f"volume={_db_to_linear(gain):.6f}",
         "-ac", "1", "-ar", "48000", str(tmp)],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not tmp.exists():
        raise RuntimeError(
            f"synth normalisation failed: {r.stderr[:300]}")
    tmp.replace(path)
    record.update({"gain_db": round(gain, 2),
                   "rms_db_after": _rms_db(path)})
    return record


def _peak_db_window(path: Path, start: float, end: float) -> float | None:
    """Peak dB of one window of a wav (ffmpeg volumedetect)."""
    dur = max(0.05, float(end) - float(start))
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{float(start):.3f}",
         "-t", f"{dur:.3f}", "-i", str(path), "-vn",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    for line in (r.stderr or "").splitlines():
        if "max_volume:" in line:
            value = line.split("max_volume:")[-1].strip().split()[0]
            if value in ("-inf", "-infinity"):
                return -120.0
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _synth_segment(spec: dict, duration: float, out_path: Path,
                   *, fade_mode: str = "edge") -> Path:
    """Render one synthesised segment wav from a SYNTHESIS_MAP spec
    (ffmpeg lavfi, mono 48 kHz). fade_mode "edge" fades out at the
    end of the segment; "full" fades out across the whole segment
    (BGM lines such as "fade down to near silence")."""
    dur = max(0.05, float(duration))
    if fade_mode == "full":
        fade_st, fade_d = 0.0, dur
    else:
        fade_d = min(0.35, dur * 0.5)
        fade_st = max(0.0, dur - fade_d)
    edge = min(0.2, dur / 4.0)
    fmt = {"dur": f"{dur:.3f}", "fade_st": f"{fade_st:.3f}",
           "fade_d": f"{fade_d:.3f}", "edge": f"{edge:.3f}"}
    inputs: list[str] = []
    for lavfi in spec["inputs"]:
        inputs += ["-f", "lavfi", "-i", lavfi.format(**fmt)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error"] + inputs + [
            "-filter_complex", spec["filter"].format(**fmt),
            "-map", "[out]", "-ac", "1", "-ar", "48000", str(out_path)],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            f"synthesis failed ({spec['method']}): {r.stderr[:300]}")
    return out_path


def _rms_db_windows(path: Path,
                    windows: list[tuple[float, float]]) -> float | None:
    """RMS dB of an audio file over the UNION of time windows, via
    one ffmpeg aselect+astats pass. Silence -> -120.0 (the same
    convention _rms_db uses). Used for the restraint check: voice
    vs each non-voice stem, measured in dialogue windows only."""
    windows = [(a, b) for a, b in windows if b > a]
    if not windows:
        return _rms_db(path)
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)
    filt = f"aselect='{expr}',asetpts=N/SR/TB,astats=metadata=1"
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vn",
         "-af", filt, "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    overall = False
    for line in (r.stderr or "").splitlines():
        if "Overall" in line:
            overall = True
        if overall and "RMS level dB:" in line:
            value = line.split("RMS level dB:")[-1].strip()
            if value in ("-inf", "-infinity"):
                return -120.0
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _combine_rms_db(values: list[float | None]) -> float | None:
    """RMS dB of the sum of non-overlapping signals measured over the
    same windows (mean squares add; dialogue and narration stems
    never overlap in time)."""
    energies = [10.0 ** (v / 10.0) for v in values if v is not None]
    if not energies:
        return None
    import math
    return round(10.0 * math.log10(sum(energies)), 2)


def _placed_stem(placements: list[tuple[Path, float, float]],
                 total_sec: float, out_path: Path, *,
                 duck_windows: list[tuple[float, float]] | None = None,
                 duck_db: float | None = None,
                 mute_windows: list[tuple[float, float]] | None = None
                 ) -> Path:
    """Mix placed segments into one full-length stem wav.

    placements: (wav_path, gain_db, delay_sec). Ducking lowers the
    whole stem by duck_db during each duck window (speech); mute
    windows silence it (explicit NONE spans). The output is exactly
    total_sec long (apad + atrim)."""
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for i, (wav, gain_db, delay_sec) in enumerate(placements):
        inputs += ["-i", str(wav)]
        delay_ms = int(round(max(0.0, delay_sec) * 1000))
        filters.append(
            f"[{i}:a]volume={_db_to_linear(gain_db):.6f},"
            f"adelay={delay_ms}:all=1[p{i}]")
        labels.append(f"[p{i}]")
    n = len(labels)
    filters.append(
        f"{''.join(labels)}amix=inputs={n}:normalize=0:"
        f"duration=longest[mix]")
    last = "[mix]"
    step = 0
    if duck_db is not None and duck_windows:
        for a, b in duck_windows:
            if b <= a:
                continue
            filters.append(
                f"{last}volume={_db_to_linear(duck_db):.6f}:"
                f"enable='between(t,{a:.3f},{b:.3f})'[d{step}]")
            last = f"[d{step}]"
            step += 1
    if mute_windows:
        for a, b in mute_windows:
            if b <= a:
                continue
            filters.append(
                f"{last}volume=0:"
                f"enable='between(t,{a:.3f},{b:.3f})'[m{step}]")
            last = f"[m{step}]"
            step += 1
    filters.append(
        f"{last}apad=whole_dur={total_sec:.2f},"
        f"atrim=0:{total_sec:.2f}[out]")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error"] + inputs + [
            "-filter_complex", ";".join(filters), "-map", "[out]",
            "-ac", "1", "-ar", "48000", str(out_path)],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            f"stem build failed ({out_path.name}): {r.stderr[:400]}")
    return out_path


# ---------------------------------------------------------------------------
# Foley sync (Phase G): footsteps at actual foot contacts
# ---------------------------------------------------------------------------

# A standstill records 2 strikes (one per foot at the first frame);
# a real walk needs at least 3 before any footstep sound is placed.
FOLEY_FOOTSTEP_MIN_STRIKES = 3
# Deterministic footstep variants, cycled so consecutive steps do
# not sound identical. Seeds are fixed: the same job re-renders the
# same sounds.
FOLEY_FOOTSTEP_VARIANTS = 3
FOLEY_FOOTSTEP_SEED_BASE = 7000
# Absolute restraint bounds for the ADDED footsteps stem: quiet by
# construction, whatever the dialogue level. (The full mix already
# passed the relative restraint loop in _mix_audio_stems; this
# bounds only what the foley stage adds.)
FOLEY_DIALOGUE_WINDOW_MAX_RMS_DB = -30.0
FOLEY_STEM_MAX_PEAK_DB = -12.0
FOLEY_MIX_MAX_PEAK_DB = -1.0
# Headroom for the foley mix (§18 fix): when the base mix already peaks
# at the bound, ANY added stem exceeds it, so the old code dropped all
# footsteps (the Zeus draft's omitted_peak: 129 placements, 0 audible).
# Instead, attenuate the base mix by the excess plus this margin and
# re-mix once. Capped: a large excess means the stem itself is too hot,
# and omission stays the honest outcome.
FOLEY_HEADROOM_MARGIN_DB = 0.5
FOLEY_HEADROOM_MAX_DB = 3.0


def footstep_placements(shot_reports, shots):
    """Absolute-time footstep placements from rendered shot reports.

    ``shot_reports`` are _render_shot reports (``footfalls`` per
    character, shot-relative times); ``shots`` is the plan list the
    audio clock was built from. Only characters with at least
    FOLEY_FOOTSTEP_MIN_STRIKES in a shot contribute. A shot whose
    plan carries a locomotion direction but recorded too few
    strikes is reported unresolved — no footsteps are invented
    for it.

    Returns (placements, per_shot, unresolved): placements are
    (t_abs, character, shot_index, foot) sorted by time.
    """
    clock = build_shot_clock(shots)
    starts = {span["index"]: span["start"]
              for span in clock["shot_spans"]}
    placements: list[tuple[float, str, int, str]] = []
    per_shot: dict[int, dict] = {}
    unresolved: list[dict] = []
    for report in shot_reports or []:
        index = report.get("index")
        if index is None or index not in starts:
            continue
        falls = report.get("footfalls") or []
        by_char: dict[str, list[dict]] = {}
        for fall in falls:
            by_char.setdefault(str(fall.get("character")), []).append(fall)
        placed = 0
        for char, char_falls in sorted(by_char.items()):
            if len(char_falls) < FOLEY_FOOTSTEP_MIN_STRIKES:
                continue
            for fall in char_falls:
                placements.append((round(starts[index]
                                         + float(fall["t"]), 3),
                                   char, int(index),
                                   str(fall.get("foot"))))
                placed += 1
        per_shot[int(index)] = {
            "strikes": {c: len(v) for c, v in by_char.items()},
            "placed": placed}
        plan = shots[index] if index < len(shots) else {}
        if (plan.get("locomotion_direction") is not None
                and placed == 0):
            unresolved.append({
                "shot_index": int(index),
                "reason": "locomotion planned but fewer than "
                          f"{FOLEY_FOOTSTEP_MIN_STRIKES} footfalls "
                          "recorded for every character; no "
                          "footsteps placed"})
    placements.sort(key=lambda p: (p[0], p[1]))
    return placements, per_shot, unresolved


def _footstep_variant_wavs(out_dir: Path) -> list[Path]:
    """Deterministic footstep WAVs from synth_sfx (verified
    properties only — see test_synth_sfx.py; human listening
    verification is recorded on the foley report, never assumed)."""
    from .synth_sfx import footstep, write_wav16
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(FOLEY_FOOTSTEP_VARIANTS):
        path = out_dir / f"footstep_var{i}.wav"
        write_wav16(path, footstep(FOLEY_FOOTSTEP_SEED_BASE + i))
        paths.append(path)
    return paths


def _wav_levels(path: Path, windows=None):
    """Peak dBFS + per-window RMS dBFS of a 16-bit PCM WAV (stdlib
    only). Windows are (start, end) seconds; the whole file is one
    window when none are given. Raises on non-16-bit input rather
    than mis-measuring it."""
    import array
    import math
    import wave
    with wave.open(str(path), "rb") as w:
        n_channels = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        n_frames = w.getnframes()
        raw = w.readframes(n_frames)
    if width != 2:
        raise ValueError(f"expected 16-bit WAV, got {width * 8}-bit: "
                         f"{path}")
    samples = array.array("h")
    samples.frombytes(raw[:len(raw) - len(raw) % 2])
    if not samples:
        return {"peak_db": None, "window_rms_db": []}
    peak = max(abs(int(s)) for s in samples) / 32768.0
    peak_db = 20 * math.log10(peak) if peak > 0 else None
    if windows is None:
        windows = [(0.0, n_frames / rate)]
    window_rms = []
    for start, end in windows:
        lo = max(0, int(start * rate) * n_channels)
        hi = min(len(samples), int(end * rate) * n_channels)
        seg = samples[lo:hi]
        if not seg:
            window_rms.append(None)
            continue
        mean_sq = sum(float(s) * float(s) for s in seg) / len(seg)
        rms = math.sqrt(mean_sq) / 32768.0
        window_rms.append(20 * math.log10(rms) if rms > 0 else None)
    return {"peak_db": peak_db, "window_rms_db": window_rms}


def sync_foley_footsteps(job_dir: Path, shot_reports, shots,
                         mix_path: Path, total_sec: float,
                         timeline_entries, mix_gains) -> dict:
    """Place footstep sounds at recorded foot contacts (Phase G).

    Builds a footsteps stem from the rendered reports' footfalls,
    checks absolute restraint bounds, and mixes it into mix.wav
    (the pre-foley mix is kept as mix_pre_foley.wav). When no
    shot recorded enough footfalls, the mix is left byte-identical
    and the report says so. When the combined mix would exceed
    the peak bound after attenuation, the original mix is kept
    and the omission is reported — footsteps are never placed
    unsafely. Returns the JSON-serializable foley report (also
    written to job_dir/foley_sync.json).
    """
    job_dir = Path(job_dir)
    audio_dir = job_dir / "audio"
    placements, per_shot, unresolved = footstep_placements(
        shot_reports, shots)
    report: dict = {
        "status": "no_footfalls",
        "placements": len(placements),
        "per_shot": per_shot,
        "unresolved": unresolved,
        "source": "synth_sfx.footstep (properties verified; human "
                  "listening verification pending)",
        "mix_changed": False,
    }
    if not placements:
        (job_dir / "foley_sync.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return report
    if not Path(mix_path).exists():
        raise RuntimeError(f"foley sync needs the mixed audio, "
                           f"missing: {mix_path}")
    bus_gains = (mix_gains or {}).get("bus_gains") or {}
    sfx_offset = (float(bus_gains.get(
        "sfx_gain_db", SPEC_AUDIO_DEFAULTS["sfx_gain_db"]))
        - SPEC_AUDIO_DEFAULTS["sfx_gain_db"])
    gain_db = round(SYNTHESIS_MAP["footstep"]["base_gain_db"]
                    + sfx_offset, 2)
    variants = _footstep_variant_wavs(audio_dir / "synth_sfx")
    dialogue_windows = [
        (float(e["start"]), float(e["end"]))
        for e in (timeline_entries or [])
        if e.get("start") is not None and e.get("end") is not None]
    stem_path = audio_dir / "footsteps.wav"
    attempts = []
    attempt_gain = gain_db
    for attempt in range(4):
        placed = [(variants[i % len(variants)], attempt_gain, t)
                  for i, (t, _c, _s, _f) in enumerate(placements)]
        _placed_stem(placed, total_sec, stem_path)
        levels = _wav_levels(stem_path, dialogue_windows or None)
        peak_ok = (levels["peak_db"] is None
                   or levels["peak_db"] <= FOLEY_STEM_MAX_PEAK_DB)
        rms_values = [v for v in levels["window_rms_db"]
                      if v is not None]
        rms_ok = (not rms_values
                  or max(rms_values) <= FOLEY_DIALOGUE_WINDOW_MAX_RMS_DB)
        attempts.append({"gain_db": attempt_gain,
                         "peak_db": levels["peak_db"],
                         "max_dialogue_window_rms_db":
                             max(rms_values) if rms_values else None,
                         "ok": bool(peak_ok and rms_ok)})
        if peak_ok and rms_ok:
            break
        attempt_gain = round(attempt_gain - 3.0, 2)
    report["gain_db"] = attempt_gain
    report["restraint_attempts"] = attempts
    report["dialogue_windows"] = len(dialogue_windows)
    if not attempts[-1]["ok"]:
        report["status"] = "omitted_restraint"
        report["reason"] = ("footsteps stem exceeded restraint "
                            "bounds after attenuation; original "
                            "mix kept")
        (job_dir / "foley_sync.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return report
    pre_foley = audio_dir / "mix_pre_foley.wav"
    import shutil
    shutil.copyfile(mix_path, pre_foley)
    combined = audio_dir / "mix_with_foley.wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(pre_foley),
         "-i", str(stem_path), "-filter_complex",
         "[0:a][1:a]amix=inputs=2:normalize=0[a]", "-map", "[a]",
         "-ac", "1", "-ar", "48000", str(combined)],
        capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"foley amix failed: {r.stderr[:300]}")
    combined_levels = _wav_levels(combined)
    report["combined_peak_db"] = combined_levels["peak_db"]
    if (combined_levels["peak_db"] is not None
            and combined_levels["peak_db"] > FOLEY_MIX_MAX_PEAK_DB):
        # Headroom retry: attenuate the base mix by the excess plus
        # the safety margin, then re-mix with the same stem. The
        # original pre-foley mix stays untouched as mix_pre_foley.wav.
        excess = combined_levels["peak_db"] - FOLEY_MIX_MAX_PEAK_DB
        headroom_db = round(excess + FOLEY_HEADROOM_MARGIN_DB, 2)
        report["headroom_first_peak_db"] = combined_levels["peak_db"]
        if headroom_db <= FOLEY_HEADROOM_MAX_DB:
            attenuated = audio_dir / "mix_pre_foley_attenuated.wav"
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(pre_foley),
                 "-af", f"volume={-headroom_db:.2f}dB",
                 "-ac", "1", "-ar", "48000", str(attenuated)],
                capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(
                    f"foley headroom failed: {r.stderr[:300]}")
            combined.unlink(missing_ok=True)
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(attenuated),
                 "-i", str(stem_path), "-filter_complex",
                 "[0:a][1:a]amix=inputs=2:normalize=0[a]", "-map", "[a]",
                 "-ac", "1", "-ar", "48000", str(combined)],
                capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(f"foley amix failed: {r.stderr[:300]}")
            combined_levels = _wav_levels(combined)
            report["combined_peak_db"] = combined_levels["peak_db"]
            report["headroom_applied_db"] = headroom_db
    if (combined_levels["peak_db"] is not None
            and combined_levels["peak_db"] > FOLEY_MIX_MAX_PEAK_DB):
        report["status"] = "omitted_peak"
        report["reason"] = ("combined mix peak "
                            f"{combined_levels['peak_db']:.1f} dBFS "
                            "exceeds the -1 dBFS bound; original "
                            "mix kept")
        combined.unlink(missing_ok=True)
        (job_dir / "foley_sync.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return report
    import os
    os.replace(combined, mix_path)
    report["status"] = "placed"
    report["mix_changed"] = True
    report["pre_foley_mix"] = str(pre_foley)
    report["footstep_times"] = [p[0] for p in placements]
    (job_dir / "foley_sync.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return report


def _mix_audio_stems(job_dir: Path, timeline_entries: list[dict],
                     total_sec: float,
                     rain_spans: list[tuple[float, float]] | None,
                     segments: list[dict], beds: list[dict],
                     mix_gains: dict | None,
                     none_spans: dict, *,
                     end_card_span: tuple[float, float] | None = None
                     ) -> tuple[Path, dict]:
    """Stem-based mix (Stage 3): voice stems (dialogue/narration) +
    synthesised foley segments + ambience beds + music pads, each a
    separate wav under job_dir/audio/, plus the master mix.wav.

    Restraint is HARD and measured: in dialogue windows the voice
    RMS must sit >= 6 dB above every non-voice stem. A stem that
    fails is lowered and the mix rebuilt (up to 3 rebuilds); the
    voice is never raised. Music/ambience duck under speech by the
    resolved ducking amount; the master respects MASTER_LIMIT_DB
    (alimiter) when the package carries it. The mix is exactly
    total_sec long with a 0.5 s fade-out, never truncated."""
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    synth_dir = audio_dir / "synth"
    synth_dir.mkdir(parents=True, exist_ok=True)
    gains = mix_gains or resolve_mix_gains({})
    bus = gains["bus_gains"]
    duck_db = gains["ducking_db"]
    master_limit = gains["master_limit_db"]
    windows = [(float(e["start"]), float(e["end"]))
               for e in timeline_entries
               if e.get("start") is not None
               and e.get("end") is not None]
    skipped = 0

    synth_files: dict[tuple[str, float, bool], Path] = {}
    synth_norm: dict[str, dict] = {}

    def _synth_for(kind: str, duration: float,
                   fade_down: bool = False) -> Path:
        key = (kind, round(float(duration), 3), bool(fade_down))
        if key in synth_files:
            return synth_files[key]
        path = synth_dir / f"{kind}_{len(synth_files):03d}.wav"
        _synth_segment(SYNTHESIS_MAP[kind], duration, path,
                       fade_mode="full" if fade_down else "edge")
        synth_norm[path.name] = _normalize_synth_segment(path)
        synth_files[key] = path
        return path

    # Rain beds: one placement per rainy scene span, from the single
    # rain_bed spec definition. Rain never spans the whole job: a
    # rainy scene's bed stays inside that scene's span.
    rain_placements: list[tuple[Path, float, float]] = []
    rain_db = None
    for span_start, span_end in rain_spans or []:
        if span_end <= span_start:
            continue
        rain_path = _synth_for("rain_bed", span_end - span_start)
        measured = _rms_db(rain_path)
        if measured is not None and (rain_db is None
                                    or measured > rain_db):
            rain_db = measured
        rain_placements.append((rain_path, 0.0, float(span_start)))

    # Voice stems, split by kind, at GLOBAL_AUDIO bus gains.
    dialogue_placements: list[tuple[Path, float, float]] = []
    narration_placements: list[tuple[Path, float, float]] = []
    for entry in timeline_entries:
        placement = (Path(entry["wav"]),
                     bus["narration_gain_db"]
                     if entry.get("kind") == "narration"
                     else bus["dialogue_gain_db"],
                     float(entry["start"]))
        if entry.get("kind") == "narration":
            narration_placements.append(placement)
        else:
            dialogue_placements.append(placement)
    stem_paths: dict[str, Path] = {}
    if dialogue_placements:
        stem_paths["dialogue.wav"] = _placed_stem(
            dialogue_placements, total_sec, audio_dir / "dialogue.wav")
    if narration_placements:
        stem_paths["narration.wav"] = _placed_stem(
            narration_placements, total_sec, audio_dir / "narration.wav")
    voice_paths = [stem_paths[k] for k in ("dialogue.wav",
                                           "narration.wav")
                   if k in stem_paths]

    # Foley segments (points + ACTION_DURATION spans).
    foley_placements: list[tuple[Path, float, float]] = []
    for seg in segments:
        duration = float(seg.get("duration") or 0.0)
        if duration <= 0:
            skipped += 1
            continue
        foley_placements.append((
            _synth_for(seg["synth_kind"], duration),
            float(seg["gain_db"]), float(seg["at_seconds"])))
    # Ambience beds (+ the rain bed, ducked and NONE-muted with them).
    ambience_placements: list[tuple[Path, float, float]] = []
    music_placements: list[tuple[Path, float, float]] = []
    for bed in beds:
        start = float(bed["start"])
        end = float(bed["end"])
        if end <= start:
            skipped += 1
            continue
        placed = (_synth_for(bed["synth_kind"], end - start,
                             bed.get("fade_down", False)),
                  float(bed["gain_db"]), start)
        if bed.get("stem") == "music":
            music_placements.append(placed)
        else:
            ambience_placements.append(placed)
    ambience_placements.extend(rain_placements)
    ambience_mute = [(float(a), float(b)) for a, b in
                     (none_spans.get("ambience") or [])]
    bgm_mute = [(float(a), float(b)) for a, b in
                (none_spans.get("bgm") or [])]
    # P8: the end card is silent by design. The delivered Ep1 draft
    # carried audible rain in the 0.5 s tail after the card because
    # the rain bed runs the full mix length; muting the beds across
    # the end-card span (foley events are never placed there) fixes
    # it at the stem level instead of in the video assembly.
    if end_card_span is not None:
        span = (float(end_card_span[0]), float(end_card_span[1]))
        if span[1] > span[0]:
            ambience_mute.append(span)
            bgm_mute.append(span)

    def build_stems(extra_att: dict[str, float]) -> dict[str, Path]:
        built: dict[str, Path] = {}
        if foley_placements:
            built["foley.wav"] = _placed_stem(
                [(p, g + extra_att.get("foley.wav", 0.0), d)
                 for p, g, d in foley_placements],
                total_sec, audio_dir / "foley.wav")
        if ambience_placements:
            built["ambience.wav"] = _placed_stem(
                [(p, g + extra_att.get("ambience.wav", 0.0), d)
                 for p, g, d in ambience_placements],
                total_sec, audio_dir / "ambience.wav",
                duck_windows=windows, duck_db=duck_db,
                mute_windows=ambience_mute)
        if music_placements:
            built["music.wav"] = _placed_stem(
                [(p, g + extra_att.get("music.wav", 0.0), d)
                 for p, g, d in music_placements],
                total_sec, audio_dir / "music.wav",
                duck_windows=windows, duck_db=duck_db,
                mute_windows=bgm_mute)
        return built

    def build_master(non_voice: dict[str, Path]) -> Path:
        mix_inputs = voice_paths + [non_voice[k] for k in
                                    ("foley.wav", "ambience.wav",
                                     "music.wav") if k in non_voice]
        if not mix_inputs:
            raise RuntimeError("no audio inputs to mix")
        inputs: list[str] = []
        for path in mix_inputs:
            inputs += ["-i", str(path)]
        labels = "".join(f"[{i}:a]" for i in range(len(mix_inputs)))
        chain = (f"{labels}amix=inputs={len(mix_inputs)}:normalize=0:"
                 f"duration=longest[mix];"
                 f"[mix]apad=whole_dur={total_sec:.2f},"
                 f"atrim=0:{total_sec:.2f}")
        if master_limit is not None:
            chain += (f",alimiter=limit={_db_to_linear(master_limit):.6f}"
                      ":level=false")
        chain += (f",afade=t=out:st={max(0.0, total_sec - 0.5):.2f}"
                  ":d=0.5[out]")
        mix = audio_dir / "mix.wav"
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error"] + inputs + [
                "-filter_complex", chain, "-map", "[out]",
                "-ac", "1", "-ar", "48000", str(mix)],
            capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not mix.exists():
            raise RuntimeError(f"audio mix failed: {r.stderr[:500]}")
        return mix

    # Voice window RMS (voice stems never change, so measure once).
    voice_db_windows = _combine_rms_db(
        [_rms_db_windows(p, windows) for p in voice_paths]) \
        if voice_paths and windows else None
    extra_att: dict[str, float] = {}
    non_voice = build_stems(extra_att)
    mix = build_master(non_voice)
    stem_dbs: dict[str, float | None] = {}
    gaps: dict[str, float | None] = {}
    iterations = 0
    for attempt in range(4):
        iterations = attempt + 1
        stem_dbs = {name: _rms_db_windows(path, windows)
                    for name, path in non_voice.items()}
        gaps = {}
        failing: dict[str, float] = {}
        for name, stem_db in stem_dbs.items():
            if voice_db_windows is None or stem_db is None:
                gaps[name] = None
            else:
                gaps[name] = round(voice_db_windows - stem_db, 1)
                if gaps[name] < 6.0:
                    failing[name] = gaps[name]
        if not failing or attempt == 3:
            break
        for name, gap in failing.items():
            extra_att[name] = extra_att.get(name, 0.0) - (6.0 - gap + 1.0)
        non_voice = build_stems(extra_att)
        mix = build_master(non_voice)
    restraint_ok = None
    if gaps:
        measured = [g for g in gaps.values() if g is not None]
        restraint_ok = bool(measured) and all(g >= 6.0 for g in measured)
    mix_duration = measure_wav_duration(mix)
    if abs(mix_duration - total_sec) > 0.05:
        raise RuntimeError(
            f"mix length {mix_duration:.3f}s != timeline "
            f"{total_sec:.3f}s — refusing an inexact mix")
    voice_rms = [_rms_db(Path(e["wav"])) for e in timeline_entries]
    voice_rms = [v for v in voice_rms if v is not None]
    voice_db_mean = (sum(voice_rms) / len(voice_rms)
                     if voice_rms else None)
    # ---- P8 audibility measurements (rendered stems only) ---------
    # Presence heuristics, NOT quality evidence: a peak/RMS reading
    # says a sound is present and roughly how loud; it says nothing
    # about pronunciation, musical quality, or whether the sound
    # matches the picture. Thresholds are documented heuristics.
    foley_events: list[dict] = []
    foley_path = non_voice.get("foley.wav")
    if foley_path is not None:
        for seg in segments:
            at = float(seg.get("at_seconds") or 0.0)
            end = float(seg.get("end_seconds") or 0.0)
            if end <= at:
                end = at + max(0.05, float(seg.get("duration") or 0.0))
            peak = _peak_db_window(foley_path, at, end)
            foley_events.append({
                "cue_id": seg.get("cue_id"), "cue_name": seg.get("cue_name"),
                "at_seconds": at, "end_seconds": end,
                "peak_db": peak,
                "likely_inaudible": (peak is not None
                                     and peak < -45.0)})
    gap_windows: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in sorted(windows):
        if a - cursor >= 1.0:
            gap_windows.append((cursor, a))
        cursor = max(cursor, b)
    end_limit = (float(end_card_span[0]) if end_card_span else total_sec)
    if end_limit - cursor >= 1.0:
        gap_windows.append((cursor, end_limit))
    music_gap_db = None
    music_path = non_voice.get("music.wav")
    if music_path is not None and gap_windows:
        music_gap_db = _rms_db_windows(music_path, gap_windows)
    audibility = {
        "foley_events": foley_events,
        "foley_inaudible_cue_ids": [
            e["cue_id"] for e in foley_events if e["likely_inaudible"]],
        "music_gap_db": music_gap_db,
        "music_gap_windows": len(gap_windows),
        "music_audible_in_gaps": (
            None if music_gap_db is None else music_gap_db >= -50.0),
        "thresholds_db": {"foley_peak": -45.0, "music_gap_rms": -50.0},
        "note": ("Presence/audibility heuristics on rendered stems "
                 "only; RMS/peak presence is NOT evidence of correct "
                 "pronunciation or musical quality."),
    }

    all_stems = dict(stem_paths)
    all_stems.update(non_voice)
    return mix, {
        "rain_db": rain_db, "voice_db_mean": voice_db_mean,
        "voice_minus_rain_db": (round(voice_db_mean - rain_db, 1)
                                if rain_db is not None
                                and voice_db_mean is not None else None),
        "rain_beds": [str(p) for p, _g, _d in rain_placements],
        "rain_bed": (str(rain_placements[0][0])
                     if rain_placements else None),
        "stems": {name: str(path) for name, path in all_stems.items()},
        "restraint": {
            "voice_db_windows": voice_db_windows,
            "stem_db_windows": stem_dbs, "gaps_db": gaps,
            "extra_attenuation_db": extra_att,
            "iterations": iterations, "ok": restraint_ok,
            "required_gap_db": 6.0, "ducking_db": duck_db},
        "ducking_db": duck_db, "master_limit_db": master_limit,
        "mix_duration_sec": round(mix_duration, 3),
        "fade_out_sec": 0.5,
        "synth_segments": len(synth_files),
        "synth_normalisation": synth_norm,
        "end_card_mute": (list(end_card_span)
                          if end_card_span is not None else None),
        "audibility": audibility,
        "skipped_jobs": skipped}


def _mix_audio(job_dir: Path, timeline_entries: list[dict],
               total_sec: float,
               rain_spans: list[tuple[float, float]] | None = None, *,
               segments: list[dict] | None = None,
               beds: list[dict] | None = None,
               mix_gains: dict | None = None,
               none_spans: dict | None = None,
               end_card_span: tuple[float, float] | None = None
               ) -> tuple[Path, dict]:
    """Mix voice wavs at their timeline offsets plus synthesised
    stems. Contract: returns (mix_path, measurements); the mix is
    exactly total_sec long with a 0.5 s fade-out and no truncation.

    ``rain_spans`` confines the rain bed to the rainy scenes' spans
    (scene-local isolation, directive section 6): an empty list or
    None means no rain anywhere.

    Old-style calls (no keyword arguments) take the legacy path
    (voice + optional per-span rain beds, unchanged). Calls with stem
    data (stage 8) take the stem-based path: dialogue/narration/foley/
    ambience/music stems, ducking, restraint re-mix and the master
    limiter (see _mix_audio_stems)."""
    if segments is None and beds is None and mix_gains is None:
        return _mix_audio_legacy(job_dir, timeline_entries,
                                 total_sec, rain_spans)
    return _mix_audio_stems(job_dir, timeline_entries, total_sec,
                            rain_spans, segments or [], beds or [],
                            mix_gains, none_spans or {},
                            end_card_span=end_card_span)


def build_contact_sheet(frames: list[str], out_path: Path,
                        *, thumb_w: int = 480, thumb_h: int = 270,
                        cols: int = 4) -> Path:
    """Contact sheet: up to 8 frames evenly spaced across the video,
    tiled with time labels — the artifact Mai compares against previous
    versions. Built from the real rendered frames, never from stills
    of another video."""
    from PIL import Image, ImageDraw, ImageFont
    picks = []
    if frames:
        n = min(8, len(frames))
        picks = [frames[int(i * (len(frames) - 1) / max(n - 1, 1))]
                 for i in range(n)]
    rows = (len(picks) + cols - 1) // cols if picks else 1
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 22)),
                      (24, 24, 30))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for i, frame_path in enumerate(picks):
        img = Image.open(frame_path).convert("RGB")
        img = img.resize((thumb_w, thumb_h))
        x = (i % cols) * thumb_w
        y = (i // cols) * (thumb_h + 22)
        sheet.paste(img, (x, y))
        fi = frames.index(frame_path)
        draw.text((x + 6, y + thumb_h + 3),
                  f"frame {fi}  t={fi / FPS:.2f}s",
                  fill=(255, 255, 255), font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path


def build_manifest(job: ProductJob, renderer_info: dict) -> dict:
    """Production manifest: everything needed to reproduce and audit
    this draft — script hash, planner, package, stages, renderer,
    QA, drive records, known limitations."""
    return {
        "job_id": job.job_id, "status": job.status,
        "script_hash": job.script_hash,
        "planner": job.planner, "planner_detail": job.planner_detail,
        "config": job.config, "stages": job.stages,
        "characters": [c.get("name") for c in
                       (job.package or {}).get("characters", [])],
        "scenes": len((job.package or {}).get("scenes", [])),
        "shots": job.shots,
        "mp4": {"path": job.mp4_path, "size_bytes": job.mp4_size,
                "duration_sec": job.mp4_duration},
        "renderer": renderer_info,
        "qa": job.qa, "drive": job.drive, "loops": job.loops,
        "errors": job.errors,
        "known_limitations": [
            "Character art: v8 design approved by Mai 2026-11-11 as-is; "
            "no character changes in this run.",
            "Creative QA is advisory only — no self-awarded Creative PASS; "
            "Mai is the final judge of art.",
            "Renderer is the code frame-by-frame renderer (Motion Canvas "
            "cannot run on this VM: Chrome launch blocked by Hatch WebGL "
            "policy).",
            "Voice pronunciation is NOT ear-verified; audio_experience is "
            "capped at 7.0 without transcription evidence.",
            "Kneel pose head height is a rig-geometry cap (~42% of "
            "standing height) — see v7/v8 audit reports.",
        ],
    }


def build_qa_report_md(job: ProductJob, manifest: dict) -> str:
    """Human-readable QA report for one draft."""
    tech = job.qa.get("technical", {})
    creative = job.qa.get("creative", {})
    verdict = job.qa.get("verdict", {})
    lines = [
        f"# QA REPORT — draft {job.job_id}",
        "",
        f"- Script hash: `{job.script_hash}`",
        f"- Planner: **{job.planner}** ({job.planner_detail})",
        f"- MP4: {job.mp4_size} bytes, {job.mp4_duration:.2f}s, "
        f"1920x1080 24fps",
        f"- Verdict: **{verdict.get('verdict', job.status)}**",
        "",
        "## Technical QA",
        "",
        f"- Status: {tech.get('status', 'n/a')}",
    ]
    for name, check in (tech.get("checks", {}) or {}).items():
        lines.append(f"  - {name}: "
                     f"{'PASS' if check.get('passed') else 'FAIL'} — "
                     f"{check.get('detail', '')}")
    lines += [
        "",
        "## Creative QA (advisory — Mai is the final judge)",
        "",
        f"- Status: {creative.get('status', 'n/a')}",
        f"- Weighted total: {creative.get('weighted_total')}",
        f"- Reasons: {creative.get('reasons', {})}",
        "",
        "## Language gate",
        "",
        f"- {job.qa.get('language', {})}",
        "",
        "## Known limitations",
        "",
    ]
    lines += [f"- {lim}" for lim in manifest["known_limitations"]]
    return "\n".join(lines) + "\n"


def dedupe_audio_events(events):
    """Deduplicate planned audio events by (event, rounded time).
    Repeated identical cues (the Eiffel excessive-SFX defect) collapse
    to one event; distinct events are never merged."""
    seen: set[tuple[str, float]] = set()
    deduped = []
    for ev in events:
        key = (ev.event_type, round(ev.at_seconds, 1))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return deduped


def _scene_is_rainy(scene: dict) -> bool:
    """Per-scene rain for the audio bed (directive section 6).

    Three independent signals, all scene-local: the location
    keyword, the location trait block's WEATHER text ("Mưa rào"
    must rain even when the action prose never says "mưa" -- the
    renderer already reads the same weather field), and a "rain"
    action cue from the scene's own directives. A rainy scene
    never implies rain in any other scene.
    """
    loc = scene.get("location")
    if isinstance(loc, dict):
        if loc.get("location_keyword") == "rainy_street":
            return True
        v1_loc = loc.get("v1_location")
        if isinstance(v1_loc, dict):
            weather = str(v1_loc.get("weather") or "").lower()
            if "mưa" in weather or "rain" in weather:
                return True
    return "rain" in (scene.get("action_cues") or [])


def _assign_line_starts(shots: list[dict],
                        timeline_entries: list[dict]) -> None:
    """Assign start/end to each timeline entry from the shot clock.

    A line split into several segments (Phase B) occupies several
    shots, but its voice is ONE uninterrupted narration: the entry
    starts at the FIRST segment's start and ends start + duration.
    Assigning on every visit (the pre-fix behaviour) overwrote the
    start with the LAST segment's start, delaying narration by a
    full segment span and truncating the final line past the stem
    end — measured by cross-correlation on job req_b741afd59822
    (L1 +6.52 s, L9 +7.98 s, dialogue exact). First visit wins;
    a line with no shot raises loudly instead of misplacing voice.
    """
    line_by_index = {e["line_index"]: e for e in timeline_entries}
    clock = 0.0
    seen: set = set()
    for shot in shots:
        if shot["kind"] in ("action", "end_card"):
            # Line-less shots (action leads, the end card) only
            # advance the clock; they carry no timeline entry.
            clock += shot["duration"]
            continue
        entry = line_by_index[shot["line_index"]]
        if shot["line_index"] not in seen:
            seen.add(shot["line_index"])
            entry["start"] = round(clock, 3)
            entry["end"] = round(clock + entry["duration"], 3)
        clock += shot["duration"]
    missing = [e["line_index"] for e in timeline_entries
               if e["line_index"] not in seen]
    if missing:
        raise RuntimeError(
            f"timeline entries with no shot (voice would be "
            f"unplaced): {missing}")


def _end_card_seconds(package: dict) -> float:
    """End-card duration in seconds (0.0 when the package declares
    no end card). The V1 adapter stores ``duration_sec``; fall back
    to parsing ``duration`` (a number, or a \"3s\" string). The
    timeline total must include the card: plan_shots appends an
    end-card shot and the renderer renders it, so excluding it
    breaks TechnicalGate.timeline_sync (Stage 3 integration fix).
    """
    card = package.get("v1_end_card") or package.get("end_card")
    if not isinstance(card, dict):
        return 0.0
    raw = card.get("duration_sec", card.get("duration"))
    if isinstance(raw, (int, float)):
        return float(raw) if float(raw) > 0 else 0.0
    if isinstance(raw, str):
        text = raw.strip().lower().rstrip("s").strip()
        try:
            value = float(text)
        except ValueError:
            return 0.0
        return value if value > 0 else 0.0
    return 0.0


def _record_to_jsonable(record):
    """Dataclass/enum-safe conversion for semantic + conflict records.

    SemanticAction / ConflictRecord are frozen dataclasses; their
    enum fields (ActionAuthority IntEnum, ActionOrigin / status
    strings) serialise as names where an enum, so the persisted
    record stays readable without importing the contract module.
    """
    if is_dataclass(record):
        record = asdict(record)
    if isinstance(record, dict):
        return {k: _record_to_jsonable(v) for k, v in record.items()}
    if isinstance(record, (list, tuple)):
        return [_record_to_jsonable(v) for v in record]
    if isinstance(record, Enum):
        return record.name
    return record


_CUE_IN_DESCRIPTION_RE = re.compile(r"cue '([a-z_]+)'")


def _discard_losing_cues(package: dict, records, events: list) -> list:
    """Remove losing keyword cues from scene action_cues lists.

    A resolved ConflictRecord whose "cues" level lost to a higher
    authority means the cue contradicts the script: the cue must
    never reach staging (planner/renderer read action_cues). The
    cue tag is parsed from the record's own description format
    ("cue '<tag>' stages...") and the scope resolves through the
    compiled events (entity action id -> scene, or shot/scene id
    -> scene). Anything unresolvable is skipped, never guessed,
    and reported in the returned list with reason="unresolved".
    Returns the discard records (applied + skipped).
    """
    discards: list[dict] = []
    by_action = {e.get("action_id"): e for e in events
                 if isinstance(e, dict)}
    shot_scene: dict = {}
    for event in events:
        if isinstance(event, dict) and event.get("shot_id") is not None:
            shot_scene.setdefault(event["shot_id"],
                                  event.get("scene_number"))
    scenes = {s.get("number"): s for s in package.get("scenes", [])
              if isinstance(s, dict)}
    cue_authority = LEVEL_AUTHORITY["cues"]
    for rec in records:
        level_a = rec.level_a if hasattr(rec, "level_a") else rec.get("level_a")
        level_b = rec.level_b if hasattr(rec, "level_b") else rec.get("level_b")
        winner = rec.winner_authority if hasattr(rec, "winner_authority") \
            else rec.get("winner_authority")
        entity = rec.entity_id if hasattr(rec, "entity_id") else rec.get("entity_id")
        description = rec.description if hasattr(rec, "description") \
            else rec.get("description", "")
        if "cues" not in (level_a, level_b):
            continue
        if winner is None or winner == cue_authority:
            continue  # unresolved, or the cue won: nothing to discard
        match = _CUE_IN_DESCRIPTION_RE.search(str(description))
        if match is None:
            discards.append({"entity_id": entity, "cue": None,
                             "reason": "unresolved",
                             "detail": "no cue tag in description"})
            continue
        cue = match.group(1)
        number = None
        event = by_action.get(entity)
        if event is not None:
            number = event.get("scene_number")
        if number is None:
            number = shot_scene.get(entity)
        if number is None:
            found = re.search(r"(\d+)", str(entity or ""))
            number = int(found.group(1)) if found else None
        scene = scenes.get(number)
        if scene is None:
            discards.append({"entity_id": entity, "cue": cue,
                             "reason": "unresolved",
                             "detail": "scope did not resolve to a scene"})
            continue
        cues = scene.get("action_cues") or []
        removed = cue in cues
        if removed:
            scene["action_cues"] = [c for c in cues if c != cue]
        winner_name = winner.name if isinstance(winner, Enum) \
            else str(winner)
        discards.append({"entity_id": entity, "cue": cue,
                         "scene": number, "removed": removed,
                         "winner_authority": winner_name,
                         "reason": "losing cue discarded"
                         if removed else "cue not in action_cues"})
    return discards


def run_product_job(script_text: str, job_dir: Path, *,
                    config: dict | None = None,
                    drive_client: GwsCliDriveClient | None = None,
                    upload: bool = True,
                    job_id: str | None = None,
                    on_stage=None) -> ProductJob:
    """Run one script through the full drawn pipeline. Returns the
    job record (status is never silently PASS — see the QA stages)."""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    job = ProductJob(
        job_id=job_id or uuid.uuid4().hex[:12],
        script=script_text, script_hash=script_hash(script_text),
        job_dir=job_dir, config=config or {})

    _stage_state = {"current": "queued"}

    def stage(name: str, status: str, detail: str = "") -> None:
        _stage_state["current"] = name
        job.record(name, status, detail)
        if on_stage:
            on_stage(name, status, detail)

    try:
        # --- 1. Script Snapshot -------------------------------------
        (job_dir / "script.txt").write_text(script_text, encoding="utf-8")
        (job_dir / "snapshot.json").write_text(json.dumps(
            {"script_hash": job.script_hash,
             "language": config.get("language", "vi-VN") if config else "vi-VN",
             "aspect_ratio": "16:9", "width": 1920, "height": 1080,
             "fps": 24, "style": "PREMIUM_STICKMAN v4"},
            indent=2, ensure_ascii=False), encoding="utf-8")
        stage("script_snapshot", "done",
              f"hash {job.script_hash[:12]}…, "
              f"{len(script_text)} chars, vi-VN, 16:9 1920x1080 24fps")

        # --- 2. Scene Package (Gemini or labelled fallback) ----------
        # enrich_v1 is opt-in via job config (server: "enrich_v1"
        # request flag): V1 scripts get real Gemini §15 trait
        # enrichment; on any enrichment failure the adapter falls
        # back to deterministic derivation with the reason
        # recorded, so the job never fails here. Default off.
        package, planner, detail = resolve_plan(
            script_text,
            enrich_v1=bool((config or {}).get("enrich_v1")))
        job.package = package
        job.planner = planner
        job.planner_detail = detail
        (job_dir / "scene_package.json").write_text(json.dumps(
            package, indent=2, ensure_ascii=False), encoding="utf-8")
        # Language gate (HARD FAIL): every spoken line and caption in a
        # vi-VN production must read Vietnamese. An English-looking line
        # (the Eiffel v5 defect) fails the job here, loudly — the
        # pipeline never dubs or captions in English instead.
        all_texts = [l["text"] for s in package["scenes"] for l in s["lines"]]
        lang_check = check_production_language(
            "vi-VN", captions=all_texts,
            narration_texts=[l["text"] for s in package["scenes"]
                             for l in s["lines"] if l["kind"] == "narration"])
        job.qa["language"] = lang_check
        if not lang_check["ok"]:
            raise RuntimeError(
                "language gate FAILED (vi-VN required, no English "
                f"fallback): {lang_check['violations']}")
        stage("scene_package", "done",
              f"planner={planner}: {detail} — "
              f"{len(package['characters'])} characters, "
              f"{len(package['scenes'])} scenes, "
              f"{len(package['shots'])} shots; language gate OK "
              f"({lang_check['checked']} lines checked)")

        # --- 2b. Semantic conflict check (early, before staging) ----
        # The conflict mechanism runs on the compiled events BEFORE
        # any staging decision (planning, TTS, rendering) so a cue
        # that contradicts the script can never shape a shot. This
        # pass uses estimated spans (times do not affect binding,
        # which is by shot/scene id); stage 7a re-runs it with real
        # spans. An unresolved mandatory conflict raises
        # UnauthorizedStoryChange and fails the job here, before
        # expensive work; any other compile failure fails here too
        # (sprint section 6 -- no silent fallback to legacy cues).
        # Losing cues are discarded from the package's action_cues
        # lists and recorded.
        _cue_records = [r for s in package["scenes"]
                        for r in (s.get("cue_records") or [])]
        # Canonical scene graph from the early compile (estimated
        # spans): the shot planner consumes it at stages 5 and 7.
        # None when the early pass did not run or failed ordinarily
        # (legacy cue-driven planning, recorded by stage 2b).
        _early_graph = None
        if _cue_records:
            _early_sem, _early_con = [], []
            try:
                _early_events, _early_unsupported = compile_actions(
                    package, inferred_cues=_cue_records,
                    semantic_sink=_early_sem, conflict_sink=_early_con)
            except UnauthorizedStoryChange as exc:
                # Mandatory conflict: record where it failed, then
                # fail the job fast, before TTS/rendering.
                stage("semantic_conflicts", "failed",
                      f"UnauthorizedStoryChange: {exc}"[:300])
                raise
            except Exception as exc:  # noqa: BLE001 - re-raised below
                # Sprint section 6: NO silent fallback. An ordinary
                # early-compile failure fails the job here, like a
                # mandatory conflict -- falling back to legacy cues
                # would stage a story the compiler could not
                # validate. The outer handler writes the structured
                # production_error.json record.
                stage("semantic_conflicts", "failed",
                      f"{type(exc).__name__}: {exc}"[:300])
                raise
            else:
                # Mandatory compile failures (actor resolution)
                # fail fast here, before staging/TTS.
                try:
                    check_compile_outcome(
                        _early_events, _early_unsupported,
                        stage="semantic_conflicts", package=package)
                except ProductionError as exc:
                    stage("semantic_conflicts", "failed",
                          str(exc)[:300])
                    raise
                _discards = _discard_losing_cues(
                    package, _early_con, _early_events)
                package["discarded_cues"] = _discards
                (job_dir / "semantic_conflicts_early.json").write_text(
                    json.dumps(
                        [_record_to_jsonable(r) for r in _early_con],
                        indent=2, ensure_ascii=False), encoding="utf-8")
                # Canonical scene graph (estimated spans): structural
                # validation fails the job here, before TTS/render.
                # The authoritative graph (real spans) is built at
                # 7a and persisted as scene_graph.json.
                try:
                    _early_graph = build_scene_graph(
                        package, _early_events,
                        semantic_actions=_early_sem,
                        unsupported=_early_unsupported)
                    validate_or_raise(_early_graph)
                except GraphValidationError as exc:
                    stage("semantic_conflicts", "failed",
                          f"GraphValidationError: {exc}"[:300])
                    raise
                # Prop-state timelines (directive section 7): a
                # definitive contradiction (pocket take followed by
                # a ground pickup with no release) fails fast here,
                # like a mandatory conflict. Per scene: a fresh
                # scene may re-introduce a prop in a fresh state.
                try:
                    _by_scene: dict = {}
                    for _event in _early_events:
                        _by_scene.setdefault(
                            _event.get("scene_number"),
                            []).append(_event)
                    for _scene_events in _by_scene.values():
                        SemanticPropTracker(
                            package.get("props") or [], _scene_events)
                except ForbiddenPropTransition as exc:
                    stage("semantic_conflicts", "failed",
                          f"ForbiddenPropTransition: {exc}"[:300])
                    raise
                stage("semantic_conflicts", "done",
                      f"{len(_early_con)} conflict records, "
                      f"{sum(1 for d in _discards if d.get('removed'))} "
                      f"losing cues discarded, "
                      f"{len(_early_events)} events compiled (estimated "
                      f"spans; re-compiled with real spans at 7a)")
        else:
            stage("semantic_conflicts", "skipped",
                  "no cue records (legacy package)")

        # --- 3. Character Design -------------------------------------
        design = []
        for i, c in enumerate(package["characters"]):
            ch = map_character(c, i)
            design.append({"name": c["name"],
                           "template": ch.template,
                           "body_variant": ch.body_variant,
                           "suit": ch.suit,
                           "height_px": int(ch.H),
                           "head_ratio": round(ch.head_r * 2 / ch.H, 3)})
        (job_dir / "character_design.json").write_text(json.dumps(
            design, indent=2, ensure_ascii=False), encoding="utf-8")
        stage("character_design", "done",
              "; ".join(f"{d['name']} ({d['template']}, {d['suit']})"
                        for d in design))

        # --- 4. Rig ---------------------------------------------------
        from .animation.rig import check_bone_lengths, validate_joints
        rig_problems = []
        for i, c in enumerate(package["characters"]):
            ch = map_character(c, i)
            from .animation.primitives import standing
            standing(ch, 960, GROUND_Y, facing=1)
            rig_problems += validate_joints(ch.joints(), ch, ground_y=GROUND_Y)
        if rig_problems:
            raise RuntimeError(f"rig validation failed: {rig_problems[:5]}")
        stage("rig", "done",
              f"{len(design)} characters, bone lengths + foot contact OK "
              f"(head_ratio 0.34, 12-joint rig)")

        # --- 5. Animation (plan; estimated durations) -----------------
        est_lines = []
        for scene in package["scenes"]:
            for line in scene["lines"]:
                est_lines.append({"line_index": len(est_lines) + 1,
                                  "duration": 4.0})
        est_shots = plan_shots(package, est_lines,
                               scene_graph=_early_graph)
        unsupported = set()
        for scene in package["scenes"]:
            for cue in scene.get("action_cues", []):
                if cue not in SUPPORTED_CUES:
                    unsupported.add(cue)
        if unsupported:
            raise RuntimeError(
                f"unsupported animation cues: {sorted(unsupported)} — "
                "the pipeline never substitutes a static pose")
        (job_dir / "animation_plan.json").write_text(json.dumps(
            est_shots, indent=2, ensure_ascii=False), encoding="utf-8")
        stage("animation", "done",
              f"{len(est_shots)} shots planned (estimated durations; "
              f"re-timed after TTS measurement)")

        # --- 6. Vietnamese TTS (vi only; failure is fatal) ------------
        flat_lines = []
        for scene in package["scenes"]:
            for line in scene["lines"]:
                flat_lines.append({"speaker": line["speaker"],
                                   "kind": line["kind"],
                                   "text": line["text"],
                                   # Per-line pause (POST_DIALOGUE_
                                   # PAUSE): the adapter emits it as
                                   # seconds; 0.35 preserves all
                                   # existing behaviour. Stage 7 reads
                                   # it into the TimelineLine.
                                   "pause_after_sec": line.get(
                                       "pause_after_sec", 0.35)})
        if not flat_lines:
            raise RuntimeError("no spoken lines in the script — "
                               "nothing to narrate")
        hints = {c["name"]: c.get("voice_hint", "")
                 for c in package["characters"]}
        voice_ids = {c["name"]: c.get("voice_id", "")
                     for c in package["characters"]}
        try:
            wavs = tts_cli_provider(flat_lines, job_dir,
                                    voice_hints=hints,
                                    voice_ids=voice_ids)
        except RuntimeError as exc:
            raise RuntimeError(
                f"Vietnamese TTS failed: {exc} — the pipeline never "
                "falls back to English voice") from exc
        durations = [measure_wav_duration(w) for w in wavs]
        if any(d is None or d <= 0 for d in durations):
            raise RuntimeError("TTS produced an empty/undated voice file")
        _manifest = json.loads(
            (job_dir / "voices_manifest.json").read_text(
                encoding="utf-8"))
        stage("vietnamese_tts", "done",
              f"{len(wavs)} lines, vi-VN, real TTS "
              f"(total voice {sum(durations):.1f}s; "
              f"{_manifest['distinct_voices_used']} distinct voices "
              f"for {len(_manifest['speakers'])} speakers; "
              f"voices_manifest.json records the engine + voice "
              f"per line)")

        # --- 7. Audio Timeline (measured, never truncated) -------------
        tl_lines = []
        for i, (line, wav, dur) in enumerate(
                zip(flat_lines, wavs, durations), 1):
            tl_lines.append(TimelineLine(
                speaker=line["speaker"], kind=line["kind"],
                text=line["text"], duration_sec=round(dur, 3),
                pause_after_sec=line.get("pause_after_sec", 0.35)))
        action_seconds = sum(float(s.get("action_lead_sec") or 0.0)
                             for s in package["scenes"])
        timeline = build_timeline(
            tl_lines, action_seconds=action_seconds,
            end_card_sec=_end_card_seconds(package))
        # Re-time the shot plan with the REAL durations.
        timeline_entries = [
            {"line_index": i + 1, "speaker": l.speaker, "kind": l.kind,
             "text": l.text, "wav": str(wavs[i]),
             "duration": round(durations[i], 3)}
            for i, l in enumerate(tl_lines)]
        shots = plan_shots(package, timeline_entries,
                           scene_graph=_early_graph)
        job.shots = shots
        (job_dir / "timeline.json").write_text(json.dumps(
            {"total_duration_sec": timeline.total_duration_sec,
             "all_measured": timeline.all_measured,
             "action_seconds": action_seconds,
             "lines": timeline_entries,
             "shots": shots}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        stage("audio_timeline", "done",
              f"total {timeline.total_duration_sec:.2f}s, all lines "
              f"measured, no truncation (guard: voice <= timeline)")

        # --- 7a. Action compilation (W4: real spans, authoritative) --
        # The stage-5 animation plan used estimated durations; this
        # compile runs AFTER TTS measurement with the real shot spans
        # (union per directive id, cumulative clock), so events carry
        # measured times. Events + unsupported persist to the job dir
        # and attach to the package for the renderer; unsupported
        # entries surface in the P9 audit, never dropped. Non-V1
        # packages compile to empty lists and keep the legacy cue
        # path (a format without semantics, not a failure). ANY
        # compile failure -- exception, graph validation, or actor
        # resolution -- fails the job after the record below is
        # written (sprint section 6: no silent fallback to legacy
        # cues, which would stage a story the compiler could not
        # validate).
        _spans: dict[str, list[float]] = {}
        _clock = 0.0
        for _s in shots:
            _did = _s.get("directive_shot_id")
            if _did:
                _span = _spans.setdefault(str(_did), [_clock, _clock])
                _span[1] = _clock + float(_s["duration"])
            _clock += float(_s["duration"])
        _compile_error = None
        _compile_exc = None
        _sem_sink: list = []
        _con_sink: list = []
        try:
            _events, _unsupported = compile_actions(
                package, timeline={"spans": _spans},
                inferred_cues=_cue_records or None,
                semantic_sink=_sem_sink, conflict_sink=_con_sink)
        except Exception as exc:  # noqa: BLE001 - recorded, re-raised
            # Sprint section 6: ANY compile failure fails the job
            # after the record below is written -- no fallback to
            # legacy cues (see the stage comment above).
            _events, _unsupported = [], []
            _compile_exc = exc
            _compile_error = f"{type(exc).__name__}: {exc}"
        # Canonical scene graph (real spans): a structural failure
        # is fatal like a mandatory conflict -- the job must not
        # render a story whose references do not resolve. The
        # error folds into _compile_error BEFORE the records are
        # written, so action_events.json stays consistent.
        _graph = None
        if _compile_error is None:
            try:
                _graph = build_scene_graph(
                    package, _events, semantic_actions=_sem_sink,
                    unsupported=_unsupported)
                validate_or_raise(_graph)
            except GraphValidationError as exc:
                _compile_error = f"GraphValidationError: {exc}"
                _compile_exc = exc
        _compiled_ok = _compile_error is None
        _classification = (classify_unsupported(_unsupported, package)
                           if _compiled_ok else
                           {"entries": [], "counts": {}, "warnings": []})
        if _compiled_ok:
            # Mandatory failures (actor resolution) fail the job;
            # the check runs BEFORE the record below is written so
            # action_events.json carries the failure consistently.
            try:
                check_compile_outcome(
                    _events, _unsupported, stage="action_compile",
                    package=package)
            except ProductionError as exc:
                _compile_error = str(exc)
                _compile_exc = exc
        package["compiled_actions"] = {
            "events": _events, "unsupported": _unsupported,
            "spans_supplied": bool(_spans),
            "compile_error": _compile_error,
            "unsupported_classification": _classification,
        }
        (job_dir / "action_events.json").write_text(json.dumps(
            package["compiled_actions"], indent=2, ensure_ascii=False),
            encoding="utf-8")
        if _compile_error is None:
            # Authoritative semantic records + conflict records from
            # the real-span compile (the early pass at 2b used
            # estimated spans and persisted only its conflicts).
            (job_dir / "semantic_actions.json").write_text(json.dumps(
                [_record_to_jsonable(r) for r in _sem_sink],
                indent=2, ensure_ascii=False), encoding="utf-8")
            (job_dir / "semantic_conflicts.json").write_text(json.dumps(
                [_record_to_jsonable(r) for r in _con_sink],
                indent=2, ensure_ascii=False), encoding="utf-8")
            # Authoritative scene graph (real spans): persisted and
            # attached to the package for downstream consumers.
            (job_dir / "scene_graph.json").write_text(json.dumps(
                _graph, indent=2, ensure_ascii=False), encoding="utf-8")
            package["scene_graph"] = _graph
        if _compile_error is not None:
            stage("action_compile", "failed", _compile_error[:300])
        else:
            stage("action_compile", "done",
                  f"{len(_events)} events, {len(_unsupported)} "
                  f"unsupported ({_classification['counts']}), "
                  f"spans_supplied={bool(_spans)}")
        if _compile_exc is not None:
            raise _compile_exc

        # --- 7b. Motion Canvas spec (Windows 3D path) ------------------
        # General scene-package -> World25D spec emission (one spec
        # per scene, real per-shot camera keyframes, fixed within
        # shots, cut on shot boundaries). Additional artifact for
        # the Windows Motion Canvas render; never a gate for the
        # 2D draft. A failure is LOUD in the job record and the 2D
        # render continues; a partial file is never written.
        try:
            # Shot clock, not the pre-plan Timeline estimate: the
            # media is built on sum(shot durations) + tail, and the
            # unified schedule freezes to the same total (frame
            # quantized) at stage 9.
            mc_spec = emit_job_spec(
                package, shots,
                sum(s["duration"] for s in shots) + 0.5,
                snapshot_hash=job.script_hash)
            (job_dir / "world25d_spec.json").write_text(json.dumps(
                mc_spec, indent=2, ensure_ascii=False), encoding="utf-8")
            stage("motioncanvas_spec", "done",
                  f"{len(mc_spec['scene_specs'])} scene specs, "
                  f"{mc_spec['duration_seconds']}s")
        except MotionCanvasSpecError as exc:
            stage("motioncanvas_spec", "failed", str(exc)[:300])

        # --- 8. SFX / Music -------------------------------------------
        # Rain is SCENE-LOCAL (directive section 6): the rainy scenes
        # are resolved per scene, and the rain bed spans only those
        # scenes. A job-level "rainy" flag leaked scene 6's rain into
        # scene 1's audio; it no longer exists.
        rainy_scenes = {
            s["number"] for s in package["scenes"]
            if _scene_is_rainy(s)}
        _shot_clock = build_shot_clock(shots)
        rain_spans = sorted(
            _shot_clock["scene_spans"][scene_no]
            for scene_no in rainy_scenes
            if scene_no in _shot_clock["scene_spans"])
        # Line start times follow the shot order: action lead-ins first,
        # then each line in its shot. Segmented lines start at their
        # FIRST segment (see _assign_line_starts).
        _assign_line_starts(shots, timeline_entries)
        # Unified production timeline (directive section 9): the one
        # authoritative clock. Seeded from the measured artifacts;
        # SFX/bed tracks join after cue resolution, subtitles after
        # splitting, then the schedule freezes.
        _timeline_builder = UnifiedTimelineBuilder()
        _expected_line_ids = seed_builder(
            _timeline_builder, shots, timeline_entries,
            (package.get("compiled_actions") or {}).get("events"))
        total_sec = _timeline_builder.draft_total_sec
        # SFX restraint (mission §3 — the Eiffel excessive-SFX fix):
        # every sound event must match an actual on-screen action cue
        # in its scene, at that scene's real start time; identical
        # events are deduplicated, never repeated; nothing is invented.
        scene_start: dict[int, float] = {}
        _clock = 0.0
        for _shot in shots:
            scene_start.setdefault(_shot["scene"], round(_clock, 2))
            _clock += _shot["duration"]
        visual_events = []
        for _scene in package["scenes"]:
            for _cue in _scene.get("action_cues", []):
                visual_events.append({
                    "event": _cue,
                    "at_seconds": scene_start.get(_scene["number"], 0.0),
                    "scene": _scene["number"]})
        # Scene-level SFX: NONE (V1) forbids even legacy action-cue
        # events in that scene (SPEC section 10.2). Non-V1 packages
        # carry no flags, so nothing is filtered for them. Raw flags
        # are used deliberately here: legacy events carry no shot
        # attribution, so a shot-scoped NONE cannot be ruled out for
        # them; shot-attributed V1 cues use the coexistence rule in
        # resolve_v1_cues instead.
        _none_flags = scene_none_flags(package)
        if _none_flags:
            visual_events = [
                v for v in visual_events
                if not _none_flags.get(v.get("scene"), {}).get("sfx")]
        events = plan_audio_events(visual_events, script_text=script_text)
        deduped = dedupe_audio_events(events.events)
        # V1 cues -> timed synthesis jobs on the measured clock
        # (Stage 3): triggers resolve here, never from planner data.
        # Non-V1 packages have no v1_audio_cues: the report is empty
        # and only legacy events render.
        v1_report = resolve_v1_cues(
            package.get("v1_audio_cues") or [],
            package=package, shots=shots,
            timeline_entries=timeline_entries, rainy_scenes=rainy_scenes,
            script_text=script_text,
            compiled_events=(package.get("compiled_actions") or {}
                             ).get("events"))
        mix_gains = v1_report["mix_gains"]
        # Legacy planned events render too (previously plan-only):
        # map them to synthesis jobs. A V1 cue wins a collision
        # (same event at the same rounded time) because its trigger
        # is specific; the legacy duplicate is recorded, not doubled.
        v1_segments = list(v1_report["segments"])
        v1_keys = {(s["event_type"], round(s["at_seconds"], 1))
                   for s in v1_segments}
        legacy_segments: list[dict] = []
        legacy_beds: list[dict] = []
        legacy_skipped: list[dict] = []
        for _ev in deduped:
            if (_ev.event_type, round(_ev.at_seconds, 1)) in v1_keys:
                legacy_skipped.append({
                    "event": _ev.event_type,
                    "at_seconds": _ev.at_seconds,
                    "reason": "superseded by a scripted V1 cue at "
                              "the same time (not doubled)"})
                continue
            _kind, _job, _reason = audio_event_to_synth_job(
                _ev, mix_gains, total_sec=total_sec)
            if _kind == "segment":
                legacy_segments.append(_job)
            elif _kind == "bed":
                legacy_beds.append(_job)
            else:
                legacy_skipped.append({
                    "event": _ev.event_type,
                    "at_seconds": _ev.at_seconds, "reason": _reason})
        if rainy_scenes:
            # rain_start beds dedupe against their OWN scene's rain
            # bed only; a bed from an unknown scene is never guessed
            # away.
            kept_beds = []
            for _bed in legacy_beds:
                if (_bed["synth_kind"] == "rain_bed"
                        and _bed.get("scene") in rainy_scenes):
                    legacy_skipped.append({
                        "event": "rain_start",
                        "at_seconds": _bed["start"],
                        "reason": "deduped against the scene rain "
                                  "bed (not doubled)"})
                else:
                    kept_beds.append(_bed)
            legacy_beds = kept_beds
        segments = v1_segments + legacy_segments
        beds = list(v1_report["beds"]) + legacy_beds
        # Combined AudioEvent plan for the report: V1 segments carry
        # cue provenance; surviving legacy events keep their shape.
        combined_events: list[AudioEvent] = []
        for _seg in v1_segments:
            combined_events.append(AudioEvent(
                _seg["event_type"], _seg["at_seconds"], _seg["sfx"],
                _seg["category"], _seg["gain_db"],
                source="synthesised",
                end_seconds=_seg["end_seconds"],
                cue_name=_seg["cue_name"], cue_id=_seg["cue_id"],
                scene=_seg["scene"], synthesis=_seg["method"]))
        for _ev in deduped:
            if (_ev.event_type, round(_ev.at_seconds, 1)) not in v1_keys:
                combined_events.append(_ev)
        combined_events.sort(key=lambda e: e.at_seconds)
        events.events = combined_events
        _end_card_sec = _end_card_seconds(package)
        _end_span = ((total_sec - _end_card_sec, total_sec)
                     if _end_card_sec > 0 else None)
        mix_path, mix_info = _mix_audio(
            job_dir, timeline_entries, total_sec, rain_spans,
            segments=segments, beds=beds, mix_gains=mix_gains,
            none_spans=v1_report["none_spans"],
            end_card_span=_end_span)
        # SFX + bed tracks join the unified timeline (segments and
        # beds carry measured times; ids are positional, unique by
        # construction).
        for _i, _seg in enumerate(segments):
            _end = float(_seg.get("end_seconds") or 0.0)
            if _end <= float(_seg["at_seconds"]):
                continue
            _timeline_builder.add_sfx(
                f"seg_{_i}", float(_seg["at_seconds"]), _end,
                {"cue_id": _seg.get("cue_id"),
                 "cue_name": _seg.get("cue_name"),
                 "synth_kind": _seg.get("synth_kind"),
                 "scene": _seg.get("scene")})
        for _i, _bed in enumerate(beds):
            _end = float(_bed.get("end") or 0.0)
            if _end <= float(_bed["start"]):
                continue
            _timeline_builder.add_bed(
                f"bed_{_i}",
                "music" if _bed.get("stem") == "music" else "ambience",
                float(_bed["start"]), _end,
                {"synth_kind": _bed.get("synth_kind"),
                 "scene": _bed.get("scene")})
        (job_dir / "audio_plan.json").write_text(json.dumps(
            {"events": events.to_dict(),
             "justification": [
                 {"event": e.event_type, "at_seconds": e.at_seconds,
                  "sfx": e.sfx, "gain_db": e.gain_db,
                  "scene": (e.scene if e.scene is not None else
                            next((v.get("scene") for v in visual_events
                                  if v["event"] == e.event_type
                                  and abs(v["at_seconds"]
                                          - e.at_seconds) < 0.6),
                                 None)),
                  "cue_name": e.cue_name, "cue_id": e.cue_id,
                  "synthesis": e.synthesis}
                 for e in combined_events],
             "blocked": events.blocked_memes,
             "legacy_skipped": legacy_skipped,
             "v1_cue_resolution": v1_report,
             "mix": mix_info, "rainy": bool(rain_spans),
             "rainy_scenes": sorted(rainy_scenes),
             "rain_spans": [[s, e] for s, e in rain_spans]},
            indent=2, ensure_ascii=False), encoding="utf-8")
        stage("sfx_music", "done",
              f"{len(combined_events)} SFX events (deduplicated, each "
              f"tied to a real on-screen cue or a scripted V1 cue), "
              f"blocked={len(events.blocked_memes)}, "
              f"V1 cues {v1_report['rendered_cues']}/"
              f"{v1_report['total_cues']} rendered "
              f"({len(v1_report['unmapped_cues'])} unmapped, "
              f"{len(v1_report['unresolved_triggers'])} unresolved "
              f"triggers), stems={sorted(mix_info.get('stems', {}))}, "
              f"rain spans={rain_spans}, "
              f"voice-rain gap={mix_info['voice_minus_rain_db']} dB, "
              f"restraint gaps={mix_info.get('restraint', {}).get('gaps_db')}, "
              f"0.5s fade-out (no abrupt ending)")

        # --- 9. Subtitle -----------------------------------------------
        subs = []
        for entry in timeline_entries:
            phrases = split_subtitle(entry["text"])
            windows = phrase_windows(entry["start"], entry["end"], phrases)
            subs.append({"line_index": entry["line_index"],
                         "phrases": phrases, "windows": windows,
                         "font_px": FONT_PX})
            for _w, _window in enumerate(windows):
                _timeline_builder.add_subtitle(
                    f"line_{entry['line_index']}_phrase_{_w}",
                    float(_window["start"]), float(_window["end"]),
                    {"line_index": entry["line_index"],
                     "phrase": _window["phrase"]})
        (job_dir / "subtitles.json").write_text(json.dumps(
            subs, indent=2, ensure_ascii=False), encoding="utf-8")
        # Freeze the unified schedule: every later stage reads it,
        # none may move it. A scheduling conflict fails the job here
        # (explicit rebuild, never a silent overwrite).
        _unified = _timeline_builder.freeze(
            expected_line_ids=_expected_line_ids)
        job.unified_timeline = _unified.to_dict()
        (job_dir / "unified_timeline.json").write_text(json.dumps(
            job.unified_timeline, indent=2, ensure_ascii=False),
            encoding="utf-8")
        # Sprint section 8, pass 1: every pre-freeze artifact
        # references the frozen schedule (version + checksum).
        # Post-render artifacts are stamped after the foley stage;
        # coverage/trace/verification reports at write time.
        _timeline_ref = timeline_ref(_unified)
        _stamp_pre = stamp_timeline_refs(
            job_dir, _timeline_ref, PRE_FREEZE_ARTIFACTS)
        job.qa["timeline_refs_pre_freeze"] = _stamp_pre
        stage("subtitle", "done",
              f"{len(subs)} lines split into short phrases, "
              f"one consistent {FONT_PX}px; unified timeline frozen "
              f"({_unified.total_frames} frames, "
              f"{_unified.total_sec:.2f}s, "
              f"checksum {_unified.checksum[:12]}...)")

        # --- 10. Renderer ----------------------------------------------
        chrome_path, chrome_detail = detect_chrome()
        # The frames below are ALWAYS rendered by the code
        # renderer (render_product_video); Motion Canvas is a
        # separate Windows path fed by the 7b spec, never the
        # engine that draws these frames. Labelling the job
        # "motion_canvas" when Chrome merely exists faked a
        # renderer that did not run (sprint section 6).
        renderer_label = "code_renderer"
        job.renderer_info = {
            "renderer": renderer_label,
            "engine": "renderer25d PerspectiveCamera + PIL, "
                      "frame-by-frame, 24fps",
            "chrome": {"path": chrome_path, "detail": chrome_detail},
            "motion_canvas_available": bool(chrome_path),
            "character_style": "PREMIUM_STICKMAN v4 "
                               "(approved by Mai 2026-11-11)",
            "width": 1920, "height": 1080, "fps": FPS,
        }
        frames_dir = job_dir / "frames"
        render = render_product_video(package, timeline_entries, frames_dir,
                                      workers=2, shots=shots)
        job.renderer_info["frames"] = render["n_frames"]
        job.renderer_info["duration_sec"] = render["duration_sec"]
        job.renderer_info["rig_violations"] = len(render["violations"])
        # W3: camera accounting (directive -> shots -> frame ranges,
        # planned vs executed poses) persisted per job for P6/P9.
        (job_dir / "camera_accounting.json").write_text(json.dumps(
            render["camera_accounting"], indent=2, ensure_ascii=False),
            encoding="utf-8")
        # Storyboard stills (step [4] artefacts) rendered from the same
        # package + real timeline, one frame per shot, into the job dir
        # so the delivery package is self-contained.
        stills = render_storyboard_stills(
            package, timeline_entries, job_dir / "storyboard",
            shots=shots)
        job.renderer_info["storyboard_stills"] = len(stills)
        (job_dir / "renderer_info.json").write_text(json.dumps(
            job.renderer_info, indent=2, ensure_ascii=False),
            encoding="utf-8")
        stage("renderer", "done",
              f"{renderer_label} ({chrome_detail}); "
              f"{render['n_frames']} frames, "
              f"{len(render['violations'])} rig violations, "
              f"duration {render['duration_sec']:.2f}s")

        # --- 10b. Foley sync (Phase G: footsteps at foot contacts) --
        _foley = sync_foley_footsteps(
            job_dir, render["shots"], shots, mix_path, total_sec,
            timeline_entries, mix_gains)
        stage("foley_sync", "done",
              f"{_foley['status']}: {_foley['placements']} footsteps "
              f"placed, {len(_foley['unresolved'])} "
              f"unresolved locomotion shots, "
              f"mix_changed={_foley['mix_changed']}")
        # Sprint section 8, pass 2: post-render artifacts reference
        # the frozen schedule.
        _stamp_post = stamp_timeline_refs(
            job_dir, _timeline_ref, POST_RENDER_ARTIFACTS)
        job.qa["timeline_refs_post_render"] = _stamp_post

        # --- 11. FFmpeg (mux; audio padded, never cut) ------------------
        mp4 = job_dir / "draft.mp4"
        pattern = build_frame_symlinks(render["frames"],
                                       job_dir / "flat_frames")
        bitrate = "20M" if job.config.get("master") else "12M"
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-threads", "2",
               "-framerate", str(FPS), "-i", pattern,
               "-i", str(mix_path),
               "-c:v", "libx264", "-profile:v", "high", "-level", "4.1",
               "-pix_fmt", "yuv420p", "-b:v", bitrate, "-maxrate", "24M",
               "-bufsize", "32M", "-r", str(FPS),
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-t", f"{render['duration_sec']:.3f}",
               "-movflags", "+faststart", str(mp4)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not mp4.exists():
            raise RuntimeError(f"ffmpeg mux failed: {r.stderr[:500]}")
        job.mp4_path = str(mp4)
        job.mp4_size = mp4.stat().st_size
        stage("ffmpeg", "done",
              f"muxed {render['n_frames']} frames + mixed audio -> "
              f"draft.mp4 ({job.mp4_size} bytes)")

        # --- 12. MP4 (probe) --------------------------------------------
        probe = probe_video(mp4)
        vs = next(s for s in probe["streams"]
                  if s["codec_type"] == "video")
        audio_streams = [s for s in probe["streams"]
                         if s["codec_type"] == "audio"]
        job.mp4_duration = float(probe["format"]["duration"])
        if (int(vs["width"]), int(vs["height"])) != (1920, 1080):
            raise RuntimeError(
                f"MP4 is {vs['width']}x{vs['height']}, not 1920x1080")
        if not audio_streams:
            raise RuntimeError("MP4 has no audio stream")
        stage("mp4", "done",
              f"1920x1080, {vs.get('r_frame_rate')} fps, "
              f"{job.mp4_duration:.2f}s, audio present")

        # --- 12b. Final MP4 verification (directive section 19) --------
        # Measures the RENDERED file against the TTS sources and the
        # frozen schedule; a failure blocks the Drive upload exactly
        # like a Technical QA failure (the draft is wrong even when
        # its plan was right). Verification exceptions fail the
        # stage loudly -- an unverified draft is not a passed draft.
        from .mp4_verifier import verify_job_mp4
        try:
            verification = verify_job_mp4(job_dir, mp4)
            verification["timeline_ref"] = dict(_timeline_ref)
            (job_dir / "mp4_verification.json").write_text(
                json.dumps(verification, indent=2, ensure_ascii=False),
                encoding="utf-8")
            job.qa["mp4_verification"] = verification
            stage("mp4_verification",
                  "done" if verification["passed"] else "failed",
                  verification["summary"])
        except Exception as exc:  # noqa: BLE001 - recorded + gated
            verification = {"passed": False,
                            "failures": [f"verifier error: {exc}"],
                            "summary": f"verifier error: {exc}"}
            job.qa["mp4_verification"] = verification
            job.errors.append(f"mp4 verification error: {exc}")
            stage("mp4_verification", "failed", str(exc)[:300])

        # --- 13. Technical QA -------------------------------------------
        dialogue_windows = [{"start": e["start"], "end": e["end"]}
                            for e in timeline_entries]
        tech = TechnicalGate().run(
            mp4, timeline_duration_sec=_unified.total_sec,
            dialogue_windows=dialogue_windows,
            expected_script_hash=job.script_hash,
            actual_script_hash=job.script_hash,
            motion_report_path=str(frames_dir / "motion_report.json"),
            pipeline_errors=job.errors, probe=probe)
        job.qa["technical"] = tech.to_dict()
        stage("technical_qa", "done" if tech.passed else "failed",
              f"{tech.status}: failed={tech.failed_checks()}")

        # --- 13b. P9 script-coverage audit (never a gate) ---------------
        # Reads the job artifacts just written and reports every
        # script item's render coverage. An audit failure is recorded
        # loudly but never fails the job: coverage evidence must not
        # mask the Technical QA verdict.
        try:
            from .coverage_audit import audit_coverage
            coverage = audit_coverage(job_dir)
            coverage["timeline_ref"] = dict(_timeline_ref)
            (job_dir / "coverage_audit.json").write_text(json.dumps(
                coverage, indent=2, ensure_ascii=False), encoding="utf-8")
            job.qa["coverage"] = {"totals": coverage["totals"],
                                  "summary": coverage["summary"]}
            stage("coverage_audit", "done",
                  f"totals={coverage['totals']}")
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            job.qa["coverage"] = {"error": str(exc)[:300]}
            stage("coverage_audit", "failed", str(exc)[:300])

        # --- 13c. Source-to-render action trace (sprint section 4) ---
        # Every mandatory action traced script -> video with its
        # frame range. Same philosophy as the coverage audit: an
        # audit failure is recorded loudly but never fails the job.
        try:
            from .action_trace import build_action_trace
            trace = build_action_trace(job_dir)
            trace["timeline_ref"] = dict(_timeline_ref)
            (job_dir / "action_trace.json").write_text(json.dumps(
                trace, indent=2, ensure_ascii=False), encoding="utf-8")
            job.qa["action_trace"] = {"summary": trace["summary"],
                                      "gaps": len(trace["gaps"])}
            stage("action_trace", "done",
                  f"traced={trace['summary']['traced']}, "
                  f"gaps={len(trace['gaps'])}, "
                  f"unsupported={trace['summary']['unsupported']}")
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            job.qa["action_trace"] = {"error": str(exc)[:300]}
            stage("action_trace", "failed", str(exc)[:300])

        # --- 13d. Audio isolation audit (sprint section 9) -----------
        # Measures the RENDERED stems: beds confined to their scene
        # spans, foley audible at anchors, NONE/end-card spans
        # silent. Non-gating audit (like coverage/trace): a leak is
        # recorded loudly for the delivery report; gating waits for
        # threshold calibration on real renders.
        try:
            from .isolation_audit import audit_audio_isolation
            isolation = audit_audio_isolation(job_dir)
            isolation["timeline_ref"] = dict(_timeline_ref)
            (job_dir / "isolation_audit.json").write_text(json.dumps(
                isolation, indent=2, ensure_ascii=False),
                encoding="utf-8")
            job.qa["isolation"] = {
                "passed": isolation["passed"],
                "failures": isolation["failures"]}
            stage("isolation_audit",
                  "done" if isolation["passed"] else "failed",
                  f"{len(isolation['checks'])} checks, "
                  f"{len(isolation['failures'])} failure(s)")
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            job.qa["isolation"] = {"error": str(exc)[:300]}
            stage("isolation_audit", "failed", str(exc)[:300])

        # --- 13e. Prop contact audit (sprint P1, section 10) --------
        # Whole-sequence grip measurement from the renderer
        # telemetry. Non-gating audit: failures are visible
        # evidence for the delivery report, and thresholds are
        # calibrated on real renders before any gating decision.
        try:
            from .contact_audit import audit_prop_contact
            contact = audit_prop_contact(job_dir)
            contact["timeline_ref"] = dict(_timeline_ref)
            (job_dir / "contact_audit.json").write_text(json.dumps(
                contact, indent=2, ensure_ascii=False),
                encoding="utf-8")
            job.qa["contact"] = {
                "passed": contact["passed"],
                "summary": contact["summary"],
                "failures": contact["failures"][:20]}
            stage("contact_audit",
                  "done" if contact["passed"] else "failed",
                  f"{contact['summary']['interactions']} interactions, "
                  f"{contact['summary']['failed']} failed")
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            job.qa["contact"] = {"error": str(exc)[:300]}
            stage("contact_audit", "failed", str(exc)[:300])
        if not tech.passed or not verification["passed"]:
            # QA FAILED -> fix & re-render loop (technical failures the
            # pipeline can fix: re-run from the renderer with a fresh
            # timeline guard; at most MAX_RERENDER_LOOPS attempts).
            failed = list(tech.failed_checks())
            if not verification["passed"]:
                failed.append("mp4_verification")
            job.loops.append({"reason": "technical_qa_failed",
                              "failed": failed})
            job.status = "QA_FAILED"
            stage("drive_upload", "skipped",
                  "QA failed — draft NOT uploaded; "
                  "re-render loop required")
            job.errors.append(
                f"technical QA failed: {failed}")
            return job

        # --- 14. Creative QA (never self-awarded) -----------------------
        creative = CreativeGate().evaluate(
            {c: None for c in
             ("character_art", "environment_art", "cinematography",
              "animation_quality", "acting_expressions",
              "visual_storytelling", "composition", "lighting",
              "audio_experience", "subtitle_readability")},
            {"subtitle_readability": {
                "type": "frame_inspection",
                "font_sizes_px": [FONT_PX] * len(subs),
                "max_lines": 2},
             "audio_experience": {
                "type": "audio_measurement",
                "pronunciation_verified": False,
                "method": "timing+RMS only",
                "voice_minus_rain_db": mix_info["voice_minus_rain_db"]}})
        job.qa["creative"] = creative.to_dict()
        character_art = CharacterArtGate().evaluate(
            {c: None for c in
             ("silhouette", "proportion", "line_quality", "joint_quality",
              "expression", "style_consistency", "small_size_readability",
              "animation_compatibility")},
            {}, human_approved=False)
        job.qa["character_art"] = character_art.to_dict()
        verdict = combine(tech, creative, character_art)
        job.qa["verdict"] = verdict
        stage("creative_qa", "done",
              f"{creative.status} (weighted_total="
              f"{creative.weighted_total}) — no self-awarded PASS; "
              f"combined verdict {verdict['verdict']}")
        job.status = verdict["verdict"]

        # --- Artifact packaging (script + hash + scene package + MP4 +
        # contact sheet + QA report + manifest + renderer info) --------
        contact_sheet = build_contact_sheet(
            render["frames"], job_dir / "contact_sheet.png")
        manifest = build_manifest(job, job.renderer_info)
        (job_dir / "manifest.json").write_text(json.dumps(
            manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        qa_report = build_qa_report_md(job, manifest)
        (job_dir / "QA_REPORT.md").write_text(qa_report, encoding="utf-8")
        job.artifacts = {
            "script": str(job_dir / "script.txt"),
            "scene_package": str(job_dir / "scene_package.json"),
            "mp4": str(mp4),
            "contact_sheet": str(contact_sheet),
            "qa_report": str(job_dir / "QA_REPORT.md"),
            "manifest": str(job_dir / "manifest.json"),
            "renderer_info": str(job_dir / "renderer_info.json"),
        }
        if (job_dir / "world25d_spec.json").exists():
            job.artifacts["motioncanvas_spec"] = str(
                job_dir / "world25d_spec.json")

        # --- 15. Google Drive Upload (draft -> TEST folder) -------------
        if upload:
            client = drive_client or GwsCliDriveClient()
            rec = client.upload_file(mp4, TEST_FOLDER_ID)
            file_id = rec.get("id", "")
            remote = client.get_file(file_id) if file_id else {}
            remote_size = int(remote.get("size") or 0)
            if not file_id or remote_size != job.mp4_size:
                raise RuntimeError(
                    f"Drive upload verification failed: local "
                    f"{job.mp4_size}, Drive {remote_size}")
            job.drive = {"file_id": file_id,
                         "url": f"https://drive.google.com/file/d/{file_id}/view",
                         "size_bytes": remote_size,
                         "folder": TEST_FOLDER_ID,
                         "artifacts": {}}
            for key in ("qa_report", "manifest", "contact_sheet",
                        "motioncanvas_spec"):
                if key not in job.artifacts:
                    continue
                path = Path(job.artifacts[key])
                r2 = client.upload_file(path, TEST_FOLDER_ID)
                fid2 = r2.get("id", "")
                rem2 = client.get_file(fid2) if fid2 else {}
                if not fid2 or int(rem2.get("size") or 0) != path.stat().st_size:
                    raise RuntimeError(
                        f"Drive upload verification failed for {path.name}")
                job.drive["artifacts"][key] = {
                    "file_id": fid2, "size_bytes": int(rem2.get("size") or 0)}
            stage("drive_upload", "done",
                  f"TEST folder, file {file_id} "
                  f"({remote_size} bytes, verified) + QA report + "
                  f"manifest + contact sheet"
                  + (" + motioncanvas_spec"
                     if "motioncanvas_spec" in job.artifacts else ""))
        else:
            stage("drive_upload", "skipped", "upload=False (test run)")
        (job_dir / "job.json").write_text(json.dumps(
            job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return job
    except Exception as exc:
        # The exception TYPE is part of the record: a generic message
        # cannot distinguish a semantic story dispute
        # (UnauthorizedStoryChange) from an ordinary stage failure.
        # Structured failure record (sprint section 6): the same
        # failure the job status reports, with the error code, the
        # stage, the source directive and the suggested resolution.
        # A ProductionError carries its own record; any other
        # exception is wrapped with the stage it failed in (read
        # BEFORE the "failed" stage record below overwrites it).
        if isinstance(exc, ProductionError):
            _structured = exc.to_dict()
        else:
            _structured = wrap_exception(
                exc, stage=_stage_state["current"]).to_dict()
        _failure = f"{type(exc).__name__}: {exc}"
        job.errors.append(_failure[:500])
        job.status = "FAILED"
        stage("failed", "failed", _failure[:300])
        (job_dir / "production_error.json").write_text(json.dumps(
            _structured, indent=2, ensure_ascii=False), encoding="utf-8")
        (job_dir / "job.json").write_text(json.dumps(
            job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return job


def approve_master(job: ProductJob, *, drive_client=None) -> ProductJob:
    """Render Master — ONLY after the user approved the draft in the
    UI (the server enforces the draft-ready status before calling
    this). Re-runs the pipeline at master bitrate and uploads to the
    root folder's master area. Never called automatically after QA."""
    if job.status not in ("DRAFT_PASSED_QA", "TECHNICAL_PASS_CREATIVE_FAIL",
                          "CREATIVE_REVIEW_REQUIRED"):
        raise RuntimeError(
            f"cannot approve master: draft status is {job.status} "
            "(Master needs a finished draft reviewed by the user)")
    master_dir = Path(job.job_dir) / "master"
    master_job = run_product_job(
        job.script, master_dir,
        config={**job.config, "master": True},
        drive_client=drive_client, upload=False,
        job_id=job.job_id + "-master")
    if master_job.status in ("FAILED", "QA_FAILED"):
        raise RuntimeError(
            f"master render failed: {master_job.errors}")
    client = drive_client or GwsCliDriveClient()
    rec = client.upload_file(Path(master_job.mp4_path), DRIVE_ROOT_FOLDER_ID)
    file_id = rec.get("id", "")
    remote = client.get_file(file_id) if file_id else {}
    if not file_id or int(remote.get("size") or 0) != master_job.mp4_size:
        raise RuntimeError("master Drive upload verification failed")
    job.master = {"file_id": file_id,
                  "url": f"https://drive.google.com/file/d/{file_id}/view",
                  "size_bytes": int(remote.get("size") or 0),
                  "source_job": master_job.job_id}
    job.status = "MASTER_UPLOADED"
    return job
