"""Agent performance aggregates per agent_id + model_version."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.projections.base import Projection
from src.schema.events import StoredEvent


class AgentPerformanceLedgerProjection(Projection):
    name = "agent_performance"

    TYPES = frozenset({"CreditAnalysisCompleted", "DecisionGenerated", "HumanReviewCompleted"})

    def __init__(self, store) -> None:
        self._store = store
        self._mem: dict[tuple[str, str], dict] = {}

    def handles(self, event: StoredEvent) -> bool:
        return event.event_type in self.TYPES

    async def apply(self, event: StoredEvent) -> None:
        p = event.payload or {}
        et = event.event_type
        now = datetime.now(timezone.utc)

        if et == "CreditAnalysisCompleted":
            agent_id = "credit_analysis"
            mv = str(p.get("model_version") or "unknown")
            dec = p.get("decision") or {}
            conf = float(dec.get("confidence") or 0.0)
            dur = int(p.get("analysis_duration_ms") or 0)
            row = await self._load(agent_id, mv)
            row["analyses_completed"] = int(row.get("analyses_completed") or 0) + 1
            n = int(row.get("samples_confidence") or 0)
            row["samples_confidence"] = n + 1
            row["avg_confidence_score"] = (
                (float(row.get("avg_confidence_score") or 0.0) * n + conf) / (n + 1) if n + 1 else conf
            )
            nd = int(row.get("samples_duration_ms") or 0)
            row["samples_duration_ms"] = nd + 1
            row["avg_duration_ms"] = (
                (float(row.get("avg_duration_ms") or 0.0) * nd + dur) / (nd + 1) if nd + 1 else float(dur)
            )
            row["last_seen_at"] = now
            row.setdefault("first_seen_at", now)
            await self._save(agent_id, mv, row)

        elif et == "DecisionGenerated":
            agent_id = "orchestrator"
            mv = "unknown"
            mvs = p.get("model_versions") or {}
            if isinstance(mvs, dict) and mvs:
                mv = str(next(iter(mvs.values())))
            rec = str(p.get("recommendation") or "").upper()
            row = await self._load(agent_id, mv)
            row["decisions_generated"] = int(row.get("decisions_generated") or 0) + 1
            n = int(row.get("samples_decisions") or 0)
            row["samples_decisions"] = n + 1
            if "APPROVE" in rec:
                row["counts_approve"] = int(row.get("counts_approve") or 0) + 1
            elif "DECLINE" in rec:
                row["counts_decline"] = int(row.get("counts_decline") or 0) + 1
            else:
                row["counts_refer"] = int(row.get("counts_refer") or 0) + 1
            total = int(row["samples_decisions"])
            row["approve_rate"] = float(row.get("counts_approve") or 0) / total
            row["decline_rate"] = float(row.get("counts_decline") or 0) / total
            row["refer_rate"] = float(row.get("counts_refer") or 0) / total
            row["last_seen_at"] = now
            row.setdefault("first_seen_at", now)
            await self._save(agent_id, mv, row)

        elif et == "HumanReviewCompleted":
            agent_id = "human_review"
            mv = "manual"
            row = await self._load(agent_id, mv)
            row["counts_override"] = int(row.get("counts_override") or 0) + (1 if p.get("override") else 0)
            total = int(row.get("decisions_generated") or 0) + 1
            row["decisions_generated"] = total
            row["human_override_rate"] = float(row["counts_override"]) / max(total, 1)
            row["last_seen_at"] = now
            row.setdefault("first_seen_at", now)
            await self._save(agent_id, mv, row)

    async def _load(self, agent_id: str, mv: str) -> dict:
        pool = getattr(self._store, "pool", None) or getattr(self._store, "_pool", None)
        if pool is None:
            return dict(self._mem.get((agent_id, mv), {}))
        async with pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT * FROM projection_agent_performance WHERE agent_id = $1 AND model_version = $2",
                agent_id,
                mv,
            )
        return dict(r) if r else {}

    async def _save(self, agent_id: str, mv: str, row: dict) -> None:
        pool = getattr(self._store, "pool", None) or getattr(self._store, "_pool", None)
        if pool is None:
            self._mem[(agent_id, mv)] = row
            return

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO projection_agent_performance (
                  agent_id, model_version, analyses_completed, decisions_generated,
                  avg_confidence_score, avg_duration_ms,
                  approve_rate, decline_rate, refer_rate, human_override_rate,
                  first_seen_at, last_seen_at,
                  samples_confidence, samples_duration_ms, samples_decisions,
                  counts_approve, counts_decline, counts_refer, counts_override
                ) VALUES (
                  $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
                )
                ON CONFLICT (agent_id, model_version) DO UPDATE SET
                  analyses_completed = EXCLUDED.analyses_completed,
                  decisions_generated = EXCLUDED.decisions_generated,
                  avg_confidence_score = EXCLUDED.avg_confidence_score,
                  avg_duration_ms = EXCLUDED.avg_duration_ms,
                  approve_rate = EXCLUDED.approve_rate,
                  decline_rate = EXCLUDED.decline_rate,
                  refer_rate = EXCLUDED.refer_rate,
                  human_override_rate = EXCLUDED.human_override_rate,
                  first_seen_at = COALESCE(projection_agent_performance.first_seen_at, EXCLUDED.first_seen_at),
                  last_seen_at = EXCLUDED.last_seen_at,
                  samples_confidence = EXCLUDED.samples_confidence,
                  samples_duration_ms = EXCLUDED.samples_duration_ms,
                  samples_decisions = EXCLUDED.samples_decisions,
                  counts_approve = EXCLUDED.counts_approve,
                  counts_decline = EXCLUDED.counts_decline,
                  counts_refer = EXCLUDED.counts_refer,
                  counts_override = EXCLUDED.counts_override
                """,
                agent_id,
                mv,
                int(row.get("analyses_completed") or 0),
                int(row.get("decisions_generated") or 0),
                row.get("avg_confidence_score"),
                row.get("avg_duration_ms"),
                row.get("approve_rate"),
                row.get("decline_rate"),
                row.get("refer_rate"),
                row.get("human_override_rate"),
                row.get("first_seen_at"),
                row.get("last_seen_at"),
                int(row.get("samples_confidence") or 0),
                int(row.get("samples_duration_ms") or 0),
                int(row.get("samples_decisions") or 0),
                int(row.get("counts_approve") or 0),
                int(row.get("counts_decline") or 0),
                int(row.get("counts_refer") or 0),
                int(row.get("counts_override") or 0),
            )
