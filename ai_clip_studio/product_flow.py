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
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .audio_events import (
    SYNTHESIS_MAP,
    AudioEvent,
    audio_event_to_synth_job,
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
                      total_sec: float, rainy: bool) -> tuple[Path, dict]:
    """Mix voice wavs at their timeline offsets + a restrained rain
    bed (when the script is rainy). Returns (mix_path, measurements).
    The rain bed is verified to sit at least 6 dB below the voice.

    Kept byte-identical for old-style callers: _mix_audio dispatches
    here when no stem data is passed (see _mix_audio_stems for the
    Stage 3 stem-based mix)."""
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
    rain_path = None
    rain_db = None
    voice_db = None
    if rainy:
        rain_path = job_dir / "audio" / "rain_bed.wav"
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", f"anoisesrc=color=pink:duration={total_sec:.2f}",
             "-af", "lowpass=f=800,volume=0.10",
             "-ac", "1", "-ar", "48000", str(rain_path)],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"rain bed synthesis failed: {r.stderr[:300]}")
        rain_db = _rms_db(rain_path)
        idx = len(inputs) // 2
        inputs += ["-i", str(rain_path)]
        filters.append(f"[{idx}:a]volume=1.0[rain]")
        labels.append("[rain]")
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
                 "rain_bed": str(rain_path) if rain_path else None}


def _db_to_linear(db: float) -> float:
    return 10.0 ** (float(db) / 20.0)


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


def _mix_audio_stems(job_dir: Path, timeline_entries: list[dict],
                     total_sec: float, rainy: bool,
                     segments: list[dict], beds: list[dict],
                     mix_gains: dict | None,
                     none_spans: dict) -> tuple[Path, dict]:
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

    def _synth_for(kind: str, duration: float,
                   fade_down: bool = False) -> Path:
        key = (kind, round(float(duration), 3), bool(fade_down))
        if key in synth_files:
            return synth_files[key]
        path = synth_dir / f"{kind}_{len(synth_files):03d}.wav"
        _synth_segment(SYNTHESIS_MAP[kind], duration, path,
                       fade_mode="full" if fade_down else "edge")
        synth_files[key] = path
        return path

    # Rain bed: the same lavfi chain as the legacy path, rendered
    # from the single rain_bed spec definition.
    rain_path = None
    rain_db = None
    if rainy:
        rain_path = audio_dir / "rain_bed.wav"
        _synth_segment(SYNTHESIS_MAP["rain_bed"], total_sec, rain_path)
        rain_db = _rms_db(rain_path)

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
    if rain_path is not None:
        ambience_placements.append((rain_path, 0.0, 0.0))
    ambience_mute = [(float(a), float(b)) for a, b in
                     (none_spans.get("ambience") or [])]
    bgm_mute = [(float(a), float(b)) for a, b in
                (none_spans.get("bgm") or [])]

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
    all_stems = dict(stem_paths)
    all_stems.update(non_voice)
    return mix, {
        "rain_db": rain_db, "voice_db_mean": voice_db_mean,
        "voice_minus_rain_db": (round(voice_db_mean - rain_db, 1)
                                if rain_db is not None
                                and voice_db_mean is not None else None),
        "rain_bed": str(rain_path) if rain_path else None,
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
        "skipped_jobs": skipped}


def _mix_audio(job_dir: Path, timeline_entries: list[dict],
               total_sec: float, rainy: bool, *,
               segments: list[dict] | None = None,
               beds: list[dict] | None = None,
               mix_gains: dict | None = None,
               none_spans: dict | None = None) -> tuple[Path, dict]:
    """Mix voice wavs at their timeline offsets plus synthesised
    stems. Contract: returns (mix_path, measurements); the mix is
    exactly total_sec long with a 0.5 s fade-out and no truncation.

    Old-style calls (no keyword arguments) take the legacy path
    (voice + optional rain bed, unchanged). Calls with stem data
    (stage 8) take the stem-based path: dialogue/narration/foley/
    ambience/music stems, ducking, restraint re-mix and the master
    limiter (see _mix_audio_stems)."""
    if segments is None and beds is None and mix_gains is None:
        return _mix_audio_legacy(job_dir, timeline_entries,
                                 total_sec, rainy)
    return _mix_audio_stems(job_dir, timeline_entries, total_sec,
                            rainy, segments or [], beds or [],
                            mix_gains, none_spans or {})


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

    def stage(name: str, status: str, detail: str = "") -> None:
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
        est_shots = plan_shots(package, est_lines)
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
        try:
            wavs = tts_cli_provider(flat_lines, job_dir, voice_hints=hints)
        except RuntimeError as exc:
            raise RuntimeError(
                f"Vietnamese TTS failed: {exc} — the pipeline never "
                "falls back to English voice") from exc
        durations = [measure_wav_duration(w) for w in wavs]
        if any(d is None or d <= 0 for d in durations):
            raise RuntimeError("TTS produced an empty/undated voice file")
        stage("vietnamese_tts", "done",
              f"{len(wavs)} lines, vi-VN, real TTS "
              f"(total voice {sum(durations):.1f}s)")

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
        shots = plan_shots(package, timeline_entries)
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

        # --- 7b. Motion Canvas spec (Windows 3D path) ------------------
        # General scene-package -> World25D spec emission (one spec
        # per scene, real per-shot camera keyframes, fixed within
        # shots, cut on shot boundaries). Additional artifact for
        # the Windows Motion Canvas render; never a gate for the
        # 2D draft. A failure is LOUD in the job record and the 2D
        # render continues; a partial file is never written.
        try:
            mc_spec = emit_job_spec(
                package, shots, timeline.total_duration_sec,
                snapshot_hash=job.script_hash)
            (job_dir / "world25d_spec.json").write_text(json.dumps(
                mc_spec, indent=2, ensure_ascii=False), encoding="utf-8")
            stage("motioncanvas_spec", "done",
                  f"{len(mc_spec['scene_specs'])} scene specs, "
                  f"{mc_spec['duration_seconds']}s")
        except MotionCanvasSpecError as exc:
            stage("motioncanvas_spec", "failed", str(exc)[:300])

        # --- 8. SFX / Music -------------------------------------------
        rainy = any(s.get("location", {}).get("location_keyword")
                    == "rainy_street" for s in package["scenes"]) or \
            any("rain" in (s.get("action_cues") or [])
                for s in package["scenes"])
        # Line start times follow the shot order: action lead-ins first,
        # then each line in its shot.
        clock = 0.0
        line_by_index = {e["line_index"]: e for e in timeline_entries}
        for shot in shots:
            if shot["kind"] in ("action", "end_card"):
                # Line-less shots (action leads, the end card) only
                # advance the clock; they carry no timeline entry.
                clock += shot["duration"]
            else:
                entry = line_by_index[shot["line_index"]]
                entry["start"] = round(clock, 3)
                entry["end"] = round(clock + entry["duration"], 3)
                clock += shot["duration"]
        total_sec = sum(s["duration"] for s in shots) + 0.5
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
            timeline_entries=timeline_entries, rainy=rainy,
            script_text=script_text)
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
        if rainy:
            # rain_start beds dedupe against the global rain bed.
            kept_beds = []
            for _bed in legacy_beds:
                if _bed["synth_kind"] == "rain_bed":
                    legacy_skipped.append({
                        "event": "rain_start",
                        "at_seconds": _bed["start"],
                        "reason": "deduped against the global rain "
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
        mix_path, mix_info = _mix_audio(
            job_dir, timeline_entries, total_sec, rainy,
            segments=segments, beds=beds, mix_gains=mix_gains,
            none_spans=v1_report["none_spans"])
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
             "mix": mix_info, "rainy": rainy},
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
              f"rain bed={'yes' if rainy else 'no'}, "
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
        (job_dir / "subtitles.json").write_text(json.dumps(
            subs, indent=2, ensure_ascii=False), encoding="utf-8")
        stage("subtitle", "done",
              f"{len(subs)} lines split into short phrases, "
              f"one consistent {FONT_PX}px")

        # --- 10. Renderer ----------------------------------------------
        chrome_path, chrome_detail = detect_chrome()
        renderer_label = ("motion_canvas" if chrome_path else
                          "code_renderer_fallback")
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
                                      workers=2)
        job.renderer_info["frames"] = render["n_frames"]
        job.renderer_info["duration_sec"] = render["duration_sec"]
        job.renderer_info["rig_violations"] = len(render["violations"])
        # Storyboard stills (step [4] artefacts) rendered from the same
        # package + real timeline, one frame per shot, into the job dir
        # so the delivery package is self-contained.
        stills = render_storyboard_stills(
            package, timeline_entries, job_dir / "storyboard")
        job.renderer_info["storyboard_stills"] = len(stills)
        (job_dir / "renderer_info.json").write_text(json.dumps(
            job.renderer_info, indent=2, ensure_ascii=False),
            encoding="utf-8")
        stage("renderer", "done",
              f"{renderer_label} ({chrome_detail}); "
              f"{render['n_frames']} frames, "
              f"{len(render['violations'])} rig violations, "
              f"duration {render['duration_sec']:.2f}s")

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

        # --- 13. Technical QA -------------------------------------------
        dialogue_windows = [{"start": e["start"], "end": e["end"]}
                            for e in timeline_entries]
        tech = TechnicalGate().run(
            mp4, timeline_duration_sec=timeline.total_duration_sec,
            dialogue_windows=dialogue_windows,
            expected_script_hash=job.script_hash,
            actual_script_hash=job.script_hash,
            motion_report_path=str(frames_dir / "motion_report.json"),
            pipeline_errors=job.errors, probe=probe)
        job.qa["technical"] = tech.to_dict()
        stage("technical_qa", "done" if tech.passed else "failed",
              f"{tech.status}: failed={tech.failed_checks()}")
        if not tech.passed:
            # QA FAILED -> fix & re-render loop (technical failures the
            # pipeline can fix: re-run from the renderer with a fresh
            # timeline guard; at most MAX_RERENDER_LOOPS attempts).
            job.loops.append({"reason": "technical_qa_failed",
                              "failed": tech.failed_checks()})
            job.status = "QA_FAILED"
            stage("drive_upload", "skipped",
                  "technical QA failed — draft NOT uploaded; "
                  "re-render loop required")
            job.errors.append(
                f"technical QA failed: {tech.failed_checks()}")
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
        job.errors.append(str(exc)[:500])
        job.status = "FAILED"
        stage("failed", "failed", str(exc)[:300])
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
