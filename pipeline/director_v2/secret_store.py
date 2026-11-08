"""Secret access for Director V2. Delegates to pipeline/env_secrets.py (env or local .env only)."""
from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from env_secrets import get_gemini_api_key, load_dotenv, redact  # noqa: E402,F401
