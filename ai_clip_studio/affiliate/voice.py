"""Vietnamese TTS for Affiliate Studio (§13) — shared provider reuse.

VieNeu-TTS is the production engine, but the ``vieneu`` package is
not installed on this Linux VM — exactly like Story Studio, this
module synthesises real Vietnamese speech through the shared
``tts_cli_provider`` (``/opt/hatch/bin/tts`` with ``--language vi``).
On Mai's Windows machine the real VieNeu provider replaces it
without changing the pipeline.

Voice presets map ONLY to voices the provider really offers
(``language_gate.VI_VOICES`` — the four voice IDs already used in
production). There is no invented voice, region, or style control:
``voice_region`` records the provider default, and ``voice_style``
is descriptive metadata only.

Per-character dubbing (Douyin standing requirement, 2026-11-12):
each distinct speaker in the source maps to its own Vietnamese
voice, consistently across the video. The mapping is DATA —
``VoiceConfig.speaker_voices`` (speaker_id -> preset name) — never
hardcoded. ``VOICE_PRESETS`` is the single seam where preset names
bind to provider voice ids: on this VM they bind to the tts CLI
voices; on Mai's Windows machine the same preset names bind to
real VieNeu voices through the provider there, with no pipeline
change. A speaker with no mapping uses the default voice.

Speed: the CLI accepts 1–200 (100 = 1.00x). Presets default to 100.
A custom speed within 90–110 is allowed as a user choice; speed is
NEVER changed automatically to fit a timeline (that would violate
the no-acceleration rule — see audio_timeline.py).

Failure behaviour: any TTS failure raises and stops the job — never
a silent placeholder, never an English fallback.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..language_gate import VI_VOICES, resolve_voice
from ..timeline import TimelineLine, measure_audio_duration
from ..tts_cli_provider import TTS_BIN, tts_cli_provider
from .schema import AffiliateScript, ScriptSegment, VoiceConfig

# Preset name -> (voice_id, gender, speed, style note). All four voice
# IDs are the real ones already used by the production pipeline.
VOICE_PRESETS: dict[str, dict] = {
    "female_review": {
        "voice_id": VI_VOICES["female"], "voice_gender": "female",
        "voice_speed": 100, "voice_style": "female product review",
        "speaker": "female_speaker", "voice_hint": "giọng nữ",
        "label_vi": "Nữ review sản phẩm",
    },
    "male_review": {
        "voice_id": VI_VOICES["male"], "voice_gender": "male",
        "voice_speed": 100, "voice_style": "male product review",
        "speaker": "male_speaker", "voice_hint": "giọng nam",
        "label_vi": "Nam review sản phẩm",
    },
    "friendly_conversational": {
        "voice_id": VI_VOICES["female"], "voice_gender": "female",
        "voice_speed": 100, "voice_style": "friendly conversational",
        "speaker": "female_speaker", "voice_hint": "giọng nữ",
        "label_vi": "Trò chuyện thân thiện",
    },
    "energetic_intro": {
        "voice_id": VI_VOICES["default"], "voice_gender": "",
        "voice_speed": 105, "voice_style": "energetic introduction",
        "speaker": "narrator", "voice_hint": "",
        "label_vi": "Mở đầu năng động",
    },
    "calm_demo": {
        "voice_id": VI_VOICES["narrator"], "voice_gender": "",
        "voice_speed": 98, "voice_style": "calm demonstration",
        "speaker": "narrator", "voice_hint": "",
        "label_vi": "Thuyết minh bình tĩnh",
    },
}

PREVIEW_TEXT = "Xin chào, đây là giọng đọc thử nghiệm cho video giới thiệu sản phẩm."

MIN_SPEED = 90
MAX_SPEED = 110


class VoiceError(RuntimeError):
    """Raised when voice resolution or synthesis fails — stops the job."""


def preset_config(preset: str) -> VoiceConfig:
    """VoiceConfig for a preset name. Raises on unknown presets."""
    if preset not in VOICE_PRESETS:
        raise VoiceError(f"unknown voice preset {preset!r}; available: "
                         f"{sorted(VOICE_PRESETS)}")
    spec = VOICE_PRESETS[preset]
    return VoiceConfig(
        voice_id=spec["voice_id"], voice_gender=spec["voice_gender"],
        voice_region="",  # provider default; the CLI exposes no region
        voice_speed=spec["voice_speed"], voice_style=spec["voice_style"],
        preset=preset)


def resolve_affiliate_voice(config: VoiceConfig) -> str:
    """Resolve the concrete provider voice id for a config.

    An explicit voice_id wins (it must be one of the real provider
    voices); otherwise the preset or the language-gate resolution
    applies. Raises instead of falling back to English.
    """
    if config.voice_id:
        if config.voice_id not in set(VI_VOICES.values()):
            raise VoiceError(
                f"voice_id {config.voice_id!r} is not a voice this "
                f"provider offers: {sorted(set(VI_VOICES.values()))}")
        return config.voice_id
    if config.preset:
        return preset_config(config.preset).voice_id
    hint = "giọng nữ" if config.voice_gender == "female" else (
        "giọng nam" if config.voice_gender == "male" else "")
    return resolve_voice("vi-VN", "narrator", hint)


def validate_speaker_voices(config: VoiceConfig) -> None:
    """Every preset named in the per-speaker map must exist.

    Raises VoiceError naming the bad speaker/preset instead of
    silently dubbing a character with the wrong voice.
    """
    for speaker_id, preset in (config.speaker_voices or {}).items():
        if preset not in VOICE_PRESETS:
            raise VoiceError(
                f"speaker_voices[{speaker_id!r}] names unknown preset "
                f"{preset!r}; available: {sorted(VOICE_PRESETS)}")


def config_for_segment(config: VoiceConfig,
                       segment: ScriptSegment) -> VoiceConfig:
    """The effective voice config for one script segment.

    A segment whose speaker_id has a mapping uses that speaker's
    preset (voice + speed + style); the shared pronunciation
    dictionary and pause come from the base config. Segments with
    no speaker mapping use the base config unchanged — so the same
    speaker always gets the same voice across the video.
    """
    preset = (config.speaker_voices or {}).get(segment.speaker_id or "")
    if not preset:
        return config
    speaker_config = preset_config(preset)
    speaker_config.pronunciation_dictionary = config.pronunciation_dictionary
    speaker_config.pause_after_sec = config.pause_after_sec
    speaker_config.speaker_voices = config.speaker_voices
    return speaker_config


def validate_speed(speed: int) -> int:
    """Speed must stay in the natural 90–110 band for affiliate
    narration. Anything else is refused, not clamped silently."""
    if not MIN_SPEED <= int(speed) <= MAX_SPEED:
        raise VoiceError(
            f"voice_speed {speed} is outside the natural band "
            f"{MIN_SPEED}–{MAX_SPEED} — refusing to distort speech")
    return int(speed)


def apply_pronunciation(text: str, pronunciation: dict[str, str]) -> str:
    """Apply the pronunciation dictionary as literal replacements.

    Deterministic, longest-match-first, applied before synthesis so
    the spoken text stays traceable (the ORIGINAL text is preserved
    in the script record; this only affects the synthesized audio).
    """
    out = text
    for term in sorted(pronunciation, key=len, reverse=True):
        out = out.replace(term, pronunciation[term])
    return out


def _synthesize_one(text: str, voice: str, speed: int, out_mp3: Path) -> None:
    result = subprocess.run(
        [TTS_BIN, "speak", "--language", "vi", "--speed", str(speed),
         "--voice", voice, "--output", str(out_mp3), "--text-stdin"],
        input=text.encode("utf-8"), capture_output=True, timeout=180)
    if result.returncode != 0 or not out_mp3.exists() or out_mp3.stat().st_size < 1000:
        raise VoiceError(
            f"TTS failed (voice={voice}, speed={speed}): "
            f"{result.stderr.decode('utf-8', 'replace')[:300]}")


def _decode_to_wav(mp3: Path, wav: Path) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
         "-ac", "1", "-ar", "48000", str(wav)],
        capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not wav.exists():
        raise VoiceError(f"ffmpeg decode failed for {mp3}: {result.stderr[:300]}")


def synthesize_script(script: AffiliateScript, job_dir: Path, *,
                      config: VoiceConfig) -> list[Path]:
    """Synthesise one real WAV per approved script segment, in order.

    Requires ``script.approved`` — unapproved scripts are refused.
    Each segment is voiced with its speaker's voice when the segment
    carries a speaker_id mapped in ``config.speaker_voices``
    (per-character dubbing); otherwise the default voice applies.
    Returns WAV paths aligned with ``script.segments`` and fills
    ``measured_sec`` / ``voice_wav`` on each segment. Raises on any
    failure; partial results are left on disk for diagnosis.
    """
    if not script.approved:
        raise VoiceError("refusing TTS: the affiliate script has not "
                         "been approved by the user yet")
    if not script.segments:
        raise VoiceError("refusing TTS: the script has no segments")
    validate_speaker_voices(config)
    # Resolve (voice, speed) per segment: same speaker -> same voice.
    jobs: list[tuple[ScriptSegment, VoiceConfig, str, int]] = []
    for seg in script.segments:
        seg_config = config_for_segment(config, seg)
        jobs.append((seg, seg_config,
                     resolve_affiliate_voice(seg_config),
                     validate_speed(seg_config.voice_speed)))
    job_dir = Path(job_dir)
    voices_dir = job_dir / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)

    # Single-voice fast path: when every segment resolves to the same
    # voice at speed 100, reuse the shared provider exactly (it
    # synthesises at speed 100 with --language vi and measures WAVs)
    # — but ONLY when the provider's own speaker->voice mapping
    # resolves to the same voice id the config asks for.
    distinct = {(voice, speed) for _, _, voice, speed in jobs}
    first_config = jobs[0][1]
    voice, speed = jobs[0][2], jobs[0][3]
    from ..tts_cli_provider import voice_for
    speaker = (VOICE_PRESETS[first_config.preset]["speaker"]
               if first_config.preset in VOICE_PRESETS else "narrator")
    hint = (VOICE_PRESETS[first_config.preset]["voice_hint"]
            if first_config.preset in VOICE_PRESETS else "")
    use_shared_provider = (len(distinct) == 1 and speed == 100
                           and voice_for(speaker, hint) == voice)
    if use_shared_provider:
        lines = [TimelineLine(
            text=apply_pronunciation(seg.text, first_config.pronunciation_dictionary),
            speaker=speaker, kind="narration")
            for seg, _, _, _ in jobs]
        wavs = tts_cli_provider(lines, job_dir,
                                voice_hints={speaker: hint})
        # The provider names files lineNN_<speaker>.wav; re-home them
        # to segment ids so the timeline/mix stages can trace them.
        renamed: list[Path] = []
        for seg, wav in zip(script.segments, wavs):
            target = voices_dir / f"{seg.segment_id}.wav"
            if wav.resolve() != target.resolve():
                target.write_bytes(wav.read_bytes())
            else:
                target = wav
            seg.voice_wav = str(target)
            measured = measure_audio_duration(target)
            if measured is None:
                raise VoiceError(f"cannot measure TTS audio {target}")
            seg.measured_sec = round(measured, 3)
            renamed.append(target)
        return renamed

    # Per-segment path: same CLI, same decode chain, explicit voice
    # and speed per segment (multi-speaker dubbing / custom speed).
    wavs: list[Path] = []
    for seg, seg_config, seg_voice, seg_speed in jobs:
        text = apply_pronunciation(seg.text,
                                   seg_config.pronunciation_dictionary)
        mp3 = voices_dir / f"{seg.segment_id}.mp3"
        wav = voices_dir / f"{seg.segment_id}.wav"
        _synthesize_one(text, seg_voice, seg_speed, mp3)
        _decode_to_wav(mp3, wav)
        measured = measure_audio_duration(wav)
        if measured is None:
            raise VoiceError(f"cannot measure TTS audio {wav}")
        seg.voice_wav = str(wav)
        seg.measured_sec = round(measured, 3)
        wavs.append(wav)
    return wavs


def preview_voice(config: VoiceConfig, out_dir: Path) -> Path:
    """Synthesise the fixed preview phrase with the chosen voice.

    A REAL preview (the same CLI + decode chain), not a canned file.
    """
    voice = resolve_affiliate_voice(config)
    speed = validate_speed(config.voice_speed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3 = out_dir / "voice_preview.mp3"
    wav = out_dir / "voice_preview.wav"
    _synthesize_one(PREVIEW_TEXT, voice, speed, mp3)
    _decode_to_wav(mp3, wav)
    return wav
