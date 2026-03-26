"""
Registered upcasters and inference strategies (read path only).

CreditAnalysisCompleted v1→v2:
  - `model_version`: missing in v1 payloads → default `"legacy-pre-2026"` (inference: pre-versioning store).
  - `regulatory_basis`: missing → `[]` (inference: no structured basis was captured).

DecisionGenerated v1→v2:
  - `model_versions`: missing → `{}` (inference: orchestrator did not record per-model map).
"""
from __future__ import annotations

from src.upcasting.registry import UpcasterRegistry


def default_upcaster_registry() -> UpcasterRegistry:
    """Built-in v1 → current for known event types."""

    r = UpcasterRegistry()

    @r.register("CreditAnalysisCompleted", 1)
    def _credit_v1_to_2(payload: dict) -> dict:
        p = dict(payload)
        p.setdefault("model_version", "legacy-pre-2026")
        p.setdefault("regulatory_basis", [])
        return p

    @r.register("DecisionGenerated", 1)
    def _decision_v1_to_2(payload: dict) -> dict:
        p = dict(payload)
        p.setdefault("model_versions", {})
        return p

    return r
