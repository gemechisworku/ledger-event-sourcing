"""Projection daemon — global catch-up with per-projection checkpoints."""
from __future__ import annotations

import asyncio
import logging
import time
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
        self._ms_per_event_ewma: dict[str, float] = {}

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
        t0 = time.perf_counter()
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
                t_apply = time.perf_counter()
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
                dt_ms = (time.perf_counter() - t_apply) * 1000
                prev = self._ms_per_event_ewma.get(proj.name, dt_ms)
                self._ms_per_event_ewma[proj.name] = 0.85 * prev + 0.15 * dt_ms
        if processed > 0:
            batch_ms = (time.perf_counter() - t0) * 1000
            per = batch_ms / processed
            for p in self._projections:
                self._ms_per_event_ewma[p.name] = 0.8 * self._ms_per_event_ewma.get(p.name, per) + 0.2 * per
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

    async def get_lag_ms(self, projection_name: str) -> int:
        """Approximate lag in milliseconds: event backlog × EWMA ms/event per projection."""
        lag_ev = await self.get_lag(projection_name)
        m = self._ms_per_event_ewma.get(projection_name, 5.0)
        return int(lag_ev * m)

    async def get_all_lags_ms(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self._projections:
            out[p.name] = await self.get_lag_ms(p.name)
        return out
