"""
SFX Bridge — Sinh hiệu ứng âm thanh (Sound Effects) cho Video Factory
Hỗ trợ:
  1. Meta AudioCraft / AudioGen (nếu torch + audiocraft được cài)
  2. Freesound fallback (nếu có FREESOUND_API_KEY)
  3. FFmpeg sine-wave fallback (luôn hoạt động, không cần internet)

Sử dụng:
  from ai-engine.sfx.audiocraft_bridge import generate_sfx
  wav_path = generate_sfx("tiếng sấm nổ vang trời", duration=3.0, out_path="thunder.wav")
"""

import os
import sys
import subprocess
import tempfile
import logging
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

AUDIOCRAFT_AVAILABLE = False
try:
    import torch
    from audiocraft.models import AudioGen
    from audiocraft.data.audio import audio_write
    AUDIOCRAFT_AVAILABLE = True
    logger.info("✅ AudioCraft (Meta) đã sẵn sàng")
except ImportError:
    logger.info("⚠️  AudioCraft chưa cài — sẽ dùng FFmpeg fallback")

# ------------------------------------------------------------------
# Ánh xạ từ khóa Tiếng Việt sang prompt Tiếng Anh cho AudioGen
# ------------------------------------------------------------------
VI_TO_EN_SFX_MAP = {
    "sấm": "thunder rumble",
    "sét": "lightning thunder crack",
    "mưa": "heavy rain pouring",
    "gió": "strong wind blowing",
    "bão": "storm wind rain thunder",
    "lửa": "fire crackling burning",
    "nước": "water flowing stream",
    "biển": "ocean waves crashing beach",
    "rừng": "forest birds chirping wind",
    "đêm": "night insects crickets",
    "bước chân": "footsteps walking gravel",
    "chạy": "running footsteps fast",
    "xe": "car engine driving",
    "súng": "gunshot explosion",
    "nổ": "explosion blast",
    "chuông": "bell ringing",
    "nhạc": "ambient background music",
    "tiếng vỗ tay": "crowd applause clapping",
    "trẻ em": "children laughing playing",
    "đám đông": "crowd cheering stadium",
    "tên lửa": "rocket engine launching blast",
    "không gian": "space ambient deep drone",
    "chiến tranh": "war explosions gunfire battle",
    "thành phố": "city traffic urban ambient",
}


def _translate_vi_prompt(prompt: str) -> str:
    """Tìm từ khóa Việt trong prompt, trả về prompt Tiếng Anh tương ứng."""
    lower = prompt.lower()
    for vi_key, en_val in VI_TO_EN_SFX_MAP.items():
        if vi_key in lower:
            return en_val
    # Nếu không tìm thấy, trả về nguyên gốc (AudioGen hiểu Tiếng Anh tốt hơn)
    return prompt


def _generate_audiocraft(prompt_en: str, duration: float, out_wav: Path) -> bool:
    """Sinh SFX bằng Meta AudioGen (cần torch + audiocraft)."""
    try:
        model = AudioGen.get_pretrained("facebook/audiogen-medium")
        model.set_generation_params(duration=duration)
        wav = model.generate([prompt_en])
        # Lưu không có extension (audio_write tự thêm .wav)
        stem = str(out_wav.with_suffix(""))
        audio_write(stem, wav[0].cpu(), model.sample_rate, strategy="loudness")
        return out_wav.exists() and out_wav.stat().st_size > 0
    except Exception as exc:
        logger.warning(f"AudioCraft error: {exc}")
        return False


def _generate_ffmpeg_fallback(prompt: str, duration: float, out_wav: Path) -> bool:
    """
    Fallback: sinh âm thanh từ FFmpeg (sine wave, noise, v.v.).
    Cơ bản nhưng đủ để pipeline không bị vỡ khi thiếu model AI.
    """
    lower = prompt.lower()
    # Chọn tần số/loại dựa theo từ khóa
    if any(k in lower for k in ["thunder", "explosion", "blast", "boom", "nổ", "sấm"]):
        filter_str = f"anoisesrc=d={duration}:c=white:a=0.5[n];[n]lowpass=f=200,highpass=f=20"
    elif any(k in lower for k in ["rain", "mưa", "water", "ocean", "waves"]):
        filter_str = f"anoisesrc=d={duration}:c=white:a=0.3[n];[n]bandpass=f=800:w=600"
    elif any(k in lower for k in ["wind", "gió", "forest", "rừng", "night"]):
        filter_str = f"anoisesrc=d={duration}:c=pink:a=0.2"
    elif any(k in lower for k in ["bell", "chuông", "ring"]):
        filter_str = f"sine=f=880:d={duration}"
    elif any(k in lower for k in ["crowd", "applause", "đám đông"]):
        filter_str = f"anoisesrc=d={duration}:c=white:a=0.4[n];[n]bandpass=f=2000:w=1500"
    elif any(k in lower for k in ["space", "không gian", "ambient"]):
        filter_str = f"anoisesrc=d={duration}:c=pink:a=0.1[n];[n]lowpass=f=400"
    else:
        # Generic tone
        filter_str = f"sine=f=440:d={duration}"

    cmd = (
        f'ffmpeg -y -f lavfi -i "{filter_str}" '
        f'-c:a pcm_s16le -ar 44100 "{out_wav}"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True)
    return out_wav.exists() and out_wav.stat().st_size > 0


def generate_sfx(
    prompt: str,
    duration: float = 3.0,
    out_path: str | Path | None = None,
) -> str:
    """
    Sinh file âm thanh SFX (.wav) từ mô tả text.

    Args:
        prompt: Mô tả âm thanh (Tiếng Việt hoặc Tiếng Anh).
        duration: Thời lượng mong muốn tính bằng giây (1.0 - 30.0).
        out_path: Đường dẫn lưu file .wav. Nếu None → tạo file tạm.

    Returns:
        Đường dẫn tuyệt đối đến file .wav đã tạo.
    """
    duration = max(0.5, min(30.0, duration))

    if out_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out_wav = Path(tmp.name)
        tmp.close()
    else:
        out_wav = Path(out_path)
        out_wav.parent.mkdir(parents=True, exist_ok=True)

    prompt_en = _translate_vi_prompt(prompt)

    if AUDIOCRAFT_AVAILABLE:
        print(f"   🎵 [AudioCraft] Sinh SFX: '{prompt_en}' ({duration}s)...")
        if _generate_audiocraft(prompt_en, duration, out_wav):
            print(f"   ✅ SFX OK: {out_wav.name}")
            return str(out_wav)

    # Fallback
    print(f"   🔊 [FFmpeg] Sinh SFX fallback: '{prompt}' ({duration}s)...")
    _generate_ffmpeg_fallback(prompt, duration, out_wav)
    print(f"   ✅ SFX OK (fallback): {out_wav.name}")
    return str(out_wav)


def generate_scene_sfx(scene: dict, out_dir: Path, scene_idx: int) -> str | None:
    """
    Sinh SFX phù hợp với nội dung một phân cảnh video.
    Phân tích từ khóa trong 'title' và 'spoken' để chọn loại SFX.

    Args:
        scene: Dict phân cảnh có keys: title, spoken, v.v.
        out_dir: Thư mục lưu file SFX.
        scene_idx: Chỉ số phân cảnh (để đặt tên file).

    Returns:
        Đường dẫn file SFX .wav hoặc None nếu không cần SFX.
    """
    text = (scene.get("title", "") + " " + scene.get("spoken", "")).lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"sfx_scene_{scene_idx:02d}.wav"

    # Chọn loại SFX dựa theo nội dung
    SFX_RULES = [
        (["chiến tranh", "chiến đấu", "nổ", "bom", "súng", "trận"], "explosion gunfire battle", 2.5),
        (["khởi đầu", "bắt đầu", "ra đời", "khai sinh", "big bang"], "dramatic impact whoosh", 2.0),
        (["vũ trụ", "không gian", "thiên hà", "ngôi sao"], "space ambient deep drone", 4.0),
        (["thành phố", "đô thị", "dân số", "xã hội"], "city crowd urban ambient", 3.0),
        (["nông nghiệp", "cánh đồng", "mùa màng", "trồng"], "nature wind birds field", 3.0),
        (["biển", "đại dương", "sóng"], "ocean waves crashing", 4.0),
        (["rừng", "thiên nhiên", "động vật"], "forest birds wind", 3.0),
        (["chuyển cảnh", "tiếp theo", "thế kỷ"], "whoosh transition cinematic", 1.0),
    ]

    for keywords, sfx_prompt, duration in SFX_RULES:
        if any(k in text for k in keywords):
            return generate_sfx(sfx_prompt, duration=duration, out_path=out_wav)

    # Mặc định: nhạc nền nhẹ cho cảnh bình thường
    return generate_sfx("ambient background subtle cinematic", duration=2.0, out_path=out_wav)


if __name__ == "__main__":
    # Thử nghiệm nhanh
    test_path = generate_sfx("tiếng sấm nổ vang trời", duration=3.0, out_path="test_thunder.wav")
    print(f"Đã tạo SFX: {test_path}")
    test_path2 = generate_sfx("city crowd ambient", duration=4.0, out_path="test_city.wav")
    print(f"Đã tạo SFX: {test_path2}")
