"""
PostgreSQL integrity + tamper detection (optional; skips if DB unavailable).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

import asyncpg

from src.event_store import EventStore
from src.integrity.audit_chain import run_integrity_check
from src.upcasters import default_upcaster_registry
from tests.pg_helpers import candidate_postgres_urls

_AUDIT_STREAM = "audit-loan-test-intpg"


async def _cleanup_audit_stream(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM outbox WHERE event_id IN (SELECT event_id FROM events WHERE stream_id = $1)",
            _AUDIT_STREAM,
        )
        await conn.execute("DELETE FROM events WHERE stream_id = $1", _AUDIT_STREAM)
        await conn.execute("DELETE FROM event_streams WHERE stream_id = $1", _AUDIT_STREAM)


@pytest.fixture
async def pg_store():
    last_exc: Exception | None = None
    for url in candidate_postgres_urls():
        store = EventStore(url, upcaster_registry=default_upcaster_registry())
        try:
            await store.connect()
            assert store._pool is not None
            await _cleanup_audit_stream(store._pool)
            yield store
            await store.close()
            return
        except Exception as exc:
            last_exc = exc
            if getattr(store, "_pool", None) is not None:
                await store.close()
    pytest.skip(
        "PostgreSQL not reachable for integrity PG test: " f"{last_exc!r}"
    )


@pytest.mark.asyncio
async def test_integrity_tamper_detected_postgres(pg_store: EventStore):
    await pg_store.append(
        _AUDIT_STREAM,
        [{"event_type": "AuditNote", "event_version": 1, "payload": {"note": "clean"}}],
        expected_version=-1,
    )
    r1 = await run_integrity_check(pg_store, "loan", "test-intpg")
    assert r1.tamper_detected is False
    assert r1.chain_valid is True

    assert pg_store._pool is not None
    async with pg_store._pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET payload = $1::jsonb WHERE stream_id = $2 AND event_type = $3",
            '{"note": "tampered"}',
            _AUDIT_STREAM,
            "AuditNote",
        )

    r2 = await run_integrity_check(pg_store, "loan", "test-intpg")
    assert r2.tamper_detected is True
    assert r2.chain_valid is False
