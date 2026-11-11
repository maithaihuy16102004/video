"""Chrome/Chromium auto-detection for the Motion Canvas + Three.js renderer.

The upstream render service (scripts/production_render_service.mjs:137)
hard-codes a Windows Chrome path. This module replaces that with
auto-detection on the machine that is actually running:

  1. $CHROME_PATH (explicit override)
  2. chromium / chromium-browser / google-chrome / google-chrome-stable
     on PATH
  3. /opt/meta-chromium/chrome (this Linux VM's browser)

A candidate only counts if it actually LAUNCHES: we run it headless with
--dump-dom about:blank and require exit code 0. On this VM
/opt/meta-chromium/chrome exists but FAILS to launch:
  "Hatch WebGL domain policy is required for browser startup"
(verified 2026-11-11 by direct run) — so detection correctly reports
"no usable Chrome" instead of pretending the path works. When no Chrome
is usable, the pipeline must fall back to the frame-by-frame renderer
(ai_clip_studio/animation + the reference implementation in
~/workspace/acceptance_loop/v4/) and say so in the job log — never
silently render a slideshow instead.
"""
import os
import shutil
import subprocess

CANDIDATE_NAMES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
)
KNOWN_PATHS = ("/opt/meta-chromium/chrome",)


def _probe(path: str, timeout: int = 30) -> tuple[bool, str]:
    """Launch the browser headless on about:blank. Returns (ok, detail)."""
    try:
        r = subprocess.run(
            [path, "--headless=new", "--no-sandbox", "--disable-gpu",
             "--disable-dev-shm-usage", "--dump-dom", "about:blank"],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, f"{path}: not executable"
    except subprocess.TimeoutExpired:
        return False, f"{path}: launch timed out after {timeout}s"
    err = (r.stderr or "").strip().splitlines()
    if r.returncode == 0 and "<html" in (r.stdout or ""):
        return True, f"{path}: launches OK"
    reason = err[0] if err else f"exit code {r.returncode}"
    return False, f"{path}: cannot launch ({reason})"


def detect_chrome() -> tuple[str | None, str]:
    """Return (usable_chrome_path_or_None, detail). Checks env, PATH,
    then known paths; every candidate is launch-probed."""
    candidates: list[str] = []
    env_path = os.environ.get("CHROME_PATH")
    if env_path:
        candidates.append(env_path)
    for name in CANDIDATE_NAMES:
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)
    for p in KNOWN_PATHS:
        if p not in candidates:
            candidates.append(p)
    tried: list[str] = []
    for path in candidates:
        ok, detail = _probe(path)
        tried.append(detail)
        if ok:
            return path, detail
    if not candidates:
        return None, ("no Chrome/Chromium found (checked $CHROME_PATH, "
                      "PATH, /opt/meta-chromium/chrome)")
    return None, "no usable Chrome: " + "; ".join(tried)
