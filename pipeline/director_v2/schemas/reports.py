"""Validation and cost reports."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from .core import DV2Model


class ValidationIssue(DV2Model):
    severity: str                            # INFO | WARN | ERROR
    code: str
    stage: str
    message: str
    shot_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(DV2Model):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class CostLine(DV2Model):
    item: str
    model: Optional[str] = None
    count: int = 0
    unit_price_usd: Optional[float] = None
    subtotal_usd: Optional[float] = None
    note: str = ""


class CostEstimate(DV2Model):
    currency: str = "USD"
    quality: str
    dry_run: bool
    lines: list[CostLine] = Field(default_factory=list)
    expected_total_usd: Optional[float] = None
    min_total_usd: Optional[float] = None
    max_total_usd: Optional[float] = None
    counters: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
