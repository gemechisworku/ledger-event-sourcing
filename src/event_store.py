"""
src/event_store.py — PostgreSQL-backed EventStore
====================================================
Phase 1: append (OCC + outbox), load_stream, load_all, stream_version, get_event.
Phase 4: pass UpcasterRegistry via upcaster_registry for load paths.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
from uuid import UUID

import asyncpg

from src.schema.events import StoredEvent, StreamMetadata


from dataclasses import dataclass as _dc


@_dc(frozen=True)
class OptimisticConcurrencyError(Exception):
    """Raised when expected_version doesn't match current stream version."""
    stream_id: str
    expected: int
    actual: int

    def __str__(self) -> str:
        return f"OCC on '{self.stream_id}': expected v{self.expected}, actual v{self.actual}"


def _schema_sql() -> str:
    p = Path(__file__).resolve().parent / "schema.sql"
    return p.read_text(encoding="utf-8")


def _aggregate_type(stream_id: str) -> str:
    if "-" in stream_id:
        return stream_id.split("-", 1)[0]
    return "unknown"


def _row_to_event(row: asyncpg.Record) -> StoredEvent:
    payload = row["payload"]
    meta = row["metadata"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(meta, str):
        meta = json.loads(meta)
    return StoredEvent(
        event_id=row["event_id"],
        stream_id=row["stream_id"],
        stream_position=row["stream_position"],
        global_position=row["global_position"],
        event_type=row["event_type"],
        event_version=row["event_version"],
        payload=dict(payload) if isinstance(payload, dict) else payload,
        metadata=dict(meta) if isinstance(meta, dict) else meta,
        recorded_at=row["recorded_at"],
    )


class EventStore:
    """Append-only PostgreSQL event store."""

    def __init__(self, db_url: str, upcaster_registry=None):
        self.db_url = db_url
        self.upcasters = upcaster_registry
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=10)
        try:
            async with pool.acquire() as conn:
                await conn.execute(_schema_sql())
            self._pool = pool
        except Exception:
            await pool.close()
            raise

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def stream_version(self, stream_id: str) -> int:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT current_version FROM event_streams WHERE stream_id = $1",
                stream_id,
            )
            if row is None:
                return -1
            return int(row["current_version"])

    async def append(
        self,
        stream_id: str,
        events: list[dict],
        expected_version: int,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict | None = None,
    ) -> list[int]:
        assert self._pool is not None
        if not events:
            return []

        meta_base = dict(metadata or {})
        if causation_id:
            meta_base["causation_id"] = causation_id
        if correlation_id:
            meta_base["correlation_id"] = correlation_id

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT stream_id, current_version FROM event_streams "
                    "WHERE stream_id = $1 FOR UPDATE",
                    stream_id,
                )

                last = int(row["current_version"]) if row else 0
                if last == 0:
                    actual_for_occ = -1
                else:
                    actual_for_occ = last

                if actual_for_occ != expected_version:
                    raise OptimisticConcurrencyError(stream_id, expected_version, actual_for_occ)

                positions: list[int] = []
                n = len(events)
                for i, event in enumerate(events):
                    stream_pos = last + i + 1
                    em = dict(meta_base)
                    payload_json = json.dumps(event.get("payload", {}))
                    ev_ver = int(event.get("event_version", 1))
                    et = event["event_type"]

                    eid = await conn.fetchval(
                        """
                        INSERT INTO events (
                        stream_id, stream_position, event_type, event_version,
                        payload, metadata, recorded_at)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                        RETURNING event_id
                        """,
                        stream_id,
                        stream_pos,
                        et,
                        ev_ver,
                        payload_json,
                        json.dumps(em),
                        datetime.now(timezone.utc),
                    )

                    await conn.execute(
                        """
                        INSERT INTO outbox (event_id, destination, payload)
                        VALUES ($1, $2, $3::jsonb)
                        """,
                        eid,
                        "ledger:default",
                        json.dumps({"stream_id": stream_id, "stream_position": stream_pos, "event_type": et}),
                    )
                    positions.append(stream_pos)

                new_last = last + n
                agg = _aggregate_type(stream_id)

                if row is None:
                    await conn.execute(
                        """
                        INSERT INTO event_streams (stream_id, aggregate_type, current_version, metadata)
                        VALUES ($1, $2, $3, '{}'::jsonb)
                        """,
                        stream_id,
                        agg,
                        new_last,
                    )
                else:
                    await conn.execute(
                        "UPDATE event_streams SET current_version = $1 WHERE stream_id = $2",
                        new_last,
                        stream_id,
                    )

                return positions

    async def load_stream(
        self,
        stream_id: str,
        from_position: int = 0,
        to_position: int | None = None,
    ) -> list[StoredEvent]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            q = (
                "SELECT event_id, stream_id, stream_position, global_position, event_type, "
                "event_version, payload, metadata, recorded_at "
                "FROM events WHERE stream_id = $1 AND stream_position >= $2"
            )
            args: list[Any] = [stream_id, from_position]
            if to_position is not None:
                q += " AND stream_position <= $3"
                args.append(to_position)
            q += " ORDER BY stream_position ASC"
            rows = await conn.fetch(q, *args)
        out: list[StoredEvent] = [_row_to_event(r) for r in rows]
        if self.upcasters:
            out = [_upcast_stored(self.upcasters, e) for e in out]
        return out

    async def load_all(
        self,
        from_position: int = 0,
        event_types: list[str] | None = None,
        batch_size: int = 500,
    ) -> AsyncGenerator[StoredEvent, None]:
        assert self._pool is not None
        pos = from_position
        while True:
            async with self._pool.acquire() as conn:
                if event_types:
                    rows = await conn.fetch(
                        """
                        SELECT event_id, stream_id, stream_position, global_position, event_type,
                        event_version, payload, metadata, recorded_at
                        FROM events
                        WHERE global_position > $1 AND event_type = ANY($2::text[])
                        ORDER BY global_position ASC
                        LIMIT $3
                        """,
                        pos,
                        event_types,
                        batch_size,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT event_id, stream_id, stream_position, global_position, event_type,
                        event_version, payload, metadata, recorded_at
                        FROM events
                        WHERE global_position > $1
                        ORDER BY global_position ASC
                        LIMIT $2
                        """,
                        pos,
                        batch_size,
                    )
            if not rows:
                break
            for r in rows:
                e = _row_to_event(r)
                if self.upcasters:
                    e = _upcast_stored(self.upcasters, e)
                yield e
            pos = int(rows[-1]["global_position"])
            if len(rows) < batch_size:
                break

    async def get_event(self, event_id: UUID) -> StoredEvent | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT event_id, stream_id, stream_position, global_position, event_type, "
                "event_version, payload, metadata, recorded_at FROM events WHERE event_id = $1",
                event_id,
            )
        if not row:
            return None
        return _row_to_event(row)

    async def archive_stream(self, stream_id: str) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE event_streams SET archived_at = NOW() WHERE stream_id = $1",
                stream_id,
            )

    async def get_stream_metadata(self, stream_id: str) -> StreamMetadata | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT stream_id, aggregate_type, current_version, created_at, archived_at, metadata "
                "FROM event_streams WHERE stream_id = $1",
                stream_id,
            )
        if not row:
            return None
        m = row["metadata"]
        if isinstance(m, str):
            m = json.loads(m)
        return StreamMetadata(
            stream_id=row["stream_id"],
            aggregate_type=row["aggregate_type"],
            current_version=int(row["current_version"]),
            created_at=row["created_at"],
            archived_at=row["archived_at"],
            metadata=dict(m) if isinstance(m, dict) else m,
        )

    async def save_checkpoint(self, projection_name: str, position: int) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO projection_checkpoints (projection_name, last_position, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (projection_name) DO UPDATE SET last_position = $2, updated_at = NOW()
                """,
                projection_name,
                position,
            )

    async def load_checkpoint(self, projection_name: str) -> int:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_position FROM projection_checkpoints WHERE projection_name = $1",
                projection_name,
            )
        return int(row["last_position"]) if row else 0


# ─────────────────────────────────────────────────────────────────────────────
# Upcaster registry — Phase 4
# ─────────────────────────────────────────────────────────────────────────────


class UpcasterRegistry:
    """Transforms old event versions on load. Pure — never writes to DB."""

    def __init__(self):
        self._upcasters: dict[str, dict[int, Any]] = {}

    def upcaster(self, event_type: str, from_version: int, to_version: int):
        def decorator(fn):
            self._upcasters.setdefault(event_type, {})[from_version] = fn
            return fn

        return decorator

    def upcast(self, event: dict) -> dict:
        et = event["event_type"]
        v = event.get("event_version", 1)
        chain = self._upcasters.get(et, {})
        while v in chain:
            event["payload"] = chain[v](dict(event["payload"]))
            v += 1
            event["event_version"] = v
        return event


def _upcast_stored(registry: Any, ev: StoredEvent) -> StoredEvent:
    """Apply upcaster chain to a StoredEvent, returning a new immutable instance."""
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


# ─────────────────────────────────────────────────────────────────────────────
# In-memory — for tests/phase1 (0-based stream positions)
# ─────────────────────────────────────────────────────────────────────────────

import asyncio as _asyncio
from collections import defaultdict as _defaultdict
from datetime import datetime as _datetime
from uuid import uuid4 as _uuid4


class InMemoryEventStore:
    """Asyncio-safe in-memory store for unit tests (phase1). Same OCC semantics as PG."""

    def __init__(self):
        self.upcasters = None
        self._streams: dict[str, list[StoredEvent]] = _defaultdict(list)
        self._versions: dict[str, int] = {}
        self._global: list[StoredEvent] = []
        self._checkpoints: dict[str, int] = {}
        self._locks: dict[str, _asyncio.Lock] = _defaultdict(_asyncio.Lock)

    async def stream_version(self, stream_id: str) -> int:
        return self._versions.get(stream_id, -1)

    async def append(
        self,
        stream_id: str,
        events: list[dict],
        expected_version: int,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict | None = None,
    ) -> list[int]:
        async with self._locks[stream_id]:
            current = self._versions.get(stream_id, -1)
            if current != expected_version:
                raise OptimisticConcurrencyError(stream_id, expected_version, current)

            positions = []
            meta = {**(metadata or {})}
            if causation_id:
                meta["causation_id"] = causation_id
            if correlation_id:
                meta["correlation_id"] = correlation_id

            for i, event in enumerate(events):
                pos = current + 1 + i
                stored = StoredEvent(
                    event_id=str(_uuid4()),
                    stream_id=stream_id,
                    stream_position=pos,
                    global_position=len(self._global),
                    event_type=event["event_type"],
                    event_version=event.get("event_version", 1),
                    payload=dict(event.get("payload", {})),
                    metadata=dict(meta),
                    recorded_at=_datetime.now(timezone.utc).isoformat(),
                )
                self._streams[stream_id].append(stored)
                self._global.append(stored)
                positions.append(pos)

            self._versions[stream_id] = current + len(events)
            return positions

    async def load_stream(
        self,
        stream_id: str,
        from_position: int = 0,
        to_position: int | None = None,
    ) -> list[StoredEvent]:
        events = [
            e
            for e in self._streams.get(stream_id, [])
            if e.stream_position >= from_position
            and (to_position is None or e.stream_position <= to_position)
        ]
        return sorted(events, key=lambda e: e.stream_position)

    async def load_all(self, from_position: int = 0, batch_size: int = 500):
        for e in self._global:
            if e.global_position >= from_position:
                yield e

    async def get_event(self, event_id: str) -> StoredEvent | None:
        for e in self._global:
            if e.event_id == event_id:
                return e
        return None

    async def save_checkpoint(self, projection_name: str, position: int) -> None:
        self._checkpoints[projection_name] = position

    async def load_checkpoint(self, projection_name: str) -> int:
        return self._checkpoints.get(projection_name, 0)
