"""Build Video from Director JSON — v2 robust.

Nhận Scene Director JSON từ AI chat → TTS tiếng Việt → Avatar micro-motion
→ B-Roll overlay 30/70 → cắt dead-air → Audio Ducking BGM → video draft MP4.

Không cần API key. Chạy hoàn toàn local.

Dùng:
    python pipeline/build_video_from_director_json.py pipeline/draft_chat_director.json
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "pipeline"))
sys.path.insert(0, str(BASE_DIR / "ai-video-editor" / "src"))
sys.path.insert(0, str(BASE_DIR / "charmotion" / "src"))
sys.path.insert(0, str(BASE_DIR / "tts" / "src"))

from scene_overlay_renderer import render_scene_with_overlay
from audio_processor import apply_audio_ducking, clean_silence_with_auto_editor
from liveportrait_runner import LivePortraitRunner
from engines import get_engine
from voices import resolve_voice
from asset_resolver import LocalAssetResolver
from production_quality import generate_contact_sheet


def _probe_duration(path: str) -> float:
    """Đo độ dài audio/video bằng ffprobe."""
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        d = float(res.stdout.strip())
        return d if d > 0.1 else 3.5
    except Exception:
        return 3.5


def _speed_to_rate(speed: float) -> Optional[str]:
    """1.0 → None, 1.1 → '+10%', 0.9 → '-10%'."""
    pct = int(round((speed - 1.0) * 100))
    return f"{pct:+d}%" if pct != 0 else None


def build_video_from_json(
    director_data: Dict[str, Any],
    output_path: str = "output/draft_video.mp4",
    voice: str = "namminh",
    bgm_key: str = "cinematic_epic",
) -> str:
    out_final = Path(output_path).resolve()
    out_final.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_final.parent / "temp_draft"
    tmp.mkdir(parents=True, exist_ok=True)

    meta = director_data.get("video_metadata", {})
    topic = meta.get("topic", "Video Draft")
    timeline = director_data.get("timeline", [])
    voice_id = resolve_voice(voice or "namminh")

    print("=" * 65)
    print(f"  DỰNG VIDEO TỪ DIRECTOR JSON")
    print(f"  Chủ đề  : {topic}")
    print(f"  Scenes  : {len(timeline)}")
    print(f"  Voice   : {voice_id}")
    print("=" * 65)

    tts = get_engine("edge-tts")
    lp = LivePortraitRunner()

    avatar_img = BASE_DIR / "assets" / "characters" / "kurzgesagt_character.png"
    if not avatar_img.exists():
        avatar_img = BASE_DIR / "assets" / "characters" / "kurzgesagt_character.jpg"
    if not avatar_img.exists():
        raise FileNotFoundError(f"Không tìm thấy ảnh nhân vật: {avatar_img}")

    asset_resolver = LocalAssetResolver(BASE_DIR / "assets" / "scenes")

    scene_videos = []
    scene_audios = []
    tts_ok_count = 0

    # ━━━ BƯỚC 1: Từng Scene → TTS + Avatar + Overlay ━━━
    for idx, scene in enumerate(timeline):
        sid = scene.get("scene_id", idx + 1)
        vo = scene.get("voiceover", {})
        text = vo.get("text", "Xin chào.")
        emotion = vo.get("emotion_tag", "neutral")
        rate_str = _speed_to_rate(vo.get("speed", 1.0))

        # 1a. TTS
        audio_path = tmp / f"voice_{sid}.mp3"
        print(f"\n{'─'*50}")
        print(f"[Scene {sid}] \"{text[:55]}...\"")
        print(f"  emotion={emotion}  rate={rate_str or 'default'}")
        tts_kwargs = {"rate": rate_str} if rate_str else {}
        tts.synthesize(text, voice=voice_id, out_path=str(audio_path), **tts_kwargs)
        dur = _probe_duration(str(audio_path))
        fsize = audio_path.stat().st_size if audio_path.exists() else 0
        is_real_voice = fsize > 5000  # >5KB = có giọng thật
        if is_real_voice:
            tts_ok_count += 1
        print(f"  -> Audio: {fsize/1024:.0f}KB, {dur:.2f}s"
              f" {'✓ giọng thật' if is_real_voice else '⚠ placeholder'}")

        # 1b. Avatar micro-motion
        avatar_clip = tmp / f"avatar_{sid}.mp4"
        lp.animate(str(avatar_img), str(avatar_clip),
                   emotion_tag=emotion, duration=dur)

        # 1c. Overlay B-Roll 30/70
        visual = scene.get("visual_director", {})
        broll_path = asset_resolver.resolve(visual)
        broll = str(broll_path) if broll_path else None
        if visual.get("b_roll_overlay_ratio", 0.0) > 0 and not broll:
            print("  ⚠ Không có B-roll khớp prompt; giữ avatar thay vì chèn ảnh sai nội dung")
        comp = tmp / f"comp_{sid}.mp4"
        render_scene_with_overlay(
            avatar_input=str(avatar_clip),
            b_roll_input=broll,
            output_scene_path=str(comp),
            scene_config=scene,
            scene_duration=dur,
        )
        scene_videos.append(comp)
        scene_audios.append(audio_path)

    # ━━━ BƯỚC 2: Ghép video ━━━
    print(f"\n{'─'*50}")
    print(f"[Concat] Ghép {len(scene_videos)} phân cảnh video...")
    concat_v = tmp / "concat_v.txt"
    concat_v.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in scene_videos),
        encoding="utf-8")
    raw_video = tmp / "raw_concat.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_v), "-c", "copy", str(raw_video),
    ], check=True, capture_output=True)
    generate_contact_sheet(out_final, out_final.with_name(f"{out_final.stem}_contact_sheet.jpg"))

    # ━━━ BƯỚC 3: Ghép audio + cắt silence ━━━
    print("[Audio] Ghép giọng đọc & cắt khoảng lặng...")
    concat_a = tmp / "concat_a.txt"
    concat_a.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in scene_audios),
        encoding="utf-8")
    raw_voice = tmp / "raw_voice.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_a), "-c", "copy", str(raw_voice),
    ], check=True, capture_output=True)
    clean_voice = tmp / "voice_clean.mp3"
    clean_silence_with_auto_editor(str(raw_voice), str(clean_voice))

    # ━━━ BƯỚC 4: Audio Ducking BGM ━━━
    print("[Audio] Áp dụng Audio Ducking BGM...")
    bgm = BASE_DIR / "assets" / "bgm" / f"{bgm_key}.mp3"
    if not bgm.exists():
        bgm = next((BASE_DIR / "assets" / "bgm").glob("*.mp3"), None)
    mixed = tmp / "mixed.mp3"
    if bgm and bgm.exists():
        apply_audio_ducking(str(clean_voice), str(bgm), str(mixed),
                            bgm_base_vol=0.18)
    else:
        import shutil
        shutil.copy2(str(clean_voice), str(mixed))

    # ━━━ BƯỚC 5: Mux final ━━━
    print("[Export] Hợp nhất Video + Audio...")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(raw_video), "-i", str(mixed),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out_final),
    ], check=True, capture_output=True)

    size_mb = out_final.stat().st_size / 1024 / 1024
    total_dur = _probe_duration(str(out_final))

    print()
    print("=" * 65)
    print(f"  ✅ VIDEO HOÀN THÀNH")
    print(f"  📁 File     : {out_final}")
    print(f"  📐 Kích thước: 1080x1920 (dọc 9:16)")
    print(f"  ⏱  Thời lượng: {total_dur:.1f}s")
    print(f"  💾 Dung lượng: {size_mb:.1f} MB")
    print(f"  🎙  Giọng đọc : {tts_ok_count}/{len(timeline)} scene có giọng thật")
    print("=" * 65)
    return str(out_final)


if __name__ == "__main__":
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
        build_video_from_json(data)
    else:
        print("Dùng: python build_video_from_director_json.py <director.json>")
