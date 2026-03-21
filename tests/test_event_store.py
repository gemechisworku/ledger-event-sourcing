"""
tests/test_event_store.py
=========================
Phase 1 tests: PostgreSQL EventStore.

Requires Postgres and database (see .env.example). Override with TEST_DB_URL or DATABASE_URL.

Run: pytest tests/test_event_store.py -v
"""
import asyncio
import sys
from pathlib import Path

import asyncpg
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from src.event_store import EventStore, OptimisticConcurrencyError
from tests.pg_helpers import candidate_postgres_urls


async def _cleanup_pytest_event_streams(pool: asyncpg.Pool) -> None:
    """
    Remove rows left from prior test runs so expected_version=-1 (new stream) works.
    Only touches stream_ids used by this module (prefix test-).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM outbox o
            WHERE o.event_id IN (SELECT event_id FROM events WHERE stream_id LIKE 'test-%')
            """
        )
        await conn.execute("DELETE FROM events WHERE stream_id LIKE 'test-%'")
        await conn.execute("DELETE FROM event_streams WHERE stream_id LIKE 'test-%'")


@pytest.fixture
async def store():
    last_exc: Exception | None = None
    for url in candidate_postgres_urls():
        s = EventStore(url)
        try:
            await s.connect()
            assert s._pool is not None
            await _cleanup_pytest_event_streams(s._pool)
            yield s
            await s.close()
            return
        except Exception as exc:
            last_exc = exc
            if getattr(s, "_pool", None) is not None:
                await s.close()
    pytest.skip(
        "PostgreSQL not reachable (tried TEST_DB_URL, DATABASE_URL, APPLICANT_REGISTRY_URL, default): "
        f"{last_exc!r}"
    )

def _event(etype, n=1):
    return [{"event_type":etype,"event_version":1,"payload":{"seq":i,"test":True}} for i in range(n)]

@pytest.mark.asyncio
async def test_append_new_stream(store):
    positions = await store.append("test-new-001", _event("TestEvent"), expected_version=-1)
    assert positions == [1]

@pytest.mark.asyncio
async def test_append_existing_stream(store):
    await store.append("test-exist-001", _event("TestEvent"), expected_version=-1)
    positions = await store.append("test-exist-001", _event("TestEvent2"), expected_version=1)
    assert positions == [2]

@pytest.mark.asyncio
async def test_occ_wrong_version_raises(store):
    await store.append("test-occ-001", _event("E"), expected_version=-1)
    with pytest.raises(OptimisticConcurrencyError) as exc:
        await store.append("test-occ-001", _event("E"), expected_version=99)
    assert exc.value.expected == 99; assert exc.value.actual == 1

@pytest.mark.asyncio
async def test_concurrent_double_append_exactly_one_succeeds(store):
    """The critical OCC test: two concurrent appends, exactly one wins."""
    await store.append("test-concurrent-001", _event("Init"), expected_version=-1)
    results = await asyncio.gather(
        store.append("test-concurrent-001", _event("A"), expected_version=1),
        store.append("test-concurrent-001", _event("B"), expected_version=1),
        return_exceptions=True,
    )
    successes = [r for r in results if isinstance(r, list)]
    errors = [r for r in results if isinstance(r, OptimisticConcurrencyError)]
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(errors) == 1

@pytest.mark.asyncio
async def test_load_stream_ordered(store):
    await store.append("test-load-001", _event("E",3), expected_version=-1)
    events = await store.load_stream("test-load-001")
    assert len(events) == 3
    positions = [e["stream_position"] for e in events]
    assert positions == sorted(positions)

@pytest.mark.asyncio
async def test_stream_version(store):
    await store.append("test-ver-001", _event("E",4), expected_version=-1)
    assert await store.stream_version("test-ver-001") == 4

@pytest.mark.asyncio
async def test_stream_version_nonexistent(store):
    assert await store.stream_version("test-does-not-exist") == -1

@pytest.mark.asyncio
async def test_load_all_yields_in_global_order(store):
    await store.append("test-global-A", _event("E",2), expected_version=-1)
    await store.append("test-global-B", _event("E",2), expected_version=-1)
    all_events = [e async for e in store.load_all(from_position=0)]
    positions = [e["global_position"] for e in all_events]
    assert positions == sorted(positions)
