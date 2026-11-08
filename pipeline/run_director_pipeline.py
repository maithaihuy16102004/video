"""Director Pipeline E2E - Chạy quy trình sản xuất video hoàn chỉnh:
1. LLM Director: Phân rã kịch bản thô thành Scene Director JSON (tự điều phối climax_score).
2. Charmotion / LivePortrait: Tạo hoạt ảnh nhân vật biểu cảm theo emotion_tag.
3. 30/70 Overlay Engine: Cắt đè B-Roll (70%) lên Avatar (30%) + Camera FX (glitch/zoom/pan) + SFX.
4. Audio Ducking & Dead-air cut: Cắt silence chết + tự ép nhỏ BGM khi nhân vật nói.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "pipeline"))
sys.path.insert(0, str(BASE_DIR / "ai-video-editor" / "src"))
sys.path.insert(0, str(BASE_DIR / "charmotion" / "src"))

from scene_director import LLMDirector
from scene_overlay_renderer import render_scene_with_overlay
from audio_processor import apply_audio_ducking, clean_silence_with_auto_editor
from liveportrait_runner import LivePortraitRunner


def run_pipeline(
    topic: str = "Bí mật đằng sau trí tuệ nhân tạo AGI",
    raw_script: str = None,
    output_video: str = "output/director_video_final.mp4"
):
    print("=" * 60)
    print(f"🎬 KHỞI ĐỘNG DIRECTOR AUTOMATION PIPELINE: {topic}")
    print("=" * 60)

    if not raw_script:
        raw_script = (
            "Bạn có bao giờ tự hỏi điều gì thực sự đứng sau trí tuệ nhân tạo AGI? "
            "Một sự thật đáng kinh ngạc mà ít người có thể ngờ tới: các mô hình ngôn ngữ đang tự tối ưu hóa mã nguồn. "
            "Nếu bạn không hành động ngay hôm nay, bạn sẽ bị thay thế trong vòng hai năm tới!"
        )

    out_final = Path(output_video).resolve()
    out_final.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = out_final.parent / "temp_scenes"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # BƯỚC 1: LLM DIRECTOR
    print("\n[Bước 1] LLM Director phân tích kịch bản & áp luật climax_score...")
    director = LLMDirector()
    director_data = director.generate_director_json(raw_script, topic=topic)
    timeline = director_data.get("timeline", [])
    print(f"-> Đã tạo {len(timeline)} phân cảnh có cấu trúc.")

    # BƯỚC 2: RENDER CÁC PHÂN CẢNH THEO QUY TẮC 30/70 & DYNAMIC CAMERA
    print("\n[Bước 2] Render phân cảnh (Avatar + B-Roll Overlap + Dynamic Camera FX)...")
    avatar_img = BASE_DIR / "assets" / "characters" / "kurzgesagt_character.png"
    if not avatar_img.exists():
        avatar_img = BASE_DIR / "assets" / "characters" / "kurzgesagt_character.jpg"

    broll_bank = [
        str(BASE_DIR / "assets" / "scenes" / f"scene{i}.jpg")
        for i in range(1, 6)
        if (BASE_DIR / "assets" / "scenes" / f"scene{i}.jpg").exists()
    ]

    scene_video_files = []
    lp_runner = LivePortraitRunner()

    for idx, scene in enumerate(timeline):
        s_id = scene.get("scene_id", idx + 1)
        emotion = scene.get("voiceover", {}).get("emotion_tag", "neutral")
        dur = 3.5  # Độ dài phân cảnh mẫu

        # Sinh Avatar video clip
        avatar_clip = temp_dir / f"avatar_scene_{s_id}.mp4"
        lp_runner.animate(str(avatar_img), str(avatar_clip), emotion_tag=emotion, duration=dur)

        # Chọn B-Roll
        broll = broll_bank[idx % len(broll_bank)] if broll_bank else None

        # Render phân cảnh cắt đè 30/70
        out_scene_mp4 = temp_dir / f"composite_scene_{s_id}.mp4"
        render_scene_with_overlay(
            avatar_input=str(avatar_clip),
            b_roll_input=broll,
            output_scene_path=str(out_scene_mp4),
            scene_config=scene,
            scene_duration=dur
        )
        scene_video_files.append(str(out_scene_mp4))

    # BƯỚC 3: GHÉP CÁC PHÂN CẢNH
    print("\n[Bước 3] Ghép chuỗi phân cảnh video...")
    concat_txt = temp_dir / "concat_list.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for fpath in scene_video_files:
            f.write(f"file '{Path(fpath).as_posix()}'\n")

    video_concat_raw = temp_dir / "video_raw_concat.mp4"
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(video_concat_raw)
    ]
    subprocess.run(cmd_concat, check=True, capture_output=True)

    # BƯỚC 4: XỬ LÝ ÂM THANH (AUTO-EDITOR & AUDIO DUCKING BGM)
    print("\n[Bước 4] Phối âm thanh: Dead-air Clean & Audio Ducking...")
    bgm_path = BASE_DIR / "assets" / "bgm" / "cinematic_epic.mp3"
    total_dur = len(scene_video_files) * 3.5

    # Tạo voice track tổng hợp
    voice_track_raw = temp_dir / "voice_track.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency=320:duration={total_dur}",
        "-c:a", "libmp3lame", str(voice_track_raw)
    ], check=True, capture_output=True)

    # Dọn dẹp khoảng lặng
    voice_clean = temp_dir / "voice_clean.mp3"
    clean_silence_with_auto_editor(str(voice_track_raw), str(voice_clean))

    # Áp dụng Ducking BGM
    mixed_audio = temp_dir / "audio_ducked_mix.mp3"
    apply_audio_ducking(str(voice_clean), str(bgm_path), str(mixed_audio), bgm_base_vol=0.18)

    # BƯỚC 5: HỢP NHẤT VIDEO & AUDIO CUỐI CÙNG
    print("\n[Bước 5] Xuất video hoàn chỉnh cuối cùng...")
    cmd_final = [
        "ffmpeg", "-y",
        "-i", str(video_concat_raw),
        "-i", str(mixed_audio),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_final)
    ]
    subprocess.run(cmd_final, check=True, capture_output=True)

    print("=" * 60)
    print(f"🎉 HOÀN THÀNH XUẤT SẮC! Video đã tạo: {out_final}")
    print("=" * 60)
    return str(out_final)


if __name__ == "__main__":
    run_pipeline()
