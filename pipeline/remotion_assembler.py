"""
Remotion Slide Renderer & Video Assembler
Tự động xuất từng frame card chất lượng cao từ Remotion Engine và dùng FFmpeg nội bộ 
ghép thành video chuẩn dài 3-5 phút với hiệu ứng Ken Burns, nhạc nền BGM ducking và phụ đề.
"""

import os
import subprocess
from pathlib import Path

REMOTION_DIR = Path(r"D:\Agent\remotion-engine")
CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

def render_scene_slides(props_path: Path, num_scenes: int, out_dir: Path):
    """
    Render từng slide tương ứng với mỗi phân cảnh qua Remotion Still (nhẹ, nhanh, siêu nét).
    """
    frames_per_scene = 30 * 25  # ~25 giây mỗi cảnh
    slide_paths = []
    
    for i in range(num_scenes):
        target_frame = int(i * frames_per_scene + 30)
        slide_img = out_dir / f"scene_slide_{i+1:02d}.png"
        
        cmd = (
            f'cd /d "{REMOTION_DIR}" && '
            f'npx remotion still VideoComposition "{slide_img.resolve()}" '
            f'--props="{props_path.resolve()}" '
            f'--frame={target_frame} '
            f'--browser-executable="{CHROME_PATH}" '
            f'--log=error'
        )
        subprocess.run(cmd, shell=True)
        if slide_img.exists():
            slide_paths.append(slide_img)
            
    return slide_paths


def assemble_multiscene_video(slide_paths: list, voice_file: Path, bgm_file: Path, out_video: Path, total_duration: float):
    """
    Ghép các slide phân cảnh với chuyển động Ken Burns zoom mượt mà, lồng voice và BGM ducking.
    """
    if not slide_paths:
        return False
        
    sec_per_slide = total_duration / len(slide_paths)
    
    # Tạo filter_complex cho từng slide với hiệu ứng zoom nhẹ (Ken Burns)
    inputs = []
    filter_parts = []
    
    for idx, slide in enumerate(slide_paths):
        inputs.extend(["-loop", "1", "-t", f"{sec_per_slide:.2f}", "-i", str(slide.resolve())])
        # Áp dụng zoompan cho từng slide: zoom từ 1.0 đến 1.08
        filter_parts.append(
            f"[{idx}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            f"zoompan=z='min(zoom+0.0003,1.08)':d={int(sec_per_slide*30)}:s=1080x1920:fps=30[v{idx}];"
        )
    
    concat_inputs = "".join(f"[v{i}]" for i in range(len(slide_paths)))
    filter_parts.append(f"{concat_inputs}concat=n={len(slide_paths)}:v=1:a=0[vconcat];")
    
    # Filter âm thanh: Trộn voice (1.0) và BGM (0.12)
    voice_idx = len(slide_paths)
    bgm_idx = voice_idx + 1
    
    inputs.extend(["-i", str(voice_file.resolve())])
    if bgm_file and bgm_file.exists():
        inputs.extend(["-i", str(bgm_file.resolve())])
        filter_parts.append(
            f"[{voice_idx}:a]volume=1.0[va];"
            f"[{bgm_idx}:a]volume=0.12[ba];"
            f"[va][ba]amix=inputs=2:duration=first[amixed]"
        )
        audio_map = "[amixed]"
    else:
        audio_map = f"{voice_idx}:a"
        
    full_filter = "".join(filter_parts)
    
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", full_filter,
        "-map", "[vconcat]",
        "-map", audio_map,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_video.resolve())
    ]
    
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_video.exists() and out_video.stat().st_size > 10000
