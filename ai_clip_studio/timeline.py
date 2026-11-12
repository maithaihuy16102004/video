"""Dynamic timeline engine (Master Prompt §8).

Duration is calculated from the real audio and the real actions —
never from a fixed 10 s / 15 s / 30 s cap. If speech needs 17 s, the
scene takes 17 s. Never truncate narration, never freeze the final
frame, never speed up speech (speed must stay 1.00x).

Upstream status (see AUDIT.md): this is exactly the V51 bug.
`pipeline/studio_api.py:1973` hard-locks previews to 15 s and finals
to 30 s, and `pipeline/universal/v5_audio_director.py` silently
truncates overflowing lines. Patch 02 (in ../patches/, reviewed and
verified but NOT yet applied — needs Mai's approval) fixes the
upstream code. This module is the additive, already-correct
implementation the pipeline uses from now on. A voice-led planner
also exists upstream (`pipeline/universal/voice/timeline_planner.py`,
`VoiceLedTimelinePlanner.build_timeline`); this module is the
standalone, testable version with the truncation guard.
"""

from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

# Silence / pause defaults (seconds).
DEFAULT_PAUSE_AFTER_SENTENCE = 0.5
DEFAULT_PAUSE_AFTER_DIALOGUE_TURN = 0.8
DEFAULT_TRANSITION_SEC = 0.6
DEFAULT_AUDIO_TAIL_SEC = 0.5


class TimelineError(ValueError):
    """Raised when a timeline would truncate speech or speed it up."""


def measure_wav_duration(path: Path) -> float:
    """Real duration of a WAV file, in seconds (wave module, stdlib)."""
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def measure_audio_duration(path: Path) -> float | None:
    """Duration of any audio file: WAV via wave, anything else via ffprobe."""
    path = Path(path)
    if path.suffix.lower() == ".wav":
        try:
            return measure_wav_duration(path)
        except (wave.Error, OSError):
            return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip()) if out.returncode == 0 else None
    except (FileNotFoundError, ValueError, subprocess.SubprocessError):
        return None


def estimate_speech_duration(text: str, chars_per_second: float = 11.0) -> float:
    """Rough Vietnamese TTS estimate, used ONLY when no real audio exists
    yet. The result is marked estimated and must be replaced by the
    measured duration before rendering (see build_timeline)."""
    text = text.strip()
    if not text:
        return 0.0
    return max(0.8, len(text) / chars_per_second)


@dataclass
class TimelineLine:
    """One spoken line with its real (or estimated) audio duration."""
    text: str
    speaker: str = "narrator"
    kind: str = "narration"  # narration | dialogue
    voice_wav: Path | None = None
    duration_sec: float | None = None  # measured duration, when known
    pause_after_sec: float = DEFAULT_PAUSE_AFTER_SENTENCE

    def resolved_duration(self) -> tuple[float, bool]:
        """(duration, was_measured). Raises if the WAV cannot be read."""
        if self.voice_wav is not None:
            measured = measure_audio_duration(Path(self.voice_wav))
            if measured is None:
                raise TimelineError(
                    f"cannot measure voice audio {self.voice_wav} for line "
                    f"{self.text[:40]!r} — refusing to guess the timeline"
                )
            return measured, True
        if self.duration_sec is not None:
            return float(self.duration_sec), True
        return estimate_speech_duration(self.text), False


@dataclass
class Timeline:
    lines: list[TimelineLine] = field(default_factory=list)
    action_seconds: float = 0.0      # physical actions needing extra time
    transition_seconds: float = 0.0  # scene transitions
    audio_tail_sec: float = DEFAULT_AUDIO_TAIL_SEC
    end_card_sec: float = 0.0        # end-card shot (V1 END_CARD)
    total_duration_sec: float = 0.0
    all_measured: bool = False

    def check_no_truncation(self, planned_sec: float, real_audio_sec: float) -> None:
        """Fail loud if the timeline is shorter than the real audio.

        This is the guard the V51 drafts lacked: a 3.00 s voice on a
        2.00 s timeline must raise, never silently cut the final line.
        """
        if real_audio_sec > planned_sec + 0.01:
            raise TimelineError(
                f"Voice audio ({real_audio_sec:.2f}s) is longer than the "
                f"planned timeline ({planned_sec:.2f}s). Extend "
                "total_duration_sec instead of truncating the final line."
            )


def build_timeline(
    lines: list[TimelineLine],
    action_seconds: float = 0.0,
    transition_seconds: float = 0.0,
    audio_tail_sec: float = DEFAULT_AUDIO_TAIL_SEC,
    speech_speed: float = 1.0,
    end_card_sec: float = 0.0,
) -> Timeline:
    """Build the timeline from real durations. No caps, no speed-up.

    ``end_card_sec`` is the V1 END_CARD shot duration: the card is
    part of the rendered video, so the timeline total must cover
    it — otherwise TechnicalGate.timeline_sync fails on every
    script that declares an end card (Stage 3 integration fix).
    """
    if speech_speed != 1.0:
        raise TimelineError(
            f"speech_speed must be 1.00x (V5 rule), got {speech_speed} — "
            "never accelerate dialogue to fit a fixed timeline"
        )
    total = 0.0
    all_measured = True
    for line in lines:
        duration, measured = line.resolved_duration()
        all_measured = all_measured and measured
        total += duration + line.pause_after_sec
    total += float(action_seconds) + float(transition_seconds) + float(audio_tail_sec)
    total += float(end_card_sec)
    timeline = Timeline(
        lines=list(lines),
        action_seconds=float(action_seconds),
        transition_seconds=float(transition_seconds),
        audio_tail_sec=float(audio_tail_sec),
        end_card_sec=float(end_card_sec),
        total_duration_sec=round(total, 3),
        all_measured=all_measured,
    )
    # Guard: the timeline must cover the whole voice track.
    voice_total = sum(l.resolved_duration()[0] for l in lines)
    timeline.check_no_truncation(timeline.total_duration_sec, voice_total)
    return timeline
