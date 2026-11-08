"""Adapter from the canonical scene plan to the PremiumMotion composition."""

from __future__ import annotations

import json
import shutil
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REMOTION = ROOT / "remotion-engine"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def _hex(color) -> str:
    return "#" + "".join(f"{max(0,min(255,int(c))):02X}" for c in color[:3])


def art_direction_for(config: dict) -> str:
    category = str(config.get("category", "")).lower()
    if "tài chính" in category:
        return "neo-editorial"
    if "lịch sử" in category:
        return "paper-tech"
    if "vũ trụ" in category:
        return "signal-noir"
    return "glass-future"


def build_premium_props(config: dict) -> dict:
    scenes = []
    for scene in config.get("scenes", []):
        plan = scene.get("edit_plan", {})
        scenes.append({
            "badge": scene.get("badge", ""),
            "headline": scene.get("headline", ""),
            "subtext": scene.get("subtext", ""),
            "spoken": scene.get("spoken", ""),
            "duration": float(scene.get("duration", 5)),
            "accent": _hex(scene.get("theme_color", (0, 220, 255))),
            "visualLanguage": plan.get("visual_language", "data_stream"),
            "visualBeats": plan.get("visual_beats", []),
            "motionArc": plan.get("motion_arc", ["anticipate", "act", "settle"]),
            "cameraPattern": plan.get("camera_pattern", ["wide", "detail", "wide"]),
            "holdSeconds": float(plan.get("hold_seconds", 0.6)),
        })
    return {"scenes": scenes, "artDirection": art_direction_for(config)}


def render_premium(config: dict, output: str | Path, props_output: str | Path | None = None) -> Path:
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    props_path = Path(props_output).resolve() if props_output else output.with_suffix(".props.json")
    props_path.write_text(json.dumps(build_premium_props(config), ensure_ascii=False, indent=2), encoding="utf-8")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("Không tìm thấy npx; cần Node.js để chạy Remotion")
    cmd = [
        npx, "remotion", "render", "src/index.tsx", "PremiumMotion", str(output),
        f"--props={props_path}", "--codec=h264", "--crf=18", "--pixel-format=yuv420p",
        "--concurrency=1", "--log=error",
    ]
    if CHROME.exists():
        cmd.append(f"--browser-executable={CHROME}")
    temp_dir = (output.parent / ".remotion-temp").resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    subprocess.run(cmd, cwd=REMOTION, check=True, env=env)
    if not output.exists() or output.stat().st_size < 10_000:
        raise RuntimeError("Remotion không tạo được video PremiumMotion hợp lệ")
    return output
