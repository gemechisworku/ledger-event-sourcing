"""Projection protocol — read models updated from global event stream."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.schema.events import StoredEvent


class Projection(ABC):
    """Single read model consumer; checkpointed via projection_checkpoints."""

    name: str

    @abstractmethod
    def handles(self, event: StoredEvent) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def apply(self, event: StoredEvent) -> None:
        raise NotImplementedError

    async def get_lag_positions(self, store) -> int:
        """Tail minus checkpoint (global positions). Checkpoint -1 = nothing processed."""
        tail = await store.max_global_position()
        cp = await store.load_checkpoint(self.name)
        eff = max(cp, 0)
        return max(0, tail - eff)
