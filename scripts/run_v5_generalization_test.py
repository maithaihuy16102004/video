"""V5.0 Generalization Suite: Autonomous End-to-End Rendering of 3 Unseen Scripts.
Part of the Premium Stickman Cinematic V5.0 Acceptance Gate.

Strict Rules:
- ZERO source code modifications before/during/after run.
- Pure Motion Canvas + Three.js WebGL rendering.
- 1080p 16:9 output @ 24fps with VieNeu-TTS 48kHz audio.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_DIR = ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCRIPTS = [
    {
        "id": "shanghai_1930",
        "title": "Chuyến Tàu Đêm Thượng Hải 1930",
        "genre": "Historical Urban Noir",
        "expected_environment": "RAIL_STATION",
        "text": """**CHUYẾN TÀU ĐÊM THƯỢNG HẢI 1930**
Bối cảnh: Ga xe lửa Thượng Hải lúc nửa đêm, khói tàu mù mịt, mưa phùn rơi trên đường ray thép.

Trần Văn Minh: Chuyến tàu tốc hành từ Nam Kinh vừa rít phanh vào ga.
Trần Văn Minh: Tôi siết chặt chiếc ô đen, mắt không rời toa hạng nhất.
Trần Văn Minh: Theo mật tin, vali tài liệu số 4 phải được bàn giao trước khi còi hiệu thứ hai vang lên.
Trần Văn Minh: Một bóng người mặc áo dạ đen bước xuống thềm ga đầy hơi nước.
Trần Văn Minh: Thời khắc quyết định đã đến.
"""
    },
    {
        "id": "choray_er",
        "title": "Cuộc Gọi Từ Phòng Cấp Cứu Chợ Rẫy",
        "genre": "Modern Medical ER",
        "expected_environment": "HOSPITAL_ER",
        "text": """**CUỘC GỌI TỪ PHÒNG CẤP CỨU CHỢ RẪY**
Bối cảnh: Phòng cấp cứu Bệnh viện Chợ Rẫy, ánh đèn huỳnh quang trắng lạnh, tiếng máy monitor kêu bip liên hồi.

Bác sĩ Tuấn: Monitor báo nhịp tim bệnh nhân tụt nhanh xuống dưới 45!
Bác sĩ Tuấn: Chuẩn bị ngay hai ống Atropine và máy sốc tim ngoài lồng ngực.
Bác sĩ Tuấn: Cả kíp trực khẩn trương ép tim liên tục, không được ngừng một giây nào.
Bác sĩ Tuấn: Sốc tim lần một ở mức 200 Jun! Lùi lại!
Bác sĩ Tuấn: Nhịp xoang đã trở lại đều đặn... Chúng ta vừa kéo bệnh nhân qua lằn ranh sinh tử.
"""
    },
    {
        "id": "sahara_2050",
        "title": "Trạm Quan Sát Bão Sa Mạc Sahara 2050",
        "genre": "Sci-Fi Desert Station",
        "expected_environment": "DESERT_STATION",
        "text": """**TRẠM QUAN SÁT BÃO SA MẠC SAHARA 2050**
Bối cảnh: Trạm khí tượng bán cầu Sahara năm 2050, bão cát vàng cuồn cuộn ngoài mái vòm kính, mảng pin mặt trời xoay theo hướng gió.

Kỹ sư Elena: Cảm biến vi sai ghi nhận vận tốc gió cát vượt mốc 140 km/h.
Kỹ sư Elena: Tôi lập tức khóa chốt áp suất vòm trung tâm và kích hoạt lá chắn bảo vệ.
Kỹ sư Elena: Màn hình toàn cảnh hiện rõ vùng tâm bão đang di chuyển thẳng về hướng trạm.
Kỹ sư Elena: Máy phát điện lượng tử dự phòng đã khởi động thành công.
Kỹ sư Elena: Dù bão cát ngoài kia có cuồng nộ đến đâu, dữ liệu quan sát khí quyển năm 2050 vẫn an toàn tuyệt đối.
"""
    }
]

def get_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()

def main():
    print("=" * 60)
    print("V5.0 MANDATORY GENERALIZATION SUITE EXECUTION")
    print("Zero-Story Coding Verification Gate")
    print("=" * 60)

    from pipeline.universal.v5_story_director import V5UniversalStoryDirector
    from pipeline.studio_api import prepare_voice

    director = V5UniversalStoryDirector()
    suite_results = []

    for item in SCRIPTS:
        sid = item["id"]
        title = item["title"]
        print(f"\n>>> [1/4] Processing Script: {title} ({sid})")

        # Step 1: Script Intelligence & Package Compilation
        v5_pkg = director.analyze_script(item["text"])
        cap_report = director.validate_capability(v5_pkg)
        print(f"    Capability Check: {cap_report.status} ({cap_report.checked_characters} chars, {cap_report.checked_locations} locs)")
        if cap_report.errors:
            print(f"    Capability Errors: {cap_report.errors}")

        runner_pkg = director.compile_to_runner_package(v5_pkg)
        pkg_file = OUT_DIR / f"package_{sid}.json"
        pkg_file.write_text(json.dumps(runner_pkg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    Saved Scene Package: {pkg_file.name}")

        # Step 2: Audio Synthesis via VieNeu-TTS
        print(f">>> [2/4] Synthesizing Voice & Audio...")
        audio_folder = OUT_DIR / f"audio_{sid}"
        audio_folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "script": item["text"],
            "voice": v5_pkg["characters"][0].get("voiceId", "vieneu-Thiện Minh"),
            "multiVoice": True
        }
        voice_path, subs_path, segments, cast = prepare_voice(payload, audio_folder)
        print(f"    Generated Voice: {voice_path.name} ({voice_path.stat().st_size / 1024:.1f} KB)")
        print(f"    Cast: {[c['name'] for c in cast]}, Segments: {len(segments)}")

        # Step 3: Production Render via Three.js + Motion Canvas
        out_mp4 = OUT_DIR / f"v5_{sid}_master.mp4"
        duration_sec = min(20.0, max(8.0, runner_pkg.get("total_sequence_duration_seconds", 15.0)))
        print(f">>> [3/4] Rendering Full HD 1080p MP4 ({duration_sec}s @ 24fps)...")

        t0 = time.time()
        cmd = [
            "node",
            str(ROOT / "scripts" / "production_render_service.mjs"),
            "--package", str(pkg_file),
            "--duration", str(duration_sec),
            "--audio", str(voice_path),
            "--out", str(out_mp4)
        ]
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0 or not out_mp4.exists():
            print(f"    ERROR rendering {sid}:")
            print(res.stderr or res.stdout)
            sys.exit(1)

        render_sec = time.time() - t0
        mp4_size_mb = out_mp4.stat().st_size / (1024 * 1024)
        mp4_sha = get_file_sha256(out_mp4)
        print(f"    Render Complete: {out_mp4.name} ({mp4_size_mb:.2f} MB, {render_sec:.1f}s, SHA: {mp4_sha[:12]}...)")

        # Step 4: Contact Sheet Extraction (4x3 tile at 1 frame per 4 seconds)
        contact_png = OUT_DIR / f"v5_{sid}_contact.png"
        print(f">>> [4/4] Generating Proof Contact Sheet: {contact_png.name}...")
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(out_mp4),
            "-vf", "fps=1/4,scale=480:-1,tile=4x3",
            "-frames:v", "1",
            str(contact_png)
        ], check=True)
        print(f"    Contact sheet saved ({contact_png.stat().st_size / 1024:.1f} KB).")

        suite_results.append({
            "script_id": sid,
            "title": title,
            "genre": item["genre"],
            "environment_category": runner_pkg["scene_world"]["architecture_style"],
            "characters": [a["dna"]["name"] for a in runner_pkg["actors"]],
            "archetypes": [a["dna"].get("archetypeId") or a["dna"].get("costume", {}).get("archetype", "young_courier") for a in runner_pkg["actors"]],
            "props": [a["dna"]["heldProps"] for a in runner_pkg["actors"]],
            "duration_sec": duration_sec,
            "mp4_file": out_mp4.name,
            "mp4_size_mb": round(mp4_size_mb, 2),
            "mp4_sha256": mp4_sha,
            "contact_sheet": contact_png.name,
            "render_elapsed_sec": round(render_sec, 1)
        })

    # Save validation manifest
    manifest_path = OUT_DIR / "v5_generalization_manifest.json"
    manifest_path.write_text(json.dumps(suite_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAll 3 generalization proofs successfully generated and saved to:")
    print(f"{OUT_DIR.resolve()}")
    print("=" * 60)

if __name__ == "__main__":
    main()
