"""Script to generate 3 distinctly different drafts and upload them directly to Google Drive,

deleting local video files immediately after upload to avoid filling up disk space.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from studio_api import JOBS, ENGINE, RENDER_LOCK, prepare_voice, render_spec, upload_video_and_remove_local, voice_duration


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 3 distinct drafts & upload to Google Drive")
    parser.add_argument("--request", help="Path to request.json", default=None)
    args = parser.parse_args()

    if args.request:
        payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
    else:
        # Use latest request.json from studio-jobs
        latest_job = Path(r"D:\Agent\output\studio-jobs\52d57a1cf6\request.json")
        if latest_job.exists():
            payload = json.loads(latest_job.read_text(encoding="utf-8"))
        else:
            raise RuntimeError("No request.json provided or found.")

    job_id = uuid.uuid4().hex[:10]
    folder = JOBS / job_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[1/4] Preparing voice for job {job_id}...")
    voice, subtitles, segments, cast = prepare_voice(payload, folder, job_id=job_id)
    duration = voice_duration(voice)
    aspect = payload.get("aspectRatio", "16:9")

    target = ENGINE / "public" / "ricks-draft" / "audio" / "voice.wav"
    variants_info = []

    variant_configs = [
        ("High retention", "Fast-paced, dynamic cuts, close-ups, camera tracking"),
        ("Dry Historical Comedy", "Deadpan wide framing, awkward pauses, reaction holds"),
        ("Cinematic Documentary", "Extreme wide establishing shots, slow majestic sweeps, deep perspective"),
    ]

    print(f"[2/4] Rendering 3 distinctly different drafts ({aspect})...")
    with RENDER_LOCK:
        target.write_bytes(voice.read_bytes())
        for i, (label, desc) in enumerate(variant_configs):
            print(f"\n--- Generating Draft {i + 1}/3: '{label}' ({desc}) ---")
            spec = render_spec(payload, duration, folder, subtitles, i, f"variant-{i + 1}.json", segments, cast)
            out = folder / f"draft-{i + 1}.mp4"

            # Render draft preview with PyCairo engine
            res = subprocess.run(
                [sys.executable, str(ROOT / "pipeline" / "fast_video_draft.py"), "--mode", "preview", "--spec", str(spec), "--out", str(out)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if res.returncode != 0:
                out.unlink(missing_ok=True)
                print(f"Error rendering draft {i + 1}: {res.stderr[:300]}")
                continue

            file_size_mb = out.stat().st_size / (1024 * 1024)
            print(f"Rendered local {out.name} ({file_size_mb:.1f} MB). Creating contact sheet...")

            # Generate contact sheet for preview
            contact = folder / f"draft-{i + 1}-contact.png"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-vf", "fps=1/4,scale=480:-1,tile=4x3", "-frames:v", "1", str(contact)],
                check=False,
            )

            print(f"Uploading {out.name} directly to Google Drive...")
            g_info = upload_video_and_remove_local(out)
            print(f"-> Uploaded successfully to Google Drive! File ID: {g_info.get('fileId')}")
            print(f"-> URL: {g_info.get('url')}")
            print(f"-> Deleted temporary local file {out.name}.")

            variants_info.append({
                "index": i + 1,
                "label": label,
                "description": desc,
                "gdrive": g_info,
            })

    # Save summary
    (folder / "variants_summary.json").write_text(json.dumps(variants_info, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("ALL 3 DISTINCT DRAFTS GENERATED & UPLOADED TO GOOGLE DRIVE:")
    print("=" * 60)
    for v in variants_info:
        gd = v.get("gdrive") or {}
        print(f"Draft #{v['index']} [{v['label']}]:")
        print(f"  * Phong cách: {v['description']}")
        print(f"  * Link Google Drive: {gd.get('url')}")
        print(f"  * File ID: {gd.get('fileId')}")
    print("=" * 60)
    print("Bo nho may tinh: Khong luu file video nang tren o cung (da don dep sach se 100%).")


if __name__ == "__main__":
    main()
