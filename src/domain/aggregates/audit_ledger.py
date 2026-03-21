"""AuditLedger aggregate — append-only audit stream.

Uses per-event dispatch: _apply delegates to _on_{EventType} methods.
"""

from __future__ import annotations

from typing import Any

from src.domain.streams import audit_stream_id
from src.schema.events import StoredEvent


class AuditLedgerAggregate:
    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.version: int = -1
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

    def _apply(self, event: StoredEvent) -> None:
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event)
        self.version = event.stream_position
        self.event_count += 1

    def _on_AuditIntegrityCheckRun(self, event: StoredEvent) -> None:
        pass
