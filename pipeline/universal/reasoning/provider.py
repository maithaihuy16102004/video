"""Reasoning-provider interface, cache and provider factory.

The pipeline only talks to ``ReasoningProvider.complete_json(stage, system, prompt, context)``.
Model names come from PipelineConfig; nothing downstream knows which model answered.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from ..config import PipelineConfig
from ..ledger import CostLedger


class ReasoningUnavailable(RuntimeError):
    """Provider could not be reached / quota exhausted / no credentials."""


class ReasoningProvider(Protocol):
    name: str
    model: str

    def complete_json(self, stage: str, system: str, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        ...


class ReasoningCache:
    """Disk cache keyed by (script hash, config fingerprint, stage, provider, model, prompt hash)."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(stage: str, provider: str, model: str, config_fp: dict, payload: str) -> str:
        blob = json.dumps({"stage": stage, "provider": provider, "model": model, "cfg": config_fp,
                           "payload_sha": hashlib.sha256(payload.encode("utf-8")).hexdigest()}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> dict | None:
        p = self.root / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def put(self, key: str, value: dict, meta: dict) -> None:
        (self.root / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.root / f"{key}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


class CachedReasoner:
    """Wraps a provider with caching, ledger accounting and optional offline fallback."""

    def __init__(self, provider: ReasoningProvider, cache: ReasoningCache, config: PipelineConfig,
                 ledger: CostLedger, fallback: ReasoningProvider | None = None):
        self.provider = provider
        self.cache = cache
        self.config = config
        self.ledger = ledger
        self.fallback = fallback
        self.sources: dict[str, str] = {}

    def complete_json(self, stage: str, system: str, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        k = ReasoningCache.key(stage, self.provider.name, self.provider.model,
                               self.config.cache_fingerprint(), system + "\n" + prompt)
        hit = self.cache.get(k)
        if hit is not None:
            self.ledger.reasoning_cache_hits += 1
            self.ledger.note("REASONING_CACHE_HIT", stage=stage, provider=self.provider.name)
            self.sources[stage] = f"CACHE:{self.provider.name}"
            return hit
        try:
            out = self.provider.complete_json(stage, system, prompt, context)
            if self.provider.name == "offline":
                self.ledger.offline_reasoning_runs += 1
            else:
                self.ledger.reasoning_calls_free_text += 1
            self.ledger.note("REASONING_CALL", stage=stage, provider=self.provider.name, model=self.provider.model)
            self.cache.put(k, out, {"stage": stage, "provider": self.provider.name, "model": self.provider.model})
            self.sources[stage] = self.provider.name.upper()
            return out
        except ReasoningUnavailable as exc:
            self.ledger.reasoning_call_failures += 1
            self.ledger.note("REASONING_UNAVAILABLE", stage=stage, error=str(exc)[:200])
            if self.fallback is None:
                raise
            out = self.fallback.complete_json(stage, system, prompt, context)
            self.ledger.offline_reasoning_runs += 1
            self.sources[stage] = "OFFLINE_FALLBACK"
            return out


def build_reasoner(config: PipelineConfig, cache_dir: Path, ledger: CostLedger) -> CachedReasoner:
    from .offline import OfflineReasoningProvider
    offline = OfflineReasoningProvider()
    if config.reasoning_provider.lower() == "offline":
        return CachedReasoner(offline, ReasoningCache(cache_dir), config, ledger, fallback=None)
    from .gemini import GeminiReasoningProvider
    primary = GeminiReasoningProvider(model=config.reasoning_model)
    return CachedReasoner(primary, ReasoningCache(cache_dir), config, ledger,
                          fallback=offline if config.allow_offline_fallback else None)
