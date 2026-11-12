"""Honest environment capability probing for the Affiliate video side.

Every capability this package depends on is probed, never assumed:
ffmpeg/ffprobe + filters, OpenCV, OCR backends, and fonts. Results
are cached per process. Probing never downloads models and never
installs anything; engine instantiation (which may download OCR
models on first use) is a separate, explicit step in ``ocr.py``.

The report this module produces is the evidence for statements like
"PaddleOCR is unavailable here" — it records what was checked and
what was found.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------
# subprocess helper
# ---------------------------------------------------------------------


def run_command(argv: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess:
    """Run a command without a shell; capture text output."""
    return subprocess.run(argv, capture_output=True, text=True,
                          timeout=timeout, check=False)


# ---------------------------------------------------------------------
# ffmpeg / ffprobe
# ---------------------------------------------------------------------

@lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        return ""
    proc = run_command([exe, "-version"], timeout=15.0)
    first = (proc.stdout or "").splitlines()
    return first[0].strip() if first else ""


@lru_cache(maxsize=1)
def ffprobe_version() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        return ""
    proc = run_command([exe, "-version"], timeout=15.0)
    first = (proc.stdout or "").splitlines()
    return first[0].strip() if first else ""


@lru_cache(maxsize=1)
def available_filters() -> set[str]:
    exe = shutil.which("ffmpeg")
    if not exe:
        return set()
    proc = run_command([exe, "-hide_banner", "-filters"], timeout=30.0)
    names: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) <= 3:
            names.add(parts[1])
    return names


@lru_cache(maxsize=1)
def available_encoders() -> set[str]:
    exe = shutil.which("ffmpeg")
    if not exe:
        return set()
    proc = run_command([exe, "-hide_banner", "-encoders"], timeout=30.0)
    names: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(("V", "A", "S")):
            names.add(parts[1])
    return names


def has_filter(name: str) -> bool:
    return name in available_filters()


def has_encoder(name: str) -> bool:
    return name in available_encoders()


# Filters this package relies on, grouped by feature.
REQUIRED_FILTERS = {
    "scene_detect": ["select", "showinfo"],
    "silence": ["silencedetect"],
    "black_freeze": ["blackdetect", "freezedetect"],
    "text_overlay": ["drawbox", "drawtext"],
    "blur": ["boxblur", "crop", "overlay", "split"],
    "transform": ["hflip", "vflip", "transpose", "rotate", "crop", "scale",
                  "pad", "trim", "setpts", "atempo", "concat", "eq",
                  "colorbalance", "unsharp", "hqdn3d"],
    "stabilize": ["vidstabdetect", "vidstabtransform"],
    "reframe": ["crop", "scale", "pad", "gblur", "overlay", "split",
                "format"],
}


def filter_report() -> dict[str, Any]:
    available = available_filters()
    detail = {}
    for group, names in REQUIRED_FILTERS.items():
        missing = [n for n in names if n not in available]
        detail[group] = {"required": names, "missing": missing,
                         "ok": not missing}
    return detail


# ---------------------------------------------------------------------
# OpenCV (optional)
# ---------------------------------------------------------------------

@lru_cache(maxsize=1)
def cv2_info() -> dict[str, Any]:
    """Probe OpenCV without failing when it is absent."""
    if importlib.util.find_spec("cv2") is None:
        return {"available": False,
                "detail": "cv2 is not installed in this Python environment"}
    try:
        import cv2
    except Exception as exc:  # noqa: BLE001 - report, never crash
        return {"available": False, "detail": f"cv2 import failed: {exc}"}
    cascade_dir = Path(getattr(cv2, "data", None).haarcascades) \
        if hasattr(cv2, "data") else None
    cascade = None
    if cascade_dir is not None:
        candidate = cascade_dir / "haarcascade_frontalface_default.xml"
        cascade = str(candidate) if candidate.exists() else None
    return {
        "available": True,
        "version": getattr(cv2, "__version__", "unknown"),
        "haar_cascade": cascade,
        "has_inpaint": hasattr(cv2, "inpaint"),
        "has_mser": hasattr(cv2, "MSER_create"),
        "detail": "cv2 import ok",
    }


def cv2_available() -> bool:
    return bool(cv2_info().get("available"))


# ---------------------------------------------------------------------
# OCR backends (optional)
# ---------------------------------------------------------------------

def _spec_available(module: str) -> tuple[bool, str]:
    try:
        found = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError) as exc:
        return False, f"import probe failed: {exc}"
    if not found:
        return False, f"module {module!r} is not installed"
    return True, f"module {module!r} found"


@lru_cache(maxsize=1)
def ocr_backends() -> list[dict[str, Any]]:
    """Probe OCR backends by importability (no model download)."""
    backends = []
    ok, detail = _spec_available("paddleocr")
    backends.append({"name": "paddleocr", "available": ok,
                     "detail": detail,
                     "note": "PaddleOCR (paddlepaddle). Chinese: lang='ch'."})
    ok, detail = _spec_available("rapidocr_onnxruntime")
    backends.append({"name": "rapidocr_onnxruntime", "available": ok,
                     "detail": detail,
                     "note": "PaddleOCR models via ONNX Runtime; models "
                             "download on first engine use."})
    ok, detail = _spec_available("easyocr")
    backends.append({"name": "easyocr", "available": ok, "detail": detail,
                     "note": "EasyOCR (not wired to an adapter in Phase 1)."})
    return backends


def ocr_available() -> bool:
    return any(b["available"] for b in ocr_backends()
               if b["name"] in ("paddleocr", "rapidocr_onnxruntime"))


# ---------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------

_CJK_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
]
_VIETNAMESE_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _first_existing(candidates: list[str]) -> str | None:
    for path in candidates:
        if Path(path).is_file():
            return path
    return None


@lru_cache(maxsize=1)
def font_report() -> dict[str, Any]:
    cjk = _first_existing(_CJK_CANDIDATES)
    vietnamese = _first_existing(_VIETNAMESE_CANDIDATES)
    return {
        "cjk_font": cjk,
        "cjk_available": cjk is not None,
        "vietnamese_font": vietnamese,
        "vietnamese_available": vietnamese is not None,
        "detail": ("CJK font for rendering/detecting Chinese text; "
                   "Vietnamese-capable font for overlay/subtitle text."),
    }


def find_cjk_font() -> str | None:
    return font_report()["cjk_font"]


def find_vietnamese_font() -> str | None:
    return font_report()["vietnamese_font"]


# ---------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------

def capability_report() -> dict[str, Any]:
    """Everything Phase 1 needs to know about this environment."""
    filters = filter_report()
    return {
        "ffmpeg": ffmpeg_version(),
        "ffprobe": ffprobe_version(),
        "encoders": {"libx264": has_encoder("libx264"),
                     "aac": has_encoder("aac")},
        "filters": filters,
        "filters_ok": all(g["ok"] for g in filters.values()),
        "opencv": cv2_info(),
        "ocr_backends": ocr_backends(),
        "ocr_available": ocr_available(),
        "fonts": font_report(),
    }


def capability_report_json(indent: int = 2) -> str:
    return json.dumps(capability_report(), ensure_ascii=False, indent=indent)
