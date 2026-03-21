"""AgentSession aggregate — stream `agent-{agent_type}-{session_id}`."""

from __future__ import annotations

from typing import Any

from ledger.domain.errors import DomainError
from ledger.domain.streams import agent_stream_id


class AgentSessionAggregate:
    """
    Gas Town: `AgentSessionStarted` must be stream_position == 1 (first event).
    Model version on subsequent decision outputs must match session model_version.
    """

    def __init__(self, agent_type: str, session_id: str) -> None:
        self.agent_type = agent_type
        self.session_id = session_id
        self.version: int = 0
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

    def _apply(self, event: dict) -> None:
        et = event["event_type"]
        p = event.get("payload", {})

        # Gas Town: InMemoryEventStore uses stream_position 0 for first event; Postgres uses 1.
        if not self._started and et != "AgentSessionStarted":
            raise DomainError(
                "Gas Town: first event on AgentSession stream must be AgentSessionStarted, "
                f"got {et}"
            )

        if et == "AgentSessionStarted":
            self._started = True
            self.model_version = p.get("model_version")
            self.application_id = p.get("application_id")
        self.version = int(event["stream_position"])

    def assert_context_loaded(self) -> None:
        if not self._started:
            raise DomainError("Agent session has no AgentSessionStarted (context not loaded)")

    def assert_model_version_current(self, model_version: str) -> None:
        self.assert_context_loaded()
        if self.model_version and model_version != self.model_version:
            raise DomainError(
                f"Model version mismatch: session={self.model_version!r}, command={model_version!r}"
            )
