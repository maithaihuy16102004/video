"""Voice audition packs (round-2 system 8).

A waveform never proves a voice sounds natural. The only honest voice
check is a human listening. This module builds a listenable pack from
a COMPLETED job: one sample per speaking voice -- the exact normalised
WAV the draft used for that speaker's first line, converted to MP3 --
plus a listening sheet that states the facts (speaker, script
VOICE_ID, engine voice, reuse) and asks Mai to judge.

The pack is built FROM a job, never re-synthesised: re-synthesis
could differ from the shipped audio, and the pack must contain
exactly what the viewer hears. It is not a pipeline stage -- the
loop builds it after a job completes -- so no job behaviour changes.

No score is computed here. Loudness, RMS and duration are reported
as measurements only; naturalness, pronunciation and fit are Mai's
judgement, recorded by her reply, never by a number in this module.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class AuditionError(RuntimeError):
    """The pack cannot be built honestly from this job."""


def _first_lines_by_speaker(timeline_lines, speakers):
    """First timeline line per speaker, in manifest speaker order."""
    first = {}
    for line in timeline_lines:
        speaker = line.get("speaker")
        if speaker in speakers and speaker not in first:
            first[speaker] = line
    missing = [s for s in speakers if s not in first]
    if missing:
        raise AuditionError(
            f"no timeline line for speaker(s): {', '.join(missing)}")
    return [first[s] for s in speakers]


def _resolve_wav(job_dir: Path, line: dict) -> Path:
    """The line's WAV: the recorded path, else the voices/ glob."""
    recorded = line.get("wav")
    if recorded:
        candidate = Path(recorded)
        if candidate.exists():
            return candidate
    speaker = line.get("speaker", "")
    index = line.get("line_index", line.get("line", 0))
    globbed = sorted((job_dir / "voices").glob(
        f"line{int(index):02d}_{speaker}.wav"))
    if globbed:
        return globbed[0]
    raise AuditionError(
        f"no WAV found for line {index} ({speaker}); refusing to "
        f"substitute audio")


def _wav_to_mp3(wav: Path, mp3: Path) -> float:
    """Convert the normalised WAV to a preview-friendly MP3.

    Returns the MP3 duration in seconds (ffprobe). The conversion
    must preserve duration: a truncated sample would misrepresent
    the voice.
    """
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(wav),
         "-codec:a", "libmp3lame", "-q:a", "3", str(mp3)],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not mp3.exists():
        raise AuditionError(
            f"MP3 conversion failed for {wav.name}: {r.stderr[:200]}")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "csv=p=0", str(mp3)],
        capture_output=True, text=True, timeout=30)
    try:
        return float(probe.stdout.strip().split(",")[0])
    except (ValueError, IndexError):
        raise AuditionError(f"could not probe {mp3.name}")


def _sheet(project_id, job_id, manifest, samples, warnings):
    lines = [
        f"# Voice audition — {project_id}",
        "",
        f"Job: `{job_id}`. Engine: {manifest.get('engine', '(unknown)')}.",
        "",
        "Nghe từng file MP3 bên dưới và cho biết: giọng có tự nhiên",
        "không? Có đúng giới tính / độ tuổi của nhân vật không? Có",
        "từ nào phát âm sai không? Không có điểm số ở đây — sóng âm",
        "không chứng minh được giọng tự nhiên. Mai là người chấm.",
        "",
    ]
    if warnings:
        lines += ["## Cảnh báo dùng chung giọng (reuse)", ""]
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    else:
        lines += ["Không có reuse: mỗi người nói dùng một giọng riêng.",
                  ""]
    lines += [f"Tổng số giọng riêng biệt: "
              f"{manifest.get('distinct_voices_used', '?')}.", ""]
    for i, s in enumerate(samples, 1):
        lines += [
            f"## {i}. {s['speaker']} — `{s['mp3_name']}`",
            "",
            f"- Script VOICE_ID: `{s['script_voice_id'] or '(none)'}`",
            f"- Giọng máy (VM): `{s['voice']}`",
            f"- Gợi ý giọng: {s['voice_hint'] or '(none)'}",
            f"- Dòng mẫu: dòng {s['line_index']} "
            f"({s['kind']}, {s['duration_sec']:.2f}s)",
            f"- Lời thoại: {s['text']}",
            "",
        ]
    lines += [
        "---",
        "",
        manifest.get("engine_note", ""),
        "",
        "Các file MP3 là bản chuyển đổi trực tiếp từ file WAV đã",
        "chuẩn hoá âm lượng mà bản draft dùng — đúng thứ người xem",
        "nghe thấy. Không tổng hợp lại, không thay thế.",
        "",
    ]
    return "\n".join(lines)


def build_audition_from_job(job_dir, out_dir, *, project_id=None):
    """Build the audition pack for one completed job.

    ``job_dir`` must hold ``voices_manifest.json`` and
    ``timeline.json``; ``out_dir`` receives one MP3 per speaker,
    ``AUDITION.md`` and ``audition_manifest.json``. Returns the
    manifest dict. Raises AuditionError rather than substituting
    or omitting audio.
    """
    job_dir = Path(job_dir)
    out_dir = Path(out_dir)
    manifest_path = job_dir / "voices_manifest.json"
    timeline_path = job_dir / "timeline.json"
    if not manifest_path.exists():
        raise AuditionError(
            f"{job_dir} has no voices_manifest.json -- the voice "
            f"record is required; refusing to guess voices")
    if not timeline_path.exists():
        raise AuditionError(f"{job_dir} has no timeline.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    speakers = manifest.get("speakers") or []
    if not speakers:
        raise AuditionError("voices manifest lists no speakers")
    assignment = manifest.get("assignment") or {}
    chosen = _first_lines_by_speaker(timeline.get("lines") or [],
                                     speakers)
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for i, line in enumerate(chosen, 1):
        speaker = line["speaker"]
        wav = _resolve_wav(job_dir, line)
        safe = "".join(c if c.isalnum() or c in "-_" else "_"
                       for c in speaker)
        mp3_name = f"{i:02d}_{safe}.mp3"
        mp3 = out_dir / mp3_name
        duration = _wav_to_mp3(wav, mp3)
        expected = float(line.get("duration") or duration)
        if abs(duration - expected) > 0.15:
            raise AuditionError(
                f"{mp3_name} duration {duration:.2f}s != line "
                f"duration {expected:.2f}s -- refusing a truncated "
                f"sample")
        info = assignment.get(speaker) or {}
        samples.append({
            "speaker": speaker,
            "script_voice_id": info.get("script_voice_id", ""),
            "voice": info.get("voice", ""),
            "voice_hint": info.get("voice_hint", ""),
            "gender": info.get("gender", ""),
            "line_index": line.get("line_index", line.get("line")),
            "kind": line.get("kind", ""),
            "text": line.get("text", ""),
            "source_wav": str(wav),
            "mp3_name": mp3_name,
            "duration_sec": round(duration, 3),
        })
    warnings = list(manifest.get("reuse_warnings") or [])
    pid = project_id or job_dir.name
    (out_dir / "AUDITION.md").write_text(
        _sheet(pid, job_dir.name, manifest, samples, warnings),
        encoding="utf-8")
    record = {
        "project_id": pid,
        "job_id": job_dir.name,
        "engine": manifest.get("engine", ""),
        "distinct_voices_used": manifest.get("distinct_voices_used"),
        "reuse_warnings": warnings,
        "samples": samples,
    }
    (out_dir / "audition_manifest.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return record
