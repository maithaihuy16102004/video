"""Build, Render, Verify, and Upload Documentary Blob-Head 16:9 Widescreen Full HD (1920x1080) Draft.

Stack: Motion Canvas + Three.js + Stickman Rig (Documentary Blob-Head Look)
Target: 1920x1080 @ 24fps | YouTube Loudness Normalization (-14.0 LUFS) | H.264+AAC
Drive Folder: 184s_VkSeauebGwyIshIyBFlVhW7GWN82
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "output" / "blob_head_16x9"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DRIVE_FOLDER_ID = "184s_VkSeauebGwyIshIyBFlVhW7GWN82"


def get_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def upload_to_drive(filepath: Path, parent_id: str) -> dict:
    file_size = filepath.stat().st_size
    sha256_hash = get_sha256(filepath)
    filename = filepath.name

    print(f"Uploading {filename} ({file_size / (1024*1024):.2f} MB) to Google Drive...", flush=True)
    cmd = f'gdrive mutate upload "{filepath}" --parent {parent_id}'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    drive_id = ""
    status = "SUCCESS" if res.returncode == 0 else "FAILED"
    for line in res.stdout.splitlines():
        if "Uploaded" in line or "Created" in line or "ID:" in line:
            parts = line.split("ID:")
            if len(parts) > 1:
                drive_id = parts[1].strip().rstrip(")")
            elif "(" in line and ")" in line:
                drive_id = line[line.rfind("(") + 1 : line.rfind(")")].replace("ID:", "").strip()

    if not drive_id and res.returncode == 0:
        q_cmd = f"gdrive readonly ls {parent_id} --json"
        q_res = subprocess.run(q_cmd, shell=True, capture_output=True, text=True)
        try:
            items = json.loads(q_res.stdout)
            for it in items:
                if it.get("name") == filename:
                    drive_id = it.get("id")
                    break
        except Exception:
            pass

    record = {
        "filename": filename,
        "local_path": str(filepath),
        "size_bytes": file_size,
        "sha256": sha256_hash,
        "drive_folder_id": parent_id,
        "drive_file_id": drive_id,
        "url": f"https://drive.google.com/file/d/{drive_id}/view" if drive_id else "",
        "status": status,
    }
    print(f"  -> Uploaded ID: {drive_id} (Status: {status}) | URL: {record['url']}", flush=True)
    return record


def build_documentary_blob_head_16x9_package() -> dict:
    """Builds the 16:9 Widescreen Full HD (1920x1080) Documentary Blob-Head Scene Package."""
    pkg = {
        "project_id": "v51_blob_head_documentary_16x9_draft",
        "sequence_id": "v51_blob_head_documentary_16x9_draft",
        "total_sequence_duration_seconds": 15.0,
        "aspect_ratio": "16:9",
        "width": 1920,
        "height": 1080,
        "fps": 24,
        "visual_style": "documentary_blob_head",
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "canonical_name": "Edo Wooden Bridge Canal (Cầu Gỗ Mục Mùa Mưa 16:9)",
            "architecture_style": "TRADITIONAL_EAST_ASIAN",
            "weather": "RAIN",
            "lighting_behavior": "WARM_DIRECT",
            "composition": "standard",
            "threejs_environment": {
                # 16:9 Widescreen camera: Elevated Y=4.45m, Target Y=4.95m preserves >= 60% open sky
                # Lateral tracking pan from X=-1.8m to X=-0.6m across the 16:9 frame
                "camera_initial": {
                    "position": [-1.8, 4.45, 6.8],
                    "target": [0.1, 4.95, 0.0],
                    "fov": 44,
                },
                "camera_keyframes": [
                    {"t": 0.0, "position": [-1.8, 4.45, 6.8], "target": [0.1, 4.95, 0.0]},
                    {"t": 7.5, "position": [-1.2, 4.40, 6.4], "target": [0.15, 4.90, 0.0]},
                    {"t": 15.0, "position": [-0.6, 4.35, 6.0], "target": [0.2, 4.85, 0.0]},
                ],
            },
        },
        "actors": [
            {
                "actor_id": "haru",
                "role": "LEAD",
                "dna": {
                    "id": "haru",
                    "name": "Haru",
                    "visualStyle": "documentary_blob_head",
                    "proportions": {
                        "headRatio": 0.42,  # Oversized round head (~42% of total height)
                        "standingHeightPx": 280,
                        "shoulderWidthPx": 42,
                        "limbThicknessPx": 8.0,  # Thin simplified body
                        "torsoLengthPx": 80,
                        "legLengthPx": 80,
                    },
                    "face": {
                        "headContour": "round_youth",
                        "skinTone": "#F5DEB3",  # Flat unshaded skin
                        "eyeType": "dot_minimal",
                        "eyeColor": "#181412",
                        "eyebrowStyle": "single_thin_line",
                        "facialHair": "none",
                    },
                    "hair": {
                        "style": "edo_topknot",
                        "color": "#181412",
                        "accessory": "paper_cord",
                    },
                    "costume": {
                        "archetype": "edo_hanten_courier",
                        "primaryColor": "#264653",
                        "accentColor": "#E76F51",
                        "pantsColor": "#1D3557",
                        "footwear": "waraji_sandals",
                    },
                    "heldProps": {
                        "rightHand": "letter_envelope",
                    },
                },
                "staging": {
                    "initial_world_pos": [-1.4, 2.65, 0.0],  # Staged on left third (16:9 width)
                    "facing": "RIGHT",
                    "posture": "stand",
                },
                # Minimum motion requirement: acting cues every 2-3s, 0 hold > 3.0s
                "performance_cues": [
                    {"time": 0.0, "pos": [-1.4, 2.65, 0.0], "action": "walk", "emotion": "determined", "facing": 1},
                    {"time": 2.2, "pos": [-1.4, 2.65, 0.0], "action": "hold", "emotion": "determined", "facing": 1},
                    {"time": 4.5, "pos": [-1.4, 2.65, 0.0], "action": "speak_gestural", "emotion": "focused", "facing": 1},
                    {"time": 6.8, "pos": [-1.4, 2.65, 0.0], "action": "point", "emotion": "intense", "facing": 1},
                    {"time": 9.2, "pos": [-1.4, 2.65, 0.0], "action": "speak", "emotion": "determined", "facing": 1},
                    {"time": 11.8, "pos": [-1.4, 2.65, 0.0], "action": "present_two_handed", "emotion": "confident", "facing": 1},
                    {"time": 14.0, "pos": [-1.4, 2.65, 0.0], "action": "idle", "emotion": "relief", "facing": 1},
                ],
            }
        ],
        "storyBeats": [
            {
                "beatId": "BEAT_01",
                "timeRange": [0.0, 4.5],
                "primaryVerb": "walk",
                "whatHappens": "Haru vượt qua mưa lũ trên cầu gỗ, bước đi quả cảm.",
                "shotType": "FULL_SHOT",
                "emotion": "determined",
                "dialogue": {
                    "speaker": "Haru",
                    "text": "Đến cây cầu bắc qua kênh, tôi nhận ra một vấn đề lớn...",
                    "voiceId": "vieneu-Thiện Minh",
                },
            },
            {
                "beatId": "BEAT_02",
                "timeRange": [4.5, 9.5],
                "primaryVerb": "speak_gestural",
                "whatHappens": "RẮC! Tấm ván dưới chân tôi bật tung! Tôi ngã nhào giữa không trung!",
                "shotType": "MEDIUM_SHOT",
                "emotion": "focused",
                "dialogue": {
                    "speaker": "Haru",
                    "text": "RẮC! Tấm ván dưới chân tôi bật tung! Tôi ngã nhào giữa không trung!",
                    "voiceId": "vieneu-Thiện Minh",
                },
            },
            {
                "beatId": "BEAT_03",
                "timeRange": [9.5, 15.0],
                "primaryVerb": "present_two_handed",
                "whatHappens": "Haru bám chắc lan can, mắt hướng về cột mốc đèn lồng phía trước, hoàn thành lời hứa giao liên.",
                "shotType": "MEDIUM_SHOT",
                "emotion": "confident",
                "dialogue": {
                    "speaker": "Haru",
                    "text": "Thật kỳ lạ... giữa lúc mạng sống treo trên thanh gỗ mục, tôi chỉ lo: Bức thư có bị ướt không?",
                    "voiceId": "vieneu-Thiện Minh",
                },
            },
        ],
        "voice_timeline": {
            "lines": [
                {
                    "start_sec": 0.5,
                    "end_sec": 4.5,
                    "speaker": "HARU",
                    "text": "Đến cây cầu bắc qua kênh, tôi nhận ra một vấn đề lớn...",
                },
                {
                    "start_sec": 4.8,
                    "end_sec": 9.2,
                    "speaker": "HARU",
                    "text": "RẮC! Tấm ván dưới chân tôi bật tung! Tôi ngã nhào giữa không trung!",
                },
                {
                    "start_sec": 9.5,
                    "end_sec": 14.85,
                    "speaker": "HARU",
                    "text": "Thật kỳ lạ... giữa lúc mạng sống treo trên thanh gỗ mục, tôi chỉ lo: Bức thư có bị ướt không?",
                },
            ]
        },
        "visual_plan": [
            {
                "type": "LOCATION_DATE_CARD",
                "content_headline": "EDO · NĂM 1800",
                "content_body": "Người Giao Liên & Cuộn Thư Mật (16:9 Widescreen)",
                "start_time": 0.0,
                "end_time": 4.5,
            }
        ],
    }
    return pkg


def prepare_master_audio(out_audio_path: Path):
    """Prepares and normalizes master audio to -14.0 LUFS (True Peak <= -1.5 dBTP)."""
    src_audio = ROOT / "output" / "v51_drafts" / "draft_2_master_audio.wav"
    if not src_audio.exists():
        src_audio = ROOT / "output" / "v51_drafts" / "v51_stabilized_edo_courier_master_audio.wav"

    print(f"      Source master audio: {src_audio.name}")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src_audio),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=7",
        "-ar", "48000",
        "-ac", "2",
        str(out_audio_path),
    ], check=True)


def main():
    start_time = time.time()
    print("=" * 70)
    print("BUILDING DOCUMENTARY BLOB-HEAD 16:9 WIDESCREEN FULL HD (1920x1080) DRAFT")
    print("Stack: Motion Canvas + Three.js + Stickman Rig")
    print("Art Direction: Documentary Blob-Head Look (16:9 Widescreen)")
    print("Target: 1920x1080 @ 24fps | YouTube Loudness Normalization (-14 LUFS)")
    print("=" * 70)

    # 1. Build Package
    pkg = build_documentary_blob_head_16x9_package()
    pkg_path = OUTPUT_DIR / "v51_blob_head_16x9_package.json"
    pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[1/5] Package configured: {pkg_path.name}")

    # 2. Master Audio
    audio_path = OUTPUT_DIR / "v51_blob_head_16x9_master_audio.wav"
    print(f"\n[2/5] Preparing Multi-Track Master Audio ({audio_path.name})...")
    prepare_master_audio(audio_path)
    print(f"      Audio prepared successfully: {audio_path.stat().st_size / (1024*1024):.2f} MB")

    # 3. Render 16:9 Widescreen Video (1920x1080 @ 24fps)
    mp4_path = OUTPUT_DIR / "v51_blob_head_16x9_draft.mp4"
    print(f"\n[3/5] Rendering 16:9 Widescreen Video via ProductionRenderService...")
    render_cmd = [
        "node",
        str(ROOT / "scripts" / "production_render_service.mjs"),
        "--package", str(pkg_path),
        "--duration", str(pkg["total_sequence_duration_seconds"]),
        "--audio", str(audio_path),
        "--out", str(mp4_path),
    ]
    res = subprocess.run(render_cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0 or not mp4_path.exists():
        print(f"Render STDERR:\n{res.stderr}")
        print(f"Render STDOUT:\n{res.stdout}")
        raise RuntimeError(f"Render failed: {res.stderr or res.stdout}")

    print(f"      Render complete! File size: {mp4_path.stat().st_size / (1024*1024):.2f} MB")

    # Generate Storyboard Contact Sheet (16:9 widescreen 3x3 grid)
    contact_path = OUTPUT_DIR / "v51_blob_head_16x9_contact.png"
    print(f"      Generating Contact Sheet ({contact_path.name})...")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(mp4_path),
        "-vf", "fps=1/1.65,scale=480:-1,tile=3x3",
        "-frames:v", "1",
        str(contact_path),
    ], check=True)

    # Export VTT captions
    vtt_path = OUTPUT_DIR / "v51_blob_head_16x9_captions.vtt"
    vtt_content = (
        "WEBVTT\n\n"
        "1\n00:00:00.500 --> 00:00:04.500\nĐến cây cầu bắc qua kênh, tôi nhận ra một vấn đề lớn...\n\n"
        "2\n00:00:04.799 --> 00:00:09.199\nRẮC! Tấm ván dưới chân tôi bật tung! Tôi ngã nhào giữa không trung!\n\n"
        "3\n00:00:09.500 --> 00:00:14.849\nThật kỳ lạ... giữa lúc mạng sống treo trên thanh gỗ mục, tôi chỉ lo: Bức thư có bị ướt không?\n"
    )
    vtt_path.write_text(vtt_content, encoding="utf-8")

    # 4. Pre-Upload Quality Gate Verification (All 8 Rules for 16:9)
    print(f"\n[4/5] Executing Pre-Upload Quality Gate on 16:9 Master Video...")
    from pipeline.pre_upload_quality_gate import PreUploadQualityGate
    gate = PreUploadQualityGate()
    gate_passed, gate_report = gate.run_pre_upload_quality_gate(
        mp4_path=mp4_path,
        package=pkg,
        vtt_path=vtt_path
    )
    report_path = OUTPUT_DIR / "quality_gate_16x9_report.json"
    report_path.write_text(json.dumps(gate_report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not gate_passed:
        print(f"\n[QUALITY GATE FAILED]")
        for rule, details in gate_report["checklist"].items():
            if not details["passed"]:
                print(f"  FAILED {rule}: {details}")
        raise RuntimeError("Pre-Upload Quality Gate failed on 16:9 master.")
    print(f"      QUALITY GATE 100% PASS! All 8 rules satisfied strictly for 16:9.")

    # 5. Upload to Google Drive
    print(f"\n[5/5] Uploading 16:9 Deliverables to Google Drive Folder: {DRIVE_FOLDER_ID}...")
    uploaded_files = {}
    for f in [mp4_path, contact_path, vtt_path, pkg_path, report_path]:
        rec = upload_to_drive(f, DRIVE_FOLDER_ID)
        uploaded_files[f.name] = rec

    summary_path = OUTPUT_DIR / "delivery_16x9_manifest.json"
    summary_path.write_text(json.dumps(uploaded_files, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - start_time
    print("=" * 70)
    print(f"16:9 BUILD, RENDER, QUALITY GATE, AND GOOGLE DRIVE UPLOAD COMPLETE ({elapsed:.1f}s)!")
    print(f"Master MP4 (16:9): {uploaded_files[mp4_path.name]['url']}")
    print(f"Contact Sheet:    {uploaded_files[contact_path.name]['url']}")
    print(f"Captions (.vtt):   {uploaded_files[vtt_path.name]['url']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
