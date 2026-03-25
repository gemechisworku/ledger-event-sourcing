"""ApplicationSummary projection — one row per loan application."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.projections.base import Projection
from src.schema.events import StoredEvent


def _app_id_from_stream(stream_id: str) -> str | None:
    for prefix in ("loan-", "credit-", "fraud-", "compliance-"):
        if stream_id.startswith(prefix):
            return stream_id[len(prefix) :]
    return None


def _parse_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    return None


class ApplicationSummaryProjection(Projection):
    name = "application_summary"

    LOAN_EVENTS = frozenset(
        {
            "ApplicationSubmitted",
            "CreditAnalysisRequested",
            "FraudScreeningRequested",
            "ComplianceCheckRequested",
            "DecisionRequested",
            "DecisionGenerated",
            "HumanReviewRequested",
            "HumanReviewCompleted",
            "ApplicationApproved",
            "ApplicationDeclined",
        }
    )
    CREDIT_EVENTS = frozenset({"CreditAnalysisCompleted", "CreditRecordOpened"})
    FRAUD_EVENTS = frozenset({"FraudScreeningCompleted"})
    COMP_EVENTS = frozenset({"ComplianceCheckCompleted"})

    def __init__(self, store) -> None:
        self._store = store
        self._mem: dict[str, dict] = {}

    def handles(self, event: StoredEvent) -> bool:
        return event.event_type in (
            self.LOAN_EVENTS | self.CREDIT_EVENTS | self.FRAUD_EVENTS | self.COMP_EVENTS
        )

    async def apply(self, event: StoredEvent) -> None:
        app_id = _app_id_from_stream(event.stream_id)
        if not app_id:
            return
        p = event.payload or {}
        et = event.event_type
        rec_at = _parse_ts(event.recorded_at) or datetime.utcnow()

        row = await self._load_row(app_id)
        row["application_id"] = app_id
        row["last_event_type"] = et
        row["last_event_at"] = rec_at
        row["last_global_position"] = int(event.global_position)

        if et == "ApplicationSubmitted":
            row["state"] = "SUBMITTED"
            row["applicant_id"] = p.get("applicant_id")
            row["requested_amount_usd"] = p.get("requested_amount_usd")
        elif et == "CreditAnalysisCompleted":
            row["state"] = "CREDIT_ANALYSIS_COMPLETE"
            dec = p.get("decision") or {}
            if isinstance(dec, dict):
                row["risk_tier"] = dec.get("risk_tier")
        elif et == "FraudScreeningCompleted":
            row["fraud_score"] = p.get("fraud_score")
        elif et == "ComplianceCheckCompleted":
            row["compliance_status"] = str(p.get("overall_verdict", ""))
        elif et == "DecisionGenerated":
            row["decision"] = p.get("recommendation")
            row["state"] = "PENDING_DECISION"
        elif et == "HumanReviewCompleted":
            row["human_reviewer_id"] = p.get("reviewer_id")
        elif et == "ApplicationApproved":
            row["state"] = "APPROVED"
            row["approved_amount_usd"] = p.get("approved_amount_usd")
            row["final_decision_at"] = _parse_ts(p.get("approved_at")) or rec_at
        elif et == "ApplicationDeclined":
            row["state"] = "DECLINED"
            row["final_decision_at"] = _parse_ts(p.get("declined_at")) or rec_at

        sess = p.get("session_id")
        if sess and isinstance(sess, str):
            sessions = list(row.get("agent_sessions_completed") or [])
            if sess not in sessions:
                sessions.append(sess)
            row["agent_sessions_completed"] = sessions[:200]

        await self._save_row(row)

    async def _load_row(self, app_id: str) -> dict:
        pool = getattr(self._store, "pool", None) or getattr(self._store, "_pool", None)
        if pool is None:
            return dict(self._mem.get(app_id, {}))
        async with pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT * FROM projection_application_summary WHERE application_id = $1", app_id
            )
        if not r:
            return {}
        return dict(r)

    async def _save_row(self, row: dict) -> None:
        pool = getattr(self._store, "pool", None) or getattr(self._store, "_pool", None)
        aid = row["application_id"]
        sessions = row.get("agent_sessions_completed")
        if isinstance(sessions, list):
            sessions_json = json.dumps(sessions)
        else:
            sessions_json = sessions or "[]"

        if pool is None:
            self._mem[aid] = {**row, "agent_sessions_completed": json.loads(sessions_json)}
            return

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO projection_application_summary (
                  application_id, state, applicant_id, requested_amount_usd, approved_amount_usd,
                  risk_tier, fraud_score, compliance_status, decision, agent_sessions_completed,
                  last_event_type, last_event_at, human_reviewer_id, final_decision_at,
                  last_global_position, updated_at
                ) VALUES (
                  $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14, $15, NOW()
                )
                ON CONFLICT (application_id) DO UPDATE SET
                  state = EXCLUDED.state,
                  applicant_id = COALESCE(EXCLUDED.applicant_id, projection_application_summary.applicant_id),
                  requested_amount_usd = COALESCE(EXCLUDED.requested_amount_usd, projection_application_summary.requested_amount_usd),
                  approved_amount_usd = COALESCE(EXCLUDED.approved_amount_usd, projection_application_summary.approved_amount_usd),
                  risk_tier = COALESCE(EXCLUDED.risk_tier, projection_application_summary.risk_tier),
                  fraud_score = COALESCE(EXCLUDED.fraud_score, projection_application_summary.fraud_score),
                  compliance_status = COALESCE(EXCLUDED.compliance_status, projection_application_summary.compliance_status),
                  decision = COALESCE(EXCLUDED.decision, projection_application_summary.decision),
                  agent_sessions_completed = EXCLUDED.agent_sessions_completed,
                  last_event_type = EXCLUDED.last_event_type,
                  last_event_at = EXCLUDED.last_event_at,
                  human_reviewer_id = COALESCE(EXCLUDED.human_reviewer_id, projection_application_summary.human_reviewer_id),
                  final_decision_at = COALESCE(EXCLUDED.final_decision_at, projection_application_summary.final_decision_at),
                  last_global_position = EXCLUDED.last_global_position,
                  updated_at = NOW()
                """,
                aid,
                row.get("state") or "UNKNOWN",
                row.get("applicant_id"),
                row.get("requested_amount_usd"),
                row.get("approved_amount_usd"),
                row.get("risk_tier"),
                row.get("fraud_score"),
                row.get("compliance_status"),
                row.get("decision"),
                sessions_json,
                row.get("last_event_type"),
                row.get("last_event_at"),
                row.get("human_reviewer_id"),
                row.get("final_decision_at"),
                int(row.get("last_global_position") or 0),
            )
