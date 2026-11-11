"""Adapter to the REAL V5.1 code in ~/workspace/video-upstream/.

This module imports from the read-only upstream clone (never copied,
never edited) via sys.path. Every import is lazy and every failure
returns a precise diagnostic instead of a mock success:

- StudioScriptV1Parser: pure stdlib, WORKS on this VM.
- MemeSoundResolver: WORKS with an explicit catalog path
  (assets/memes/catalog.json, 188 memes, Linux paths resolved).
- V5UniversalStoryDirector (Gemini): BROKEN here — needs `pydantic`
  (ModuleNotFoundError) and GEMINI_API_KEY (unset). Its autonomous
  semantic fallback cannot run without the module import.
- VietNeuTTSAdapter: BROKEN here — needs the `vieneu` package
  (ModuleNotFoundError) and the local VieNeu model.
- Motion Canvas + Three.js render service: BROKEN here — hard-codes
  C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe
  (scripts/production_render_service.mjs:137).
- ffmpeg / ffprobe: AVAILABLE on this VM.
- hatch_gws_cli Drive: AVAILABLE (connected account).

Set AI_CLIP_UPSTREAM to override the clone location.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

UPSTREAM_ROOT = Path(
    os.environ.get("AI_CLIP_UPSTREAM", "")
    or Path.home() / "workspace" / "video-upstream"
)

CHROME_WINDOWS_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class UpstreamUnavailable(RuntimeError):
    """A real upstream dependency is missing. Not a mock — fail loud."""


def upstream_root() -> Path:
    if not UPSTREAM_ROOT.is_dir():
        raise UpstreamUnavailable(
            f"upstream clone not found at {UPSTREAM_ROOT} "
            "(expected ~/workspace/video-upstream/, head c4832c8)"
        )
    return UPSTREAM_ROOT


def _ensure_path() -> Path:
    root = upstream_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def parse_studio_script_v1(script_text: str) -> dict[str, Any]:
    """Real Studio Script V1 parse (pipeline/studio_script_v1_parser.py)."""
    root = _ensure_path()
    try:
        from pipeline.studio_script_v1_parser import StudioScriptV1Parser
    except Exception as exc:
        raise UpstreamUnavailable(
            f"cannot import StudioScriptV1Parser: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        pkg = StudioScriptV1Parser().parse(script_text)
        return pkg.to_dict()
    except Exception as exc:
        raise UpstreamUnavailable(
            f"StudioScriptV1Parser.parse failed: {type(exc).__name__}: {exc}"
        ) from exc


def resolve_meme(tag: str, catalog_path: Path | None = None) -> dict[str, Any]:
    """Real meme resolution (pipeline/meme_resolver.py + catalog.json)."""
    root = _ensure_path()
    catalog = catalog_path or root / "assets" / "memes" / "catalog.json"
    if not catalog.exists():
        raise UpstreamUnavailable(f"meme catalog missing: {catalog}")
    try:
        from pipeline.meme_resolver import MemeSoundResolver
    except Exception as exc:
        raise UpstreamUnavailable(
            f"cannot import MemeSoundResolver: {type(exc).__name__}: {exc}"
        ) from exc
    resolved = MemeSoundResolver(catalog_path=catalog).resolve(tag)
    return {
        "meme_id": resolved.meme_id,
        "title": resolved.title,
        "filename": resolved.filename,
        "exists": resolved.exists,
        "is_missing": resolved.is_missing,
        "error": resolved.error_message,
        "file_path": str(resolved.file_path),
        "gain_db": resolved.gain_db,
    }


def gemini_story_plan(script_text: str) -> dict[str, Any]:
    """Real Gemini story director (pipeline/universal/v5_story_director.py).

    Requires `pydantic` and GEMINI_API_KEY. On this VM both are
    missing, so this raises UpstreamUnavailable with the exact cause
    instead of returning a fabricated package.
    """
    root = _ensure_path()
    if not os.environ.get("GEMINI_API_KEY"):
        raise UpstreamUnavailable(
            "GEMINI_API_KEY is not set — V5UniversalStoryDirector cannot "
            "call Gemini (pipeline/universal/v5_story_director.py:90-91). "
            "Set it on Mai's Windows machine where the key lives."
        )
    try:
        from pipeline.universal.v5_story_director import V5UniversalStoryDirector
    except Exception as exc:
        raise UpstreamUnavailable(
            f"cannot import V5UniversalStoryDirector: {type(exc).__name__}: "
            f"{exc} — install the repo's Python dependencies on the "
            "machine that runs the renderer"
        ) from exc
    director = V5UniversalStoryDirector()
    return director.analyze_script(script_text)


def check_vieneu_available() -> tuple[bool, str]:
    """VieNeu-TTS availability probe (pipeline/universal/voice/vietneu_adapter.py)."""
    try:
        import vieneu  # noqa: F401
    except ModuleNotFoundError:
        return False, (
            "package 'vieneu' is not installed on this VM — "
            "VietNeuTTSAdapter (pipeline/universal/voice/vietneu_adapter.py:20) "
            "cannot load the Vieneu/OnnxV3LiteEngine. Install the VieNeu "
            "model + package on Mai's Windows machine."
        )
    return True, "vieneu package importable"


def check_render_available() -> tuple[bool, str]:
    """Motion Canvas + Three.js render availability probe.

    Auto-detects a launchable Chrome (see chrome_detect.py) instead of
    trusting the Windows path hard-coded in the upstream render service.
    """
    from .chrome_detect import detect_chrome

    render_service = upstream_root() / "scripts" / "production_render_service.mjs"
    if not render_service.exists():
        return False, f"render service missing: {render_service}"
    chrome_path, detail = detect_chrome()
    if chrome_path is not None:
        return True, (
            f"Chrome usable at {chrome_path} — pass it as executablePath "
            "to the Motion Canvas render service (upstream hard-codes a "
            "Windows path; do not use that on this machine)."
        )
    return False, (
        "Motion Canvas + Three.js renderer unavailable: " + detail + ". "
        "Fallback: frame-by-frame renderer (ai_clip_studio/animation "
        "primitives + reference implementation in "
        "~/workspace/acceptance_loop/v4/) — real joint animation, not a "
        "slideshow. Run the Motion Canvas render on Mai's Windows machine "
        "with Chrome installed."
    )


def diagnostics() -> dict[str, Any]:
    """One-shot availability report for all real dependencies."""
    ok_vieneu, vieneu_msg = check_vieneu_available()
    ok_render, render_msg = check_render_available()
    try:
        root = upstream_root()
        root_ok, root_msg = True, f"clone present at {root}"
    except UpstreamUnavailable as exc:
        root_ok, root_msg = False, str(exc)
    return {
        "upstream_clone": {"ok": root_ok, "detail": root_msg},
        "gemini_api_key": {
            "ok": bool(os.environ.get("GEMINI_API_KEY")),
            "detail": "GEMINI_API_KEY set" if os.environ.get("GEMINI_API_KEY")
                      else "GEMINI_API_KEY not set",
        },
        "vieneu_tts": {"ok": ok_vieneu, "detail": vieneu_msg},
        "motion_canvas_threejs_render": {"ok": ok_render, "detail": render_msg},
        "ffmpeg": {"ok": bool(_which("ffmpeg")), "detail": "ffmpeg on PATH"},
        "ffprobe": {"ok": bool(_which("ffprobe")), "detail": "ffprobe on PATH"},
    }


def _which(name: str) -> str | None:
    import shutil
    return shutil.which(name)
