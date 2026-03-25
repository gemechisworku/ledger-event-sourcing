"""In-memory job registry for pipeline runs (MVP — single process)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class JobState:
    queue: asyncio.Queue[Any | None]
    done: bool = False
    error: str | None = None


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}

    def create(self) -> str:
        jid = str(uuid4())
        self._jobs[jid] = JobState(queue=asyncio.Queue())
        return jid

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def forget(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
