"""Chinese speech transcription (§10) — faster-whisper, Mandarin.

Runs the real faster-whisper engine from the project's venv
(``~/workspace/.venvs/whisper``, faster-whisper 1.2.1) as a
subprocess, because the system python does not have the package.
Models tiny/small/medium are already cached locally (Systran
faster-whisper builds); no download is attempted at runtime.

Rules:
  * Transcription is never fabricated: segments come only from the
    model. Silence / no-speech audio yields ``has_speech=False`` and
    an empty segment list — never invented words.
  * Word-level timestamps and VAD are enabled so the timeline and
    subtitle stages can align to real speech.
  * Outputs: ``source_transcript.json`` / ``.srt`` / ``.txt`` in the
    job directory, written by ``write_transcript_files``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

WHISPER_VENV_PYTHON = Path.home() / "workspace" / ".venvs" / "whisper" / "bin" / "python"
CACHED_MODELS = ("tiny", "small", "medium")
DEFAULT_MODEL = "small"

_ASR_SCRIPT = r'''
import json, sys, wave
import numpy as np
from faster_whisper import WhisperModel

# NOTE: the input must be a 16 kHz mono WAV loaded as a numpy array.
# Passing a file path makes faster-whisper 1.2.1 call av.open() with
# metadata_errors=..., which the installed PyAV 19.0.2 rejects
# (same workaround as acceptance_loop/transcribe_check.py).
wav_path, model_name, language = sys.argv[1], sys.argv[2], sys.argv[3]
with wave.open(wav_path, "rb") as wf:
    n, sr, ch, sw = (wf.getnframes(), wf.getframerate(),
                     wf.getnchannels(), wf.getsampwidth())
    raw = wf.readframes(n)
if sw == 2:
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
elif sw == 4:
    audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
else:
    raise ValueError(f"unsupported sample width {sw}")
if ch > 1:
    audio = audio.reshape(-1, ch).mean(axis=1)
assert sr == 16000, f"expected 16 kHz WAV, got {sr} Hz"
model = WhisperModel(model_name, device="cpu", compute_type="int8")
segments, info = model.transcribe(
    audio, language=language, beam_size=5,
    word_timestamps=True, vad_filter=True,
    vad_parameters={"min_silence_duration_ms": 500},
)
out = {"language": info.language,
       "language_probability": round(info.language_probability, 4),
       "duration": round(info.duration, 3),
       "segments": []}
for seg in segments:
    out["segments"].append({
        "start": round(seg.start, 3), "end": round(seg.end, 3),
        "text": seg.text.strip(),
        "avg_logprob": round(seg.avg_logprob, 4),
        "no_speech_prob": round(seg.no_speech_prob, 4),
        "words": [{"start": round(w.start, 3), "end": round(w.end, 3),
                   "word": w.word, "probability": round(w.probability, 4)}
                  for w in (seg.words or [])],
    })
print(json.dumps(out, ensure_ascii=False))
'''


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    words: list[dict] = field(default_factory=list)
    # Speaker label for per-character dubbing. faster-whisper has no
    # diarization, so the default is a single labelled speaker; real
    # multi-speaker labels come from assign_speakers() (explicit user
    # ranges) or a diarization backend (see diarize_with_pyannote).
    speaker_id: str = "SPEAKER_00"

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "text": self.text,
                "avg_logprob": self.avg_logprob,
                "no_speech_prob": self.no_speech_prob, "words": self.words,
                "speaker_id": self.speaker_id}


@dataclass
class Transcript:
    language: str
    language_probability: float
    duration_sec: float
    segments: list[TranscriptSegment] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    source_path: str = ""
    # How speaker labels were produced: "single" (one labelled
    # speaker, the honest default), "manual" (user-supplied ranges),
    # or "pyannote" (diarization backend, when available).
    speaker_method: str = "single"

    @property
    def has_speech(self) -> bool:
        return any(seg.text.strip() for seg in self.segments)

    @property
    def speakers(self) -> list[str]:
        """Distinct speaker labels in first-appearance order."""
        seen: list[str] = []
        for seg in self.segments:
            if seg.speaker_id not in seen:
                seen.append(seg.speaker_id)
        return seen

    @property
    def full_text(self) -> str:
        return "".join(seg.text for seg in self.segments).strip()

    def to_dict(self) -> dict:
        return {"language": self.language,
                "language_probability": self.language_probability,
                "duration_sec": self.duration_sec,
                "model": self.model, "source_path": self.source_path,
                "speaker_method": self.speaker_method,
                "speakers": self.speakers,
                "has_speech": self.has_speech,
                "segments": [s.to_dict() for s in self.segments]}


def _python_with_whisper() -> str:
    """Prefer the project venv python; fall back to sys.executable
    only if it can import faster_whisper (checked by the caller)."""
    if WHISPER_VENV_PYTHON.exists():
        return str(WHISPER_VENV_PYTHON)
    return sys.executable


def extract_audio_for_asr(video_path: Path, out_dir: Path) -> Path:
    """Extract 16 kHz mono WAV for ASR. Raises on failure."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "asr_input.wav"
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video_path),
         "-vn", "-ac", "1", "-ar", "16000", str(wav)],
        capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not wav.exists():
        raise RuntimeError(f"audio extraction failed for {video_path}: "
                           f"{result.stderr[:300]}")
    return wav


def transcribe_chinese(audio_path: Path, *, model: str = DEFAULT_MODEL,
                       language: str = "zh",
                       timeout_sec: int = 600) -> Transcript:
    """Transcribe Mandarin speech from an audio/video file.

    The input is first normalized to 16 kHz mono WAV with ffmpeg
    (any container/codec ffmpeg reads), then passed to
    faster-whisper as a numpy array. ``model`` must be one of the
    locally cached models (tiny/small/medium) so no network
    download is needed at runtime.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"audio file not found: {audio_path}")
    if model not in CACHED_MODELS:
        raise ValueError(f"model {model!r} is not cached locally; "
                         f"cached models: {list(CACHED_MODELS)}")
    python = _python_with_whisper()
    with tempfile.TemporaryDirectory(prefix="affiliate_asr_") as tmp:
        wav = extract_audio_for_asr(audio_path, Path(tmp))
        script_path = Path(tmp) / "asr_worker.py"
        script_path.write_text(_ASR_SCRIPT, encoding="utf-8")
        result = subprocess.run(
            [python, str(script_path), str(wav), model, language],
            capture_output=True, text=True, timeout=timeout_sec)
    if result.returncode != 0:
        raise RuntimeError(f"faster-whisper failed: "
                           f"{result.stderr.strip()[-500:]}")
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    return Transcript(
        language=str(payload.get("language", language)),
        language_probability=float(payload.get("language_probability", 0.0)),
        duration_sec=float(payload.get("duration", 0.0)),
        segments=[TranscriptSegment(
            start=float(s["start"]), end=float(s["end"]),
            text=str(s.get("text", "")),
            avg_logprob=float(s.get("avg_logprob", 0.0)),
            no_speech_prob=float(s.get("no_speech_prob", 0.0)),
            words=list(s.get("words", [])))
            for s in payload.get("segments", [])],
        model=model,
        source_path=str(audio_path),
    )


def _srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def transcript_to_srt(transcript: Transcript) -> str:
    """SRT rendering of the real segments (empty when no speech).

    When the transcript has more than one speaker, each cue is
    prefixed with its speaker label so the dubbing review can tell
    the characters apart.
    """
    multi = len(transcript.speakers) > 1
    chunks = []
    for i, seg in enumerate(transcript.segments, 1):
        if not seg.text.strip():
            continue
        text = seg.text.strip()
        if multi:
            text = f"[{seg.speaker_id}] {text}"
        chunks.append(f"{i}\n{_srt_timestamp(seg.start)} --> "
                      f"{_srt_timestamp(seg.end)}\n{text}\n")
    return "\n".join(chunks)


def write_transcript_files(transcript: Transcript, out_dir: Path) -> dict[str, Path]:
    """Write source_transcript.json / .srt / .txt. Returns paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    json_path = out_dir / "source_transcript.json"
    json_path.write_text(json.dumps(transcript.to_dict(), ensure_ascii=False,
                                    indent=2), encoding="utf-8")
    paths["json"] = json_path
    srt_path = out_dir / "source_transcript.srt"
    srt_path.write_text(transcript_to_srt(transcript), encoding="utf-8")
    paths["srt"] = srt_path
    txt_path = out_dir / "source_transcript.txt"
    txt_path.write_text(transcript.full_text + "\n", encoding="utf-8")
    paths["txt"] = txt_path
    return paths


class DiarizationError(RuntimeError):
    """Raised when speaker diarization was requested but no backend
    is available. Never silently replaced by invented speakers."""


def diarization_available() -> bool:
    """True when a diarization backend (pyannote.audio) is importable
    in THIS interpreter. The ASR worker runs in the whisper venv, so
    integration must check there too."""
    try:
        import pyannote.audio  # noqa: F401
        return True
    except ImportError:
        return False


def diarize_with_pyannote(audio_path: Path, transcript: Transcript,
                          *, hf_token: str = "") -> Transcript:
    """Speaker-diarize with pyannote.audio (NOT installed here).

    Raises DiarizationError naming the missing dependency instead of
    fabricating speaker labels. When pyannote IS installed, this is
    the seam: run the pipeline, then apply its turns with
    ``assign_speakers`` (method "pyannote").
    """
    if not diarization_available():
        raise DiarizationError(
            "pyannote.audio is not installed, so automatic speaker "
            "diarization is unavailable. Install it "
            "(pip install pyannote-audio) with a Hugging Face token "
            "for a diarization model, or use assign_speakers() with "
            "explicit user-supplied speaker ranges instead.")
    raise DiarizationError(
        "pyannote.audio is importable but no diarization pipeline "
        "is wired yet — wire one here before claiming diarization.")


def assign_speakers(transcript: Transcript,
                    ranges: list[dict]) -> dict:
    """Assign speaker labels from explicit user-supplied ranges.

    ``ranges`` is a list of {start, end, speaker_id}. A segment takes
    the speaker of the range covering its midpoint; segments outside
    every range keep SPEAKER_00. Sets ``speaker_method="manual"``.
    Returns {assigned, total, speakers}. Raises ValueError on
    malformed ranges — speaker labels are user data, never guessed.
    """
    parsed = []
    for i, r in enumerate(ranges):
        try:
            start, end = float(r["start"]), float(r["end"])
            speaker = str(r["speaker_id"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"speaker range [{i}] needs start/end/"
                             f"speaker_id: {exc}") from exc
        if not speaker or end <= start or start < 0:
            raise ValueError(
                f"speaker range [{i}] is invalid: {r!r}")
        parsed.append((start, end, speaker))
    assigned = 0
    for seg in transcript.segments:
        midpoint = (seg.start + seg.end) / 2
        for start, end, speaker in parsed:
            if start <= midpoint < end:
                seg.speaker_id = speaker
                assigned += 1
                break
    transcript.speaker_method = "manual"
    return {"assigned": assigned, "total": len(transcript.segments),
            "speakers": transcript.speakers}


def transcript_from_dict(payload: dict) -> Transcript:
    """Rebuild a Transcript from a stored source_transcript.json."""
    segments = [TranscriptSegment(
        start=float(s["start"]), end=float(s["end"]),
        text=str(s.get("text", "")),
        avg_logprob=float(s.get("avg_logprob", 0.0)),
        no_speech_prob=float(s.get("no_speech_prob", 0.0)),
        words=list(s.get("words", [])),
        speaker_id=str(s.get("speaker_id", "SPEAKER_00")))
        for s in payload.get("segments", [])]
    return Transcript(
        language=str(payload.get("language", "")),
        language_probability=float(payload.get("language_probability", 0.0)),
        duration_sec=float(payload.get("duration_sec", 0.0)),
        segments=segments,
        model=str(payload.get("model", DEFAULT_MODEL)),
        source_path=str(payload.get("source_path", "")),
        speaker_method=str(payload.get("speaker_method", "single")))
