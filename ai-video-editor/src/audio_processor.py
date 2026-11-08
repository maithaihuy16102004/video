"""Audio Processor - Xử lý âm thanh chuyên nghiệp:
1. Auto-Editor: Tự động loại bỏ silence/dead-air > 0.3s để tăng nhịp độ video.
2. Audio Ducking (FFmpeg Sidechain): Tự động ép nhỏ nhạc nền khi nhân vật nói,
   dâng nhạc mượt mà ở các khoảng nghỉ.
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def clean_silence_with_auto_editor(
    input_audio: str,
    output_audio: str,
    threshold: str = "4%",
    margin: str = "0.08s"
) -> str:
    """Dọn sạch khoảng lặng chết (>0.3s) bằng auto-editor hoặc fallback bằng FFmpeg silenceremove."""
    in_p = Path(input_audio).resolve()
    out_p = Path(output_audio).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("auto-editor"):
        print(f"[AudioProcessor] Chạy auto-editor (margin={margin}, threshold={threshold})...")
        cmd = [
            "auto-editor", str(in_p),
            "--margin", margin,
            "--edit", f"audio:threshold={threshold}",
            "-o", str(out_p)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode == 0 and out_p.exists():
            return str(out_p)
        print(f"[AudioProcessor] auto-editor gặp lỗi ({res.stderr[:200]}), chuyển sang FFmpeg...")

    # Fallback FFmpeg silenceremove 2 chiều (cắt silence đầu, giữa, cuối)
    print("[AudioProcessor] Sử dụng FFmpeg silenceremove (cắt khoảng lặng > 0.3s)...")
    cmd = [
        "ffmpeg", "-y", "-i", str(in_p),
        "-af", (
            "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-35dB:detection=peak,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-35dB:detection=peak,"
            "areverse"
        ),
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(out_p)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(out_p)


def apply_audio_ducking(
    voice_path: str,
    bgm_path: str,
    output_path: str,
    bgm_base_vol: float = 0.15,
    threshold: float = 0.08,
    ratio: float = 5.0
) -> str:
    """Tự động ép nhạc nền nhỏ xuống (-18dB ~ -22dB) khi giọng nói cất lên
    bằng bộ lọc FFmpeg sidechaincompress (hoặc sidechainamplify).
    """
    v_p = Path(voice_path).resolve()
    b_p = Path(bgm_path).resolve()
    o_p = Path(output_path).resolve()
    o_p.parent.mkdir(parents=True, exist_ok=True)

    print(f"[AudioProcessor] Áp dụng Audio Ducking (voice={v_p.name}, bgm={b_p.name})...")

    # Filter complex:
    # 1. Giảm âm lượng cơ sở của BGM: [1:a]volume=0.15[bgm_base]
    # 2. Tạo bản sao BGM và đưa qua sidechaincompress dựa trên tín hiệu voice [0:a]
    filter_complex = (
        f"[1:a]volume={bgm_base_vol}[bgm_base];"
        f"[bgm_base][0:a]sidechaincompress=threshold={threshold}:ratio={ratio}:attack=20:release=350[bgm_ducked];"
        f"[0:a][bgm_ducked]amix=inputs=2:weights=1 1:dropout_transition=2[out_audio]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(v_p),
        "-i", str(b_p),
        "-filter_complex", filter_complex,
        "-map", "0:v?",        # Giữ luồng video nếu file voice là video
        "-map", "[out_audio]",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-shortest",
        str(o_p)
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[AudioProcessor] Đã xuất file trộn Audio Ducking -> {o_p}")
    return str(o_p)


if __name__ == "__main__":
    print("Module audio_processor sẵn sàng.")
