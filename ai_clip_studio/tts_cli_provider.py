"""Voice provider backed by the /opt/hatch/bin/tts CLI (shared engine).

Production wants VieNeu-TTS (stage 9), but the `vieneu` package is not
installed on this Linux VM — so the provider synthesises real Vietnamese
speech with the same CLI the v3/v4 narrations used, and the orchestrator
records it as an injected provider. On Mai's Windows machine the real
VieNeu provider replaces this without changing the pipeline.

Voice map (by speaker role, not by story):
  narrator -> avocado_v2:MAI_01 (Aria, Warm) — warm Vietnamese narrator
  male speaker (voice_hint "giọng nam") -> avocado_v2:ronan (Casual)
  female speaker (voice_hint "giọng nữ") -> avocado_v2:paloma (Light)
  unknown -> avocado_v2:MAI_03 (default, same as v3)

Each line is synthesised at speed 100 (1.00x, never sped up) with
--language vi, decoded to 48 kHz mono WAV, and measured. Returns exactly
one WAV per input line, in order.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

TTS_BIN = "/opt/hatch/bin/tts"
NARRATOR_VOICE = "avocado_v2:MAI_01"
MALE_VOICE = "avocado_v2:ronan"
FEMALE_VOICE = "avocado_v2:paloma"
DEFAULT_VOICE = "avocado_v2:MAI_03"


def voice_for(speaker: str, voice_hint: str = "") -> str:
    if speaker == "narrator":
        return NARRATOR_VOICE
    hint = (voice_hint or "").lower()
    if "giọng nam" in hint or "nam" in hint:
        return MALE_VOICE
    if "giọng nữ" in hint or "nữ" in hint:
        return FEMALE_VOICE
    return DEFAULT_VOICE


def tts_cli_provider(lines, job_dir: Path, *,
                     voice_hints: dict[str, str] | None = None) -> list[Path]:
    """Synthesise one real WAV per line. `lines` are TimelineLine objects
    (or dicts with text/speaker). Raises on any failure — never returns a
    silent placeholder."""
    job_dir = Path(job_dir)
    out_dir = job_dir / "voices"
    out_dir.mkdir(parents=True, exist_ok=True)
    hints = voice_hints or {}
    wavs: list[Path] = []
    for i, line in enumerate(lines, 1):
        if isinstance(line, dict):
            text = line["text"]
            speaker = line.get("speaker", "narrator")
        else:  # TimelineLine dataclass
            text = line.text
            speaker = line.speaker
        voice = voice_for(speaker, hints.get(speaker, ""))
        mp3 = out_dir / f"line{i:02d}_{speaker}.mp3"
        r = subprocess.run(
            [TTS_BIN, "speak", "--language", "vi", "--speed", "100",
             "--voice", voice, "--output", str(mp3), "--text-stdin"],
            input=text.encode("utf-8"), capture_output=True, timeout=180)
        if r.returncode != 0 or not mp3.exists() or mp3.stat().st_size < 1000:
            raise RuntimeError(
                f"TTS failed for line {i} ({speaker}): "
                f"{r.stderr.decode('utf-8', 'replace')[:300]}")
        wav = out_dir / f"line{i:02d}_{speaker}.wav"
        r2 = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
             "-ac", "1", "-ar", "48000", str(wav)],
            capture_output=True, text=True, timeout=60)
        if r2.returncode != 0 or not wav.exists():
            raise RuntimeError(f"ffmpeg decode failed for line {i}: {r2.stderr[:300]}")
        wavs.append(wav)
    return wavs
