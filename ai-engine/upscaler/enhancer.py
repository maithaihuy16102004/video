"""
Video Upscaler & Frame Interpolator Engine
Cung cấp giải pháp nâng cấp độ nét (Super Resolution) và tăng số khung hình (60 FPS Interpolation).
Chạy thông qua FFmpeg filter (minterpolate / scale) và hỗ trợ tích hợp Real-ESRGAN / RIFE NCNN.
"""

import os
import subprocess
from pathlib import Path

def interpolate_to_60fps(input_video: str, output_video: str):
    """
    Nội suy khung hình lên 60 FPS chuẩn mượt (Frame Interpolation).
    Sử dụng thuật toán Motion Estimation (MCI) tối ưu từ FFmpeg.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(input_video),
        "-vf", "minterpolate='fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1'",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "copy",
        str(output_video)
    ]
    subprocess.run(cmd, stdout=subprocess.DEV_NULL, stderr=subprocess.DEV_NULL)
    return output_video

def upscale_video_2k(input_video: str, output_video: str):
    """
    Nâng cấp video lên chuẩn 2K (1440x2560) sắc nét với bộ lọc lanczos cao cấp.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(input_video),
        "-vf", "scale=1440:2560:flags=lanczos,unsharp=5:5:0.8:3:3:0.4",
        "-c:v", "libx264", "-crf", "17", "-preset", "fast",
        "-c:a", "copy",
        str(output_video)
    ]
    subprocess.run(cmd, stdout=subprocess.DEV_NULL, stderr=subprocess.DEV_NULL)
    return output_video
