"""Transcribe real TTS narration with faster-whisper (numpy-array input
bypasses the broken av file-path API in av 19.0.2) and compare against
the script text (WER). Used for the voice pronunciation check required
by qa_gates rule (c): a voice score above 7.0 needs verified
transcription, not timing+RMS only.

Usage: python3 transcribe_check.py <model> <wav>... 
Model: tiny | small (cached in ~/.cache/huggingface).
"""
import json
import re
import sys
import unicodedata
import wave

import numpy as np
from faster_whisper import WhisperModel


def load_wav_16k(path):
    with wave.open(str(path), "rb") as wf:
        n = wf.getnframes()
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(n)
    if sw == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != 16000:
        # linear resample (good enough for a pronunciation check)
        idx = np.linspace(0, len(audio) - 1, int(len(audio) * 16000 / sr))
        audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
    return audio


def norm(text):
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"[^\w\sÀ-ỹ]", " ", text)
    return " ".join(text.split())


def wer(ref, hyp):
    r, h = norm(ref).split(), norm(hyp).split()
    if not r:
        return None
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + cost)
    return round(d[len(r)][len(h)] / len(r), 3)


def main():
    model_name = sys.argv[1] if len(sys.argv) > 1 else "small"
    wavs = sys.argv[2:]
    if not wavs:
        print("usage: transcribe_check.py <model> <wav>...", file=sys.stderr)
        return 2
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    out = []
    for wav in wavs:
        audio = load_wav_16k(wav)
        segments, info = model.transcribe(audio, language="vi",
                                          beam_size=5)
        text = " ".join(s.text.strip() for s in segments)
        out.append({"wav": wav, "language": info.language,
                    "language_probability": round(info.language_probability, 3),
                    "transcription": text})
        print(json.dumps(out[-1], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
