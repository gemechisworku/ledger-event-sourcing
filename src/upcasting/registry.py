"""
UpcasterRegistry — transform older event versions on read only.
Never mutates persisted rows.
"""
from __future__ import annotations

from typing import Any

from src.models.events import StoredEvent


class UpcasterRegistry:
    """Apply on load_stream / load_all — never on append()."""

    def __init__(self) -> None:
        self._chains: dict[str, dict[int, Any]] = {}

    def register(self, event_type: str, from_version: int):
        """Decorator: register fn(payload: dict) -> dict for one version step."""

        def decorator(fn):
            self._chains.setdefault(event_type, {})[from_version] = fn
            return fn

        return decorator

    def upcast(self, event: dict) -> dict:
        et = event.get("event_type")
        v = int(event.get("event_version", 1))
        chain = self._chains.get(et, {})
        out = dict(event)
        while v in chain:
            out["payload"] = chain[v](dict(out.get("payload", {})))
            v += 1
            out["event_version"] = v
        return out


def upcast_stored_event(registry: UpcasterRegistry | None, ev: StoredEvent) -> StoredEvent:
    if registry is None:
        return ev
    d = {
        "event_id": ev.event_id,
        "stream_id": ev.stream_id,
        "stream_position": ev.stream_position,
        "global_position": ev.global_position,
        "event_type": ev.event_type,
        "event_version": ev.event_version,
        "payload": dict(ev.payload),
        "metadata": dict(ev.metadata),
        "recorded_at": ev.recorded_at,
    }
    d = registry.upcast(d)
    return StoredEvent(**d)
