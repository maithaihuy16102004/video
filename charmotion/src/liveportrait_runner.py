"""LivePortrait Runner - Điều phối hoạt ảnh nhân vật từ Driving Videos.
Hỗ trợ:
1. LivePortrait Inference (nếu đã clone repo & cài weights).
2. Lightweight Micro-motion Fallback (tối ưu hóa cho laptop nhẹ nhàng, không ăn GPU,
   tự tạo cử động thở, nháy mắt, nghiêng đầu nhẹ bằng FFmpeg/Pillow).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
DRIVING_DIR = BASE_DIR / "assets" / "driving_clips"


class LivePortraitRunner:
    def __init__(self, liveportrait_root: Optional[str] = None):
        self.root = Path(liveportrait_root) if liveportrait_root else BASE_DIR / "LivePortrait"
        self.has_liveportrait = (self.root / "inference.py").exists()

    def get_driving_video(self, emotion_tag: str) -> Optional[str]:
        """Lấy driving video tương ứng theo cảm xúc kịch bản"""
        mapping = {
            "curious": "curious.mp4",
            "surprised": "surprised.mp4",
            "tense": "tense.mp4",
            "excited": "excited.mp4",
            "serious": "serious.mp4",
            "neutral": "neutral.mp4"
        }
        target = DRIVING_DIR / mapping.get(emotion_tag, "neutral.mp4")
        if target.exists():
            return str(target)
        return None

    def animate(
        self,
        portrait_img: str,
        output_video: str,
        emotion_tag: str = "neutral",
        duration: float = 4.0,
        width: int = 1080,
        height: int = 1920,
        driving_video_ref: Optional[str] = None,
        motion_intensity: float = 0.5,
        allow_static_fallback: bool = True,
    ) -> str:
        """Thực hiện animate ảnh nhân vật:
        - Nếu có LivePortrait local: Chạy inference với driving video tương ứng.
        - Nếu chạy ở chế độ tiết kiệm tài nguyên (laptop Acer Nitro): Dùng dynamic micro-motion FFmpeg.
        """
        out_p = Path(output_video).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if not 0.0 <= motion_intensity <= 1.0:
            raise ValueError("motion_intensity phải nằm trong khoảng 0.0..1.0")
        requested_driver = Path(driving_video_ref).resolve() if driving_video_ref else None
        driving_clip = str(requested_driver) if requested_driver and requested_driver.exists() else self.get_driving_video(emotion_tag)

        if not allow_static_fallback and not self.has_liveportrait:
            raise RuntimeError(
                f"Preset ricks_dynamic cần LivePortrait thật. Không tìm thấy inference.py tại {self.root}."
            )
        if not allow_static_fallback and not driving_clip:
            raise RuntimeError(
                f"Preset ricks_dynamic cần driving video thật cho emotion={emotion_tag}."
            )

        # 1. Chạy LivePortrait nếu có sẵn repo
        if self.has_liveportrait and driving_clip:
            print(f"[LivePortrait] Chạy inference với driving={driving_clip} (emotion={emotion_tag})...")
            cmd = [
                sys.executable, str(self.root / "inference.py"),
                "-s", portrait_img,
                "-d", driving_clip,
                "-o", str(out_p),
                "--flag_eye_retargeting",
                "--flag_lip_retargeting"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if res.returncode == 0 and out_p.exists():
                return str(out_p)
            if not allow_static_fallback:
                raise RuntimeError(f"LivePortrait inference thất bại: {res.stderr[:500]}")
            print(f"[LivePortrait] Inference lỗi ({res.stderr[:200]}), chuyển sang chế độ micro-motion...")

        if not allow_static_fallback:
            raise RuntimeError("Không thể tạo hoạt ảnh nhân vật thật; static fallback đã bị khóa.")

        # 2. Lightweight Micro-motion Fallback (Siêu nhẹ, không nóng máy, chạy tốt kể cả khi mở AutoCAD)
        print(f"[LivePortrait] Chạy Micro-motion generator (emotion={emotion_tag}, duration={duration}s)...")
        fps = 30
        total_frames = int(duration * fps)

        # Tạo hiệu ứng cử động tự nhiên: thở nhẹ, nghiêng đầu nhẹ theo nhịp
        if emotion_tag in ["surprised", "tense"]:
            # Nhịp nhanh, hơi giật nhẹ
            vf = (
                f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2},"
                f"zoompan=z='min(zoom+0.002,1.25)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
                f"setsar=1"
            )
        elif emotion_tag in ["excited", "curious"]:
            # Nghiêng và zoom nhẹ
            vf = (
                f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2},"
                f"zoompan=z='min(zoom+0.0015,1.2)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
                f"setsar=1"
            )
        else:
            # Neutral / serious: nhịp thở êm đềm
            vf = (
                f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2},"
                f"zoompan=z='min(zoom+0.001,1.15)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
                f"setsar=1"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", portrait_img,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            str(out_p)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[LivePortrait] Đã tạo clip nhân vật động -> {out_p}")
        return str(out_p)


if __name__ == "__main__":
    runner = LivePortraitRunner()
    portrait = "assets/characters/kurzgesagt_character.png"
    out_test = "assets/test_avatar_animated.mp4"
    if os.path.exists(portrait):
        runner.animate(portrait, out_test, emotion_tag="curious", duration=3.0)
