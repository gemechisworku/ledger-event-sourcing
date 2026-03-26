"""Gas Town — reconstruct agent session context from the ledger."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.streams import agent_stream_id


@dataclass
class AgentContext:
    context_text: str
    last_event_position: int
    pending_work: list[str]
    session_health_status: str
    verbatim_tail: list[str] = field(default_factory=list)


async def reconstruct_agent_context(
    store,
    agent_type: str,
    session_id: str,
    token_budget: int = 8000,
) -> AgentContext:
    """
    Load agent session stream `agent-{agent_type}-{session_id}` and build a compact
    narrative for crash recovery.
    """
    sid = agent_stream_id(agent_type, session_id)
    stream = await store.load_stream(sid)
    if not stream:
        return AgentContext(
            context_text="(empty session)",
            last_event_position=-1,
            pending_work=[],
            session_health_status="EMPTY",
            verbatim_tail=[],
        )

    tail = stream[-3:]
    verbatim = [f"{e.event_type}:{e.stream_position}" for e in tail]

    pending: list[str] = []
    for e in reversed(stream):
        if e.event_type == "AgentSessionFailed":
            pending.append(f"recover_from_failure:{e.payload.get('error_type')}")
            break
        if e.event_type == "AgentSessionCompleted":
            break

    last_pos = stream[-1].stream_position
    health = "COMPLETED" if stream[-1].event_type == "AgentSessionCompleted" else "IN_PROGRESS"
    if stream[-1].event_type == "AgentSessionFailed":
        health = "NEEDS_RECONCILIATION"

    summary_parts = [f"events={len(stream)}", f"last={stream[-1].event_type}"]
    text = " | ".join(summary_parts)[: max(100, token_budget)]

    return AgentContext(
        context_text=text,
        last_event_position=last_pos,
        pending_work=pending,
        session_health_status=health,
        verbatim_tail=verbatim,
    )
