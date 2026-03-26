"""
Registered upcasters and inference strategies (read path only).

CreditAnalysisCompleted v1→v2:
  - `model_version`: if missing, infer `legacy-pre-YYYY` from `completed_at` / `recorded_at` when present.
  - `confidence_score`: explicit null when unknown at v1; if nested `decision.confidence` exists, may be mirrored.
  - `regulatory_basis`: infer from active `rule_version` entries when present, else [].

DecisionGenerated v1→v2:
  - `model_versions`: map each `contributing_sessions` id to a placeholder unless explicit map exists in payload.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.upcasting.registry import UpcasterRegistry


def _infer_model_version_stamp(payload: dict) -> str:
    raw = payload.get("completed_at") or payload.get("recorded_at")
    if not raw:
        return "legacy-pre-2026"
    try:
        if isinstance(raw, datetime):
            y = raw.year
        else:
            y = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).year
        return f"legacy-pre-{y}"
    except Exception:
        return "legacy-pre-2026"


def default_upcaster_registry() -> UpcasterRegistry:
    """Built-in v1 → current for known event types."""

    r = UpcasterRegistry()

    @r.register("CreditAnalysisCompleted", 1)
    def _credit_v1_to_2(payload: dict) -> dict:
        p = dict(payload)
        if "model_version" not in p:
            p["model_version"] = _infer_model_version_stamp(p)
        p.setdefault("regulatory_basis", [])
        rb = p.get("regulatory_basis")
        if isinstance(rb, list) and rb:
            pass
        elif (payload.get("rule_versions") or payload.get("active_rule_versions")):
            p["regulatory_basis"] = list(payload.get("rule_versions") or payload.get("active_rule_versions") or [])
        if "confidence_score" not in p:
            p["confidence_score"] = None
        dec = p.get("decision")
        if p.get("confidence_score") is None and isinstance(dec, dict) and "confidence" in dec:
            p["confidence_score"] = dec.get("confidence")
        return p

    @r.register("DecisionGenerated", 1)
    def _decision_v1_to_2(payload: dict) -> dict:
        p = dict(payload)
        mv = dict(p.get("model_versions") or {})
        for sid in p.get("contributing_sessions") or []:
            mv.setdefault(str(sid), "unknown@legacy-bindings")
        p["model_versions"] = mv
        return p

    return r
