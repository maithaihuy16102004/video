"""Shared secret loading for legacy pipeline scripts and Director V2.

Secrets are read ONLY from the process environment or a local, git-ignored
``.env`` / ``.env.local`` file at the repository root. Never hard-code keys.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LOADED = False


def load_dotenv(root: Path = ROOT) -> None:
    """Populate os.environ from .env/.env.local without overriding real env vars."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    for name in (".env.local", ".env"):
        path = root / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_gemini_api_key(required: bool = False) -> str:
    load_dotenv()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if required and not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to the environment or to a local .env file "
            "(see .env.example)."
        )
    return key


_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(key=)[^&\s\"']+", re.I),
    re.compile(r"(x-goog-api-key['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+", re.I),
]


def redact(text: object) -> str:
    """Remove anything that looks like an API key from text destined for logs."""
    out = str(text)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key and len(key) >= 8:
        out = out.replace(key, "***REDACTED***")
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "***REDACTED***", out)
    return out
