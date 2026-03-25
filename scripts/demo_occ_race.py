#!/usr/bin/env python3
"""
Live demo: two concurrent appends on the same stream with the same expected_version.
Exactly one wins; the other gets OptimisticConcurrencyError (then optional retry).

Run (Postgres required, same env as the API):
  uv run python scripts/demo_occ_race.py

Docker:
  docker compose exec api uv run python scripts/demo_occ_race.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from src.event_store import EventStore, OptimisticConcurrencyError
from src.upcasters import default_upcaster_registry


def _ev(name: str) -> list[dict]:
    return [{"event_type": name, "event_version": 1, "payload": {"demo": True, "event": name}}]


async def main() -> None:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DB_URL")
    if not url:
        print("Set DATABASE_URL or TEST_DB_URL to a PostgreSQL database.", file=sys.stderr)
        sys.exit(1)

    stream_id = "demo-occ-race-001"
    store = EventStore(url, upcaster_registry=default_upcaster_registry())
    await store.connect()
    try:
        # Clean slate for this stream
        pool = store._pool
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM outbox WHERE event_id IN (SELECT event_id FROM events WHERE stream_id = $1)", stream_id)
            await conn.execute("DELETE FROM events WHERE stream_id = $1", stream_id)
            await conn.execute("DELETE FROM event_streams WHERE stream_id = $1", stream_id)

        print("1) Initial append (expected_version=-1) …")
        await store.append(stream_id, _ev("Init"), expected_version=-1)
        v = await store.stream_version(stream_id)
        print(f"   stream_version after Init = {v}\n")

        print("2) Two concurrent tasks both call append(..., expected_version=1) …")
        results = await asyncio.gather(
            store.append(stream_id, _ev("ContenderA"), expected_version=1),
            store.append(stream_id, _ev("ContenderB"), expected_version=1),
            return_exceptions=True,
        )

        for i, r in enumerate(results, start=1):
            label = "Task A" if i == 1 else "Task B"
            if isinstance(r, list):
                print(f"   {label}: SUCCESS — new positions {r}")
            elif isinstance(r, OptimisticConcurrencyError):
                print(f"   {label}: OptimisticConcurrencyError — expected {r.expected}, actual {r.actual}, stream={r.stream_id}")
            else:
                print(f"   {label}: UNEXPECTED {r!r}")

        print("\n3) Retry pattern for the loser (reload version, append again) …")
        ver = await store.stream_version(stream_id)
        pos = await store.append(stream_id, _ev("RetryAfterReload"), expected_version=ver)
        print(f"   After reload, append with expected_version={ver} → positions {pos}")
        final = await store.load_stream(stream_id)
        print(f"\n4) Final stream: {len(final)} events (Init + one race winner + retry) = {len(final)}")
        for e in final:
            print(f"   pos {e.stream_position}: {e.event_type}")
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
