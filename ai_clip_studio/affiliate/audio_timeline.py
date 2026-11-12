"""Audio-driven timeline + audio buses + mix (§14–§15).

The timeline is built from REAL generated speech durations — never
from character-count estimates at render time, never by truncating
speech, never by accelerating it. When narration is longer than the
available footage, the conflict is REPORTED with the four §14
resolution options; the timeline builder never silently freezes the
last frame or speeds up speech.

Audio buses: voice / original / music / sfx. Mix modes:
REPLACE_ALL, KEEP_PRODUCT_SOUNDS, DUCK_ORIGINAL_AUDIO, CUSTOM_MIX.
Default behaviour: low music, automatic ducking under speech, smooth
fades, restrained SFX. Music is mixed ONLY from an authorized file
(``AudioMix.music_authorized``) — no copyrighted music reuse.

``render_mix`` runs a real ffmpeg mix. The mix plan is a pure data
structure (``MixPlan``) so tests can verify gains/fades/ducking
without running ffmpeg, and the render stage can verify the real
output file afterwards.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..timeline import TimelineError, measure_audio_duration
from .schema import AffiliateScript, AudioMix

RESOLUTION_OPTIONS = (
    "shorten_script_with_approval",
    "reallocate_visual_segments",
    "use_additional_authorized_footage",
    "report_unresolved_conflict",
)


@dataclass
class TimelineSegment:
    segment_id: str
    section: str
    text: str
    start: float
    end: float
    voice_wav: str
    measured_sec: float

    def to_dict(self) -> dict:
        return {"segment_id": self.segment_id, "section": self.section,
                "text": self.text, "start": round(self.start, 3),
                "end": round(self.end, 3), "voice_wav": self.voice_wav,
                "measured_sec": self.measured_sec}


@dataclass
class AffiliateTimeline:
    segments: list[TimelineSegment] = field(default_factory=list)
    footage_sec: float = 0.0
    narration_sec: float = 0.0
    total_sec: float = 0.0
    all_measured: bool = False
    conflict: dict | None = None

    def to_dict(self) -> dict:
        return {"segments": [s.to_dict() for s in self.segments],
                "footage_sec": round(self.footage_sec, 3),
                "narration_sec": round(self.narration_sec, 3),
                "total_sec": round(self.total_sec, 3),
                "all_measured": self.all_measured,
                "conflict": self.conflict}


def build_affiliate_timeline(script: AffiliateScript, *,
                             footage_sec: float,
                             pause_after_sec: float = 0.5,
                             audio_tail_sec: float = 0.5) -> AffiliateTimeline:
    """Place measured narration segments on the footage timeline.

    Every segment must carry a measured WAV (from the TTS stage) —
    estimated durations are refused here, because the render timeline
    must come from real speech. ``conflict`` is set (not raised) when
    narration overflows the footage, so the API can present the §14
    options to the user; the render stage must refuse to render while
    a conflict is unresolved.
    """
    if footage_sec <= 0:
        raise TimelineError("footage_sec must be > 0")
    segments: list[TimelineSegment] = []
    clock = 0.0
    for seg in script.segments:
        if not seg.voice_wav or seg.measured_sec is None:
            raise TimelineError(
                f"segment {seg.segment_id} has no measured TTS audio — "
                "the affiliate timeline is built from real speech only")
        measured = measure_audio_duration(Path(seg.voice_wav))
        if measured is None:
            raise TimelineError(f"cannot measure {seg.voice_wav}")
        segments.append(TimelineSegment(
            segment_id=seg.segment_id, section=seg.section, text=seg.text,
            start=round(clock, 3), end=round(clock + measured, 3),
            voice_wav=seg.voice_wav, measured_sec=round(measured, 3)))
        clock += measured + pause_after_sec
    narration_sec = round(max(0.0, clock - pause_after_sec), 3)
    total = round(max(footage_sec, narration_sec) + audio_tail_sec, 3)
    conflict = None
    if narration_sec > footage_sec + 0.01:
        conflict = {
            "kind": "narration_longer_than_footage",
            "narration_sec": narration_sec,
            "footage_sec": round(footage_sec, 3),
            "overflow_sec": round(narration_sec - footage_sec, 3),
            "options": list(RESOLUTION_OPTIONS),
            "resolved": False,
            "resolution": None,
        }
    return AffiliateTimeline(
        segments=segments, footage_sec=round(footage_sec, 3),
        narration_sec=narration_sec, total_sec=total,
        all_measured=True, conflict=conflict)


def resolve_timeline_conflict(timeline: AffiliateTimeline, *,
                              resolution: str,
                              note: str = "") -> AffiliateTimeline:
    """Record a user-chosen §14 resolution. The resolution itself
    (shortening, reallocation, extra footage) is applied by the
    caller; this only records the decision on the timeline."""
    if resolution not in RESOLUTION_OPTIONS:
        raise TimelineError(f"unknown resolution {resolution!r}")
    if timeline.conflict is None:
        raise TimelineError("no timeline conflict to resolve")
    timeline.conflict["resolved"] = True
    timeline.conflict["resolution"] = resolution
    timeline.conflict["resolution_note"] = note
    return timeline


# ------------------------------------------------------------------- mix

@dataclass
class MixPlan:
    mode: str
    voice_wav: str = ""       # concatenated narration, or ""
    original_wav: str = ""    # source audio stem, or ""
    music_wav: str = ""       # authorized music file, or ""
    sfx_wavs: list[str] = field(default_factory=list)
    bus_gains_db: dict[str, float] = field(default_factory=dict)
    ducking_db: float = 14.0
    fade_in_sec: float = 0.3
    fade_out_sec: float = 0.5
    total_sec: float = 0.0

    def to_dict(self) -> dict:
        return {"mode": self.mode, "voice_wav": self.voice_wav,
                "original_wav": self.original_wav,
                "music_wav": self.music_wav, "sfx_wavs": self.sfx_wavs,
                "bus_gains_db": dict(self.bus_gains_db),
                "ducking_db": self.ducking_db,
                "fade_in_sec": self.fade_in_sec,
                "fade_out_sec": self.fade_out_sec,
                "total_sec": self.total_sec}


def plan_mix(mix: AudioMix, *, voice_wav: str = "", original_wav: str = "",
             music_wav: str = "", sfx_wavs: list[str] | None = None,
             total_sec: float = 0.0) -> MixPlan:
    """Build a mix plan from the AudioMix config + real stem paths.

    REPLACE_ALL drops the original stem entirely. KEEP_PRODUCT_SOUNDS
    keeps it low under the voice. DUCK_ORIGINAL_AUDIO applies
    sidechain ducking. CUSTOM_MIX uses the configured gains verbatim.
    Music without authorization is refused, not mixed quietly.
    """
    if music_wav and not mix.music_authorized:
        raise TimelineError("refusing to mix background music without "
                            "an authorization confirmation")
    gains = dict(mix.bus_gains_db)
    original = original_wav
    if mix.mode == "REPLACE_ALL":
        original = ""
        gains["original"] = -60.0
    elif mix.mode == "KEEP_PRODUCT_SOUNDS":
        gains.setdefault("original", -18.0)
    elif mix.mode == "DUCK_ORIGINAL_AUDIO":
        gains.setdefault("original", -6.0)
    return MixPlan(
        mode=mix.mode, voice_wav=voice_wav, original_wav=original,
        music_wav=music_wav, sfx_wavs=list(sfx_wavs or []),
        bus_gains_db=gains, ducking_db=mix.ducking_db,
        fade_in_sec=mix.fade_in_sec, fade_out_sec=mix.fade_out_sec,
        total_sec=total_sec)


def _sidechain_filter_name() -> str | None:
    """The sidechain compressor filter this ffmpeg build provides.

    FFmpeg builds differ: modern builds expose ``sidechaincompressor``
    while others (including this VM's FFmpeg 8.1.2) expose the older
    ``sidechaincompress`` name. Both take identical parameters.
    Returns None when neither exists — the mix then keeps the music
    at its low static gain instead of claiming ducking it cannot do.
    """
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    names = result.stdout
    if " sidechaincompressor " in names or "\n sidechaincompressor" in names:
        return "sidechaincompressor"
    if " sidechaincompress " in names or "\n sidechaincompress" in names:
        return "sidechaincompress"
    return None


def build_mix_filter(plan: MixPlan) -> tuple[list[str], str]:
    """Build the ffmpeg inputs + filter_complex for a mix plan.

    Returns (input_args, filter_complex). Inputs are ordered:
    0=voice, 1=original, 2=music, 3..=sfx. Each bus gets its gain,
    the music/original buses are ducked under the voice with a
    sidechain compressor, and the final mix gets smooth fades.
    """
    inputs: list[str] = []
    chains: list[str] = []
    labels: list[str] = []
    idx = 0

    def _add(path: str, bus: str) -> str:
        nonlocal idx
        inputs.extend(["-i", path])
        label = f"[{idx}:a]"
        gain = plan.bus_gains_db.get(bus, 0.0)
        out_label = f"b{bus}"
        chains.append(f"{label}volume={gain}dB[{out_label}]")
        idx += 1
        return out_label

    voice_label = None
    if plan.voice_wav:
        voice_label = _add(plan.voice_wav, "voice")
        labels.append(voice_label)
    duck_sources: list[str] = []
    if plan.original_wav:
        duck_sources.append(_add(plan.original_wav, "original"))
    if plan.music_wav:
        duck_sources.append(_add(plan.music_wav, "music"))
    for i, sfx in enumerate(plan.sfx_wavs):
        labels.append(_add(sfx, "sfx"))
    # Duck music/original under the voice when a voice bus exists.
    sidechain = _sidechain_filter_name() if voice_label is not None else None
    for j, src in enumerate(duck_sources):
        if voice_label is not None and sidechain is not None:
            ducked = f"duck{j}"
            chains.append(
                f"[{src}][{voice_label}]{sidechain}="
                f"threshold=-30dB:ratio=4:attack=50:release=400:"
                f"makeup=0dB[{ducked}]")
            labels.append(ducked)
        else:
            # No voice bus, or no sidechain filter in this ffmpeg
            # build: the bus keeps its (low) static gain. The plan's
            # ducking flag is not claimed in that case.
            labels.append(src)
    if not labels:
        raise TimelineError("mix plan has no audio inputs")
    if len(labels) == 1:
        mixed = labels[0]
    else:
        chains.append(
            f"{''.join('[' + l + ']' for l in labels)}"
            f"amix=inputs={len(labels)}:normalize=0[mixed]")
        mixed = "mixed"
    fade_out_start = max(0.0, plan.total_sec - plan.fade_out_sec)
    chains.append(
        f"[{mixed}]afade=t=in:st=0:d={plan.fade_in_sec},"
        f"afade=t=out:st={fade_out_start}:d={plan.fade_out_sec}[faded]")
    # apad + the -t limit in render_mix pin the mix to exactly the
    # timeline length even when a bus (e.g. music) is shorter.
    chains.append("[faded]apad[out]")
    return inputs, ";".join(chains)


def render_mix(plan: MixPlan, out_path: Path) -> Path:
    """Run the real ffmpeg mix. Returns the mixed WAV path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    inputs, filter_complex = build_mix_filter(plan)
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
           "-filter_complex", filter_complex,
           "-map", "[out]", "-t", str(plan.total_sec),
           "-ac", "2", "-ar", "48000", str(out_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not out_path.exists():
        raise TimelineError(f"ffmpeg mix failed: {result.stderr[:400]}")
    return out_path


def concatenate_voice(timeline: AffiliateTimeline, out_path: Path) -> Path:
    """Concatenate the narration WAVs with their pauses into one
    voice stem, placed at the timeline offsets. Silence pads the
    gaps; nothing is truncated or sped up."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not timeline.segments:
        raise TimelineError("no narration segments to concatenate")
    inputs: list[str] = []
    delays: list[str] = []
    for i, seg in enumerate(timeline.segments):
        inputs.extend(["-i", seg.voice_wav])
        delays.append(f"[{i}:a]adelay={int(seg.start * 1000)}|"
                      f"{int(seg.start * 1000)}[d{i}]")
    labels = "".join(f"[d{i}]" for i in range(len(timeline.segments)))
    # apad pads the stem with silence to the full timeline length:
    # without it, amix ends at the last narration segment and the
    # -t limit cannot extend the file (the mix then truncates).
    filt = (";".join(delays) + f";{labels}amix=inputs="
            f"{len(timeline.segments)}:normalize=0[mixed];[mixed]apad[out]")
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
           "-filter_complex", filt, "-map", "[out]",
           "-t", str(timeline.total_sec),
           "-ac", "1", "-ar", "48000", str(out_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not out_path.exists():
        raise TimelineError(f"voice concatenation failed: {result.stderr[:400]}")
    return out_path
