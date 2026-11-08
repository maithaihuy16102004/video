"""Zero-cost ledger.  paid_cost_usd must remain 0.00 under current policy."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CostLedger:
    reasoning_calls_free_text: int = 0
    reasoning_call_failures: int = 0
    reasoning_cache_hits: int = 0
    offline_reasoning_runs: int = 0
    paid_api_calls: int = 0
    paid_image_calls: int = 0
    paid_cost_usd: float = 0.0
    local_renders: int = 0
    render_seconds: float = 0.0
    planning_seconds: float = 0.0
    events: list[dict] = field(default_factory=list)
    billing_note: str = ("Gemini text calls use the user's existing GEMINI_API_KEY within its free quota. "
                         "Billing tier cannot be verified via the API; no image-generation or paid endpoints are called.")

    def note(self, kind: str, **kw) -> None:
        self.events.append({"t": round(time.time(), 3), "kind": kind, **kw})

    def assert_zero_cost(self) -> None:
        if self.paid_api_calls or self.paid_image_calls or self.paid_cost_usd:
            raise RuntimeError("ZERO_COST_POLICY_VIOLATION")

    def merge(self, other: "CostLedger") -> None:
        for k in ("reasoning_calls_free_text", "reasoning_call_failures", "reasoning_cache_hits",
                  "offline_reasoning_runs", "paid_api_calls", "paid_image_calls", "local_renders"):
            setattr(self, k, getattr(self, k) + getattr(other, k))
        self.paid_cost_usd += other.paid_cost_usd
        self.render_seconds += other.render_seconds
        self.planning_seconds += other.planning_seconds
        self.events.extend(other.events)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["paid_cost_usd"] = round(self.paid_cost_usd, 2)
        d["render_seconds"] = round(self.render_seconds, 3)
        d["planning_seconds"] = round(self.planning_seconds, 3)
        d["zero_cost_guarantee_met"] = self.paid_cost_usd == 0 and self.paid_api_calls == 0 and self.paid_image_calls == 0
        return d

    def write(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
