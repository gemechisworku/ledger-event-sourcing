"""Compliance audit read model + temporal replay from stream."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.domain.streams import compliance_stream_id
from src.projections.base import Projection
from src.schema.events import StoredEvent


def _parse_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    return None


class ComplianceAuditProjection(Projection):
    name = "compliance_audit"

    TYPES = frozenset(
        {
            "ComplianceCheckInitiated",
            "ComplianceRulePassed",
            "ComplianceRuleFailed",
            "ComplianceRuleNoted",
            "ComplianceCheckCompleted",
        }
    )

    def __init__(self, store) -> None:
        self._store = store
        self._mem: dict[str, dict] = {}

    def handles(self, event: StoredEvent) -> bool:
        return event.event_type in self.TYPES

    async def apply(self, event: StoredEvent) -> None:
        p = event.payload or {}
        app_id = p.get("application_id")
        if not app_id:
            return
        row = await self._load_row(app_id)
        rules = list(row.get("rules_json") or [])
        if isinstance(rules, str):
            rules = json.loads(rules)

        if event.event_type == "ComplianceCheckInitiated":
            row["regulation_set_version"] = p.get("regulation_set_version")
        elif event.event_type in (
            "ComplianceRulePassed",
            "ComplianceRuleFailed",
            "ComplianceRuleNoted",
        ):
            rules.append(
                {
                    "event_type": event.event_type,
                    "rule_id": p.get("rule_id"),
                    "rule_name": p.get("rule_name"),
                    "rule_version": p.get("rule_version"),
                    "recorded_at": event.recorded_at,
                }
            )
        elif event.event_type == "ComplianceCheckCompleted":
            row["overall_verdict"] = str(p.get("overall_verdict", ""))

        row["rules_json"] = rules[:500]
        row["last_global_position"] = int(event.global_position)
        await self._save_row(app_id, row)

    async def get_current_compliance(self, application_id: str) -> dict[str, Any]:
        return await self._load_row(application_id)

    async def get_compliance_at(self, application_id: str, as_of: datetime) -> dict[str, Any]:
        """Replay compliance stream up to as_of (inclusive)."""
        sid = compliance_stream_id(application_id)
        stream = await self._store.load_stream(sid)
        rules: list[dict] = []
        overall_verdict: str | None = None
        regulation_set_version: str | None = None
        for ev in stream:
            ts = _parse_ts(ev.recorded_at)
            if ts and ts > as_of:
                break
            p = ev.payload or {}
            if ev.event_type == "ComplianceCheckInitiated":
                regulation_set_version = p.get("regulation_set_version")
            elif ev.event_type in (
                "ComplianceRulePassed",
                "ComplianceRuleFailed",
                "ComplianceRuleNoted",
            ):
                rules.append(
                    {
                        "event_type": ev.event_type,
                        "rule_id": p.get("rule_id"),
                        "rule_name": p.get("rule_name"),
                    }
                )
            elif ev.event_type == "ComplianceCheckCompleted":
                overall_verdict = str(p.get("overall_verdict", ""))
        return {
            "application_id": application_id,
            "overall_verdict": overall_verdict,
            "rules_json": rules,
            "regulation_set_version": regulation_set_version,
        }

    async def rebuild_from_scratch(self) -> None:
        pool = getattr(self._store, "pool", None) or getattr(self._store, "_pool", None)
        if pool is None:
            self._mem.clear()
            await self._store.save_checkpoint(self.name, 0)
            async for ev in self._store.load_all(0):
                if self.handles(ev):
                    await self.apply(ev)
            return

        async with pool.acquire() as conn:
            await conn.execute("TRUNCATE projection_compliance_audit")
        await self._store.save_checkpoint(self.name, 0)
        async for ev in self._store.load_all(0):
            if self.handles(ev):
                await self.apply(ev)

    async def _load_row(self, app_id: str) -> dict:
        pool = getattr(self._store, "pool", None) or getattr(self._store, "_pool", None)
        if pool is None:
            return dict(self._mem.get(app_id, {}))
        async with pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT * FROM projection_compliance_audit WHERE application_id = $1", app_id
            )
        if not r:
            return {}
        return dict(r)

    async def _save_row(self, app_id: str, row: dict) -> None:
        pool = getattr(self._store, "pool", None) or getattr(self._store, "_pool", None)
        rj = row.get("rules_json")
        if isinstance(rj, list):
            rj_s = json.dumps(rj)
        else:
            rj_s = rj or "[]"

        if pool is None:
            self._mem[app_id] = {
                **row,
                "application_id": app_id,
                "rules_json": json.loads(rj_s) if isinstance(rj_s, str) else rj,
            }
            return

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO projection_compliance_audit (
                  application_id, overall_verdict, rules_json, regulation_set_version,
                  last_global_position, updated_at
                ) VALUES ($1, $2, $3::jsonb, $4, $5, NOW())
                ON CONFLICT (application_id) DO UPDATE SET
                  overall_verdict = EXCLUDED.overall_verdict,
                  rules_json = EXCLUDED.rules_json,
                  regulation_set_version = COALESCE(EXCLUDED.regulation_set_version, projection_compliance_audit.regulation_set_version),
                  last_global_position = EXCLUDED.last_global_position,
                  updated_at = NOW()
                """,
                app_id,
                row.get("overall_verdict"),
                rj_s,
                row.get("regulation_set_version"),
                int(row.get("last_global_position") or 0),
            )
