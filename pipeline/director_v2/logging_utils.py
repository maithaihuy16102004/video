"""Structured JSONL run log. Every message passes through redact() before hitting disk/console."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

from .secret_store import redact


class RunLogger:
    def __init__(self, path: Optional[Path] = None, echo: bool = True):
        self.path = path
        self.echo = echo
        self._t0 = time.perf_counter()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def log(self, stage: str, event: str, **data: Any) -> None:
        rec = {
            "t": round(time.perf_counter() - self._t0, 3),
            "stage": stage,
            "event": event,
            **data,
        }
        line = redact(json.dumps(rec, ensure_ascii=False, default=str))
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if self.echo:
            summary = " ".join(f"{k}={v}" for k, v in data.items() if not isinstance(v, (list, dict)))
            msg = redact(f"[dv2 {rec['t']:7.2f}s] {stage:<22} {event} {summary}")
            try:
                print(msg, file=sys.stderr)
            except UnicodeEncodeError:
                print(msg.encode("ascii", "replace").decode("ascii"), file=sys.stderr)


NULL_LOGGER = RunLogger(None, echo=False)
