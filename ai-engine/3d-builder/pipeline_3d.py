"""
Pipeline Bridge: Tự động hóa Dựng cảnh 3D, Render góc máy và Tích hợp TripoSR / TRELLIS Mesh
"""

import os
import sys
import json
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
AGENT_ROOT = BASE_DIR.parent.parent

class ThreeDStudioPipeline:
    def __init__(self):
        self.studio_html = BASE_DIR / "studio_director.html"
        self.output_dir = BASE_DIR / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_camera_angle(self, angle_name="cinematic_low", out_frame="storyboard_frame.png"):
        """
        Dùng headless browser (Chrome) chụp ảnh phối cảnh 3D từ góc máy chỉ định.
        Hỗ trợ các góc: topview, over_shoulder, cinematic_low, tracking
        """
        out_path = self.output_dir / out_frame
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        
        # Chụp màn hình góc máy 3D bằng Chrome Headless
        cmd = [
            chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--window-size=1920,1080",
            f"--screenshot={out_path.resolve()}",
            str(self.studio_html.resolve())
        ]
        
        print(f"🎬 [3D Studio] Đang render góc máy: {angle_name}...")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if out_path.exists():
            print(f"✅ [3D Studio] Đã xuất frame bối cảnh: {out_path.name}")
            return str(out_path)
        return None

    def generate_mesh_triposr(self, input_image: str, output_obj: str = "model.obj"):
        """
        Bridge tích hợp TripoSR / TRELLIS (biến ảnh concept 2D thành vật thể 3D Mesh).
        """
        print(f"🧊 [Image-to-3D] Khởi tạo trích xuất Mesh 3D từ: {input_image}...")
        # Khi TripoSR / TRELLIS được cấu hình repo local
        triposr_dir = AGENT_ROOT / "TripoSR"
        if triposr_dir.exists():
            cmd = f'python "{triposr_dir / "run.py"}" "{input_image}" --output-dir "{self.output_dir}"'
            subprocess.run(cmd, shell=True)
            return str(self.output_dir / output_obj)
        else:
            print("💡 [Hướng dẫn] TripoSR có thể clone bằng: git clone https://github.com/VAST-AI-Research/TripoSR.git")
            return None

if __name__ == "__main__":
    director = ThreeDStudioPipeline()
    director.render_camera_angle("cinematic_low", "test_angle.png")
