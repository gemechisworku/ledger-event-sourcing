"""Projection daemon — global catch-up with per-projection checkpoints."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.projections.base import Projection
from src.schema.events import StoredEvent

if TYPE_CHECKING:
    from src.event_store import EventStore

logger = logging.getLogger(__name__)

DEFAULT_BATCH = 200
MAX_SKIP_FAILURES = 3


class ProjectionDaemon:
    def __init__(self, store: EventStore, projections: list[Projection]) -> None:
        self._store = store
        self._projections = list(projections)
        self._running = False
        self._fail_counts: dict[tuple[str, int], int] = {}

    @property
    def projections(self) -> list[Projection]:
        return self._projections

    async def run_forever(self, poll_interval_ms: int = 100, batch_size: int = DEFAULT_BATCH) -> None:
        self._running = True
        while self._running:
            await self.process_batch(batch_size=batch_size)
            await asyncio.sleep(poll_interval_ms / 1000.0)

    def stop(self) -> None:
        self._running = False

    async def process_batch(self, batch_size: int = DEFAULT_BATCH) -> int:
        """Returns number of events processed."""
        if not self._projections:
            return 0
        checkpoints = [await self._store.load_checkpoint(p.name) for p in self._projections]
        start = min(checkpoints)
        processed = 0
        async for ev in self._store.load_all(from_position=start, batch_size=batch_size):
            processed += 1
            for proj in self._projections:
                ck = await self._store.load_checkpoint(proj.name)
                if ck >= ev.global_position:
                    continue
                if not proj.handles(ev):
                    await self._store.save_checkpoint(proj.name, int(ev.global_position))
                    continue
                key = (proj.name, int(ev.global_position))
                try:
                    await proj.apply(ev)
                    await self._store.save_checkpoint(proj.name, int(ev.global_position))
                    self._fail_counts.pop(key, None)
                except Exception as exc:
                    n = self._fail_counts.get(key, 0) + 1
                    self._fail_counts[key] = n
                    logger.exception("projection %s failed on g=%s (attempt %s)", proj.name, ev.global_position, n)
                    if n >= MAX_SKIP_FAILURES:
                        logger.warning("skipping event g=%s for projection %s after %s failures", ev.global_position, proj.name, n)
                        await self._store.save_checkpoint(proj.name, int(ev.global_position))
                        self._fail_counts.pop(key, None)
        return processed

    async def get_all_lags(self) -> dict[str, int]:
        out: dict[str, int] = {}
        tail = await self._store.max_global_position()
        for p in self._projections:
            cp = await self._store.load_checkpoint(p.name)
            eff = max(cp, 0)
            out[p.name] = max(0, tail - eff)
        return out

    async def get_lag(self, projection_name: str) -> int:
        for p in self._projections:
            if p.name == projection_name:
                tail = await self._store.max_global_position()
                cp = await self._store.load_checkpoint(p.name)
                eff = max(cp, 0)
                return max(0, tail - eff)
        raise KeyError(projection_name)
