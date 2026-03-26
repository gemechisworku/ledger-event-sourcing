"""AgentSession aggregate — stream `agent-{agent_type}-{session_id}`.

Uses per-event dispatch: _apply delegates to _on_{EventType} methods.
"""

from __future__ import annotations

from typing import Any

from src.domain.errors import DomainError
from src.domain.streams import agent_stream_id
from src.models.events import StoredEvent


class AgentSessionAggregate:
    """
    Gas Town: `AgentSessionStarted` must be the first event on the stream.
    Model version on subsequent decision outputs must match session model_version.
    """

    def __init__(self, agent_type: str, session_id: str) -> None:
        self.agent_type = agent_type
        self.session_id = session_id
        self.version: int = -1
        self.model_version: str | None = None
        self.application_id: str | None = None
        self._started: bool = False

    @property
    def stream_id(self) -> str:
        return agent_stream_id(self.agent_type, self.session_id)

    @classmethod
    async def load(cls, store: Any, agent_type: str, session_id: str) -> AgentSessionAggregate:
        agg = cls(agent_type=agent_type, session_id=session_id)
        events = await store.load_stream(agg.stream_id)
        for ev in events:
            agg._apply(ev)
        agg.version = await store.stream_version(agg.stream_id)
        return agg

    def _apply(self, event: StoredEvent) -> None:
        if not self._started and event.event_type != "AgentSessionStarted":
            raise DomainError(
                "Gas Town: first event on AgentSession stream must be AgentSessionStarted, "
                f"got {event.event_type}"
            )
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event)
        self.version = event.stream_position

    def _on_AgentSessionStarted(self, event: StoredEvent) -> None:
        self._started = True
        self.model_version = event.payload.get("model_version")
        self.application_id = event.payload.get("application_id")

    def _on_AgentNodeExecuted(self, event: StoredEvent) -> None:
        pass

    def _on_AgentSessionCompleted(self, event: StoredEvent) -> None:
        pass

    # ── Guards ──

    def assert_not_already_started(self) -> None:
        if self._started:
            raise DomainError("Agent session already started")

    def assert_context_loaded(self) -> None:
        if not self._started:
            raise DomainError("Agent session has no AgentSessionStarted (context not loaded)")

    def assert_model_version_current(self, model_version: str) -> None:
        self.assert_context_loaded()
        if self.model_version and model_version != self.model_version:
            raise DomainError(
                f"Model version mismatch: session={self.model_version!r}, command={model_version!r}"
            )
