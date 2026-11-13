"""Voice provider backed by the /opt/hatch/bin/tts CLI (shared engine).

Production wants VieNeu-TTS (stage 9), but the `vieneu` package is not
installed on this Linux VM — so the provider synthesises real Vietnamese
speech with the same CLI the v3/v4 narrations used, and the orchestrator
records it as an injected provider. On Mai's Windows machine the real
VieNeu provider replaces this without changing the pipeline: it maps the
script's VOICE_IDs directly to VieNeu voices.

P8 (visual recovery): every job records a voices manifest
(job_dir/voices_manifest.json) stating the actual engine, the voice used
for every line, the script VOICE_ID behind it, and the loudness
normalisation applied. No voice substitution is ever silent: when two
characters share one VM voice, the manifest says so, with the reason.

Voice assignment (VM stand-in only): speakers are grouped by the gender
of their voice_hint, and distinct script VOICE_IDs within a group get
distinct CLI voices from a small pool of KNOWN voices (the CLI exposes
no voice list, so no ID outside this pool is ever invented). When a
group has more distinct VOICE_IDs than pool voices, voices are reused
and the reuse is recorded as a warning in the manifest. The narrator
voice is reserved for an actual narrator speaker; first-person scripts
have none, so the voice stays in the pool.

Each line is synthesised at speed 100 (1.00x, never sped up) with
--language vi, decoded to 48 kHz mono WAV, RMS-normalised to the voice
target (peak-guarded, never clipped), and measured. Returns exactly one
WAV per input line, in order.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

TTS_BIN = "/opt/hatch/bin/tts"
NARRATOR_VOICE = "avocado_v2:MAI_01"
MALE_VOICE = "avocado_v2:ronan"
FEMALE_VOICE = "avocado_v2:paloma"
DEFAULT_VOICE = "avocado_v2:MAI_03"

#: Known CLI voices only (the CLI exposes no voice list). Pools are
#: ordered by first-seen assignment; the narrator voice joins the
#: female pool only when no narrator speaker exists (first-person
#: scripts), so a narrator never shares a voice with a character.
MALE_POOL = (MALE_VOICE, DEFAULT_VOICE)
FEMALE_POOL = (FEMALE_VOICE, NARRATOR_VOICE)
UNKNOWN_POOL = (DEFAULT_VOICE, MALE_VOICE, FEMALE_VOICE, NARRATOR_VOICE)

ENGINE_LABEL = ("tts_cli (/opt/hatch/bin/tts, Meta Shortwave) — "
                "VM stand-in, NOT VieNeu-TTS")

#: Voice loudness target (ffmpeg volumedetect mean_volume) + guards.
VOICE_TARGET_DB = -20.0
VOICE_MAX_GAIN_DB = 12.0
VOICE_PEAK_CEILING_DB = -1.0


def _gender_of_hint(voice_hint: str = "") -> str:
    """'female' | 'male' | 'unknown' from a voice hint.

    Female is checked FIRST: a bare "nam" substring misfires on
    "giọng nữ miền Nam" (southern female voice). Male fires only on
    the explicit phrase "giọng nam", the word "nam" alone, or male
    markers — never on a bare "nam" substring ("Việt Nam", "năm").
    derive_voice_hint returns exactly "giọng nam" / "giọng nữ" / "",
    so the phrase checks cover every adapter-produced hint.
    """
    hint = (voice_hint or "").lower()
    if "nữ" in hint or "female" in hint or "giọng chị" in hint:
        return "female"
    if ("giọng nam" in hint or "nam tính" in hint
            or "đàn ông" in hint or "male" in hint
            or hint.strip() == "nam"):
        return "male"
    return "unknown"


def voice_for(speaker: str, voice_hint: str = "") -> str:
    """Single-voice resolution (backward compatible).

    Prefer resolve_voice_assignment for multi-speaker jobs: it keeps
    distinct script voices distinct instead of collapsing every male
    speaker onto one voice.
    """
    if speaker == "narrator":
        return NARRATOR_VOICE
    gender = _gender_of_hint(voice_hint)
    if gender == "female":
        return FEMALE_VOICE
    if gender == "male":
        return MALE_VOICE
    return DEFAULT_VOICE


def resolve_voice_assignment(speakers, *, voice_hints=None,
                             voice_ids=None):
    """Assign one CLI voice per speaker, keeping distinct script
    VOICE_IDs distinct within each gender group.

    ``speakers`` is the first-seen order of speaker names (line order).
    Returns (assignment, warnings): assignment maps speaker ->
    {"voice", "script_voice_id", "voice_hint", "gender"}; warnings
    lists every voice reuse (pool exhausted) in plain language.
    Deterministic: same inputs, same assignment.
    """
    hints = voice_hints or {}
    ids = voice_ids or {}
    has_narrator = "narrator" in speakers
    pools = {
        "male": list(MALE_POOL),
        "female": [v for v in FEMALE_POOL
                   if not (has_narrator and v == NARRATOR_VOICE)],
        "unknown": [v for v in UNKNOWN_POOL
                    if not (has_narrator and v == NARRATOR_VOICE)],
    }
    used: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {}
    warnings: list[str] = []
    assignment: dict[str, dict] = {}
    for speaker in speakers:
        if speaker == "narrator":
            assignment[speaker] = {
                "voice": NARRATOR_VOICE, "script_voice_id": "",
                "voice_hint": hints.get(speaker, ""), "gender": "narrator"}
            continue
        hint = hints.get(speaker, "")
        gender = _gender_of_hint(hint)
        script_id = str(ids.get(speaker) or "")
        key = (gender, script_id or speaker)
        if key in used:
            voice = used[key]
        else:
            pool = pools[gender]
            slot = counters.get(gender, 0)
            counters[gender] = slot + 1
            voice = pool[slot % len(pool)]
            if slot >= len(pool):
                warnings.append(
                    f"voice reuse: {speaker} (VOICE_ID "
                    f"{script_id or '(none)'}) shares {voice} with "
                    f"another {gender} voice — the VM pool holds "
                    f"{len(pool)} {gender} voices; the VieNeu "
                    f"provider maps VOICE_IDs directly")
            used[key] = voice
        assignment[speaker] = {
            "voice": voice, "script_voice_id": script_id,
            "voice_hint": hint, "gender": gender}
    return assignment, warnings


def _wav_levels(path: Path) -> tuple[float | None, float | None]:
    """(mean_volume dB, max_volume dB) via ffmpeg volumedetect."""
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vn",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    mean_db = None
    max_db = None
    for line in (r.stderr or "").splitlines():
        m = re.search(r"mean_volume:\s*(-?[\d.]+|-\s*inf)", line)
        if m:
            try:
                mean_db = float(m.group(1))
            except ValueError:
                mean_db = -120.0
        m = re.search(r"max_volume:\s*(-?[\d.]+|-\s*inf)", line)
        if m:
            try:
                max_db = float(m.group(1))
            except ValueError:
                max_db = -120.0
    return mean_db, max_db


def _normalize_wav(path: Path, *, target_db: float = VOICE_TARGET_DB,
                   max_gain_db: float = VOICE_MAX_GAIN_DB,
                   peak_ceiling_db: float = VOICE_PEAK_CEILING_DB
                   ) -> dict:
    """RMS-normalise one WAV to ``target_db`` mean volume.

    Gain is capped at ``max_gain_db`` and reduced when the peak would
    exceed ``peak_ceiling_db`` (never clipped). Silence (mean -120)
    is left untouched and reported. Returns the measurement record;
    the file is rewritten in place only when |gain| >= 0.1 dB.
    """
    mean_db, max_db = _wav_levels(path)
    record = {"mean_db_before": mean_db, "max_db_before": max_db,
              "gain_db": 0.0, "capped": False, "target_db": target_db}
    if mean_db is None or mean_db <= -90.0:
        # volumedetect reports digital silence as -91.0 dB (its
        # 16-bit floor), not -inf; anything at/below -90 dB mean is
        # effectively silent and must never be amplified.
        record["note"] = "silence or unreadable levels; left untouched"
        return record
    gain = target_db - mean_db
    if gain > max_gain_db:
        gain = max_gain_db
        record["capped"] = True
    if max_db is not None:
        headroom = peak_ceiling_db - max_db
        if gain > headroom:
            gain = headroom
            record["capped"] = True
    if abs(gain) < 0.1:
        record["mean_db_after"] = mean_db
        record["max_db_after"] = max_db
        return record
    tmp = path.with_suffix(".norm.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path),
         "-af", f"volume={10.0 ** (gain / 20.0):.6f}",
         "-ac", "1", "-ar", "48000", str(tmp)],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not tmp.exists():
        raise RuntimeError(f"voice normalisation failed: {r.stderr[:300]}")
    tmp.replace(path)
    mean_after, max_after = _wav_levels(path)
    record.update({"gain_db": round(gain, 2),
                   "mean_db_after": mean_after,
                   "max_db_after": max_after})
    return record


def tts_cli_provider(lines, job_dir: Path, *,
                     voice_hints: dict[str, str] | None = None,
                     voice_ids: dict[str, str] | None = None
                     ) -> list[Path]:
    """Synthesise one real WAV per line. `lines` are TimelineLine objects
    (or dicts with text/speaker). Raises on any failure — never returns a
    silent placeholder. Writes job_dir/voices_manifest.json (P8)."""
    job_dir = Path(job_dir)
    out_dir = job_dir / "voices"
    out_dir.mkdir(parents=True, exist_ok=True)
    hints = voice_hints or {}
    ids = voice_ids or {}
    parsed = []
    speakers: list[str] = []
    for line in lines:
        if isinstance(line, dict):
            text = line["text"]
            speaker = line.get("speaker", "narrator")
        else:  # TimelineLine dataclass
            text = line.text
            speaker = line.speaker
        parsed.append((text, speaker))
        if speaker not in speakers:
            speakers.append(speaker)
    assignment, warnings = resolve_voice_assignment(
        speakers, voice_hints=hints, voice_ids=ids)
    wavs: list[Path] = []
    line_records = []
    for i, (text, speaker) in enumerate(parsed, 1):
        voice = assignment[speaker]["voice"]
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
        norm = _normalize_wav(wav)
        wavs.append(wav)
        line_records.append({
            "line": i, "speaker": speaker,
            "voice": voice,
            "script_voice_id": assignment[speaker]["script_voice_id"],
            "voice_hint": assignment[speaker]["voice_hint"],
            "wav": str(wav), "normalisation": norm})
    manifest = {
        "engine": ENGINE_LABEL,
        "engine_note": ("The VM stand-in synthesises Vietnamese via the "
                        "shared TTS CLI. On Mai's Windows machine the "
                        "VieNeu provider replaces this module and maps "
                        "each script VOICE_ID to its VieNeu voice "
                        "directly; the script_voice_id column is the "
                        "key that mapping uses."),
        "assignment": assignment,
        "reuse_warnings": warnings,
        "distinct_voices_used": len({a["voice"]
                                     for a in assignment.values()}),
        "speakers": speakers,
        "lines": line_records,
        "normalisation_target_db": VOICE_TARGET_DB,
    }
    (job_dir / "voices_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return wavs
