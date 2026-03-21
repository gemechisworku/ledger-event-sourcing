"""AuditLedger aggregate — append-only audit stream."""

from __future__ import annotations

from typing import Any

from ledger.domain.streams import audit_stream_id


class AuditLedgerAggregate:
    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.version: int = 0
        self.event_count: int = 0

    @property
    def stream_id(self) -> str:
        return audit_stream_id(self.entity_type, self.entity_id)

    @classmethod
    async def load(cls, store: Any, entity_type: str, entity_id: str) -> AuditLedgerAggregate:
        agg = cls(entity_type=entity_type, entity_id=entity_id)
        events = await store.load_stream(agg.stream_id)
        for ev in events:
            agg._apply(ev)
        agg.version = await store.stream_version(agg.stream_id)
        return agg

    def _apply(self, event: dict) -> None:
        self.version = int(event["stream_position"])
        self.event_count += 1
