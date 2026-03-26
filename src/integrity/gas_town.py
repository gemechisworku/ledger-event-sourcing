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


_VERBATIM_TYPES = frozenset(
    {
        "AgentSessionFailed",
        "AgentSessionPending",
        "AgentInputValidationFailed",
        "AgentExecutionError",
    }
)


def _is_pending_or_error(ev) -> bool:
    et = ev.event_type
    if et in _VERBATIM_TYPES:
        return True
    pl = ev.payload or {}
    st = str(pl.get("status") or "").upper()
    if st in ("PENDING", "ERROR", "FAILED"):
        return True
    if pl.get("pending_reconciliation") is True:
        return True
    return False


def _decision_without_completion(stream: list) -> bool:
    """True if the stream ends in a decision-like step without AgentSessionCompleted."""
    if not stream:
        return False
    last = stream[-1]
    if last.event_type == "AgentSessionFailed":
        return True
    if last.event_type == "AgentNodeExecuted":
        nn = str((last.payload or {}).get("node_name") or "").lower()
        if "decision" in nn:
            return not any(e.event_type == "AgentSessionCompleted" for e in stream)
    return False


async def reconstruct_agent_context(
    store,
    agent_type: str,
    session_id: str,
    token_budget: int = 8000,
) -> AgentContext:
    """
    Load agent session stream cold and build token-efficient context.
    Preserves verbatim: last 3 events plus any PENDING/ERROR-class events.
    Older events are collapsed into a short summary line each.
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

    verbatim_indices: set[int] = set()
    for i, e in enumerate(stream):
        if _is_pending_or_error(e):
            verbatim_indices.add(i)
    for i in range(max(0, len(stream) - 3), len(stream)):
        verbatim_indices.add(i)

    summary_lines: list[str] = []
    verbatim_blocks: list[str] = []
    for i, e in enumerate(stream):
        tag = f"{e.event_type}@{e.stream_position}"
        if i in verbatim_indices:
            verbatim_blocks.append(f"{tag} {e.payload!r}"[:500])
        else:
            summary_lines.append(tag)

    summary = " | ".join(summary_lines) if summary_lines else "(tail-only)"
    verbatim_text = " || ".join(verbatim_blocks)
    text = f"SUMMARY: {summary}\nVERBATIM: {verbatim_text}"[: max(100, token_budget)]

    pending: list[str] = []
    for e in reversed(stream):
        if e.event_type == "AgentSessionFailed":
            pending.append(f"recover_from_failure:{(e.payload or {}).get('error_type')}")
            break
        if e.event_type == "AgentSessionCompleted":
            break

    last_pos = stream[-1].stream_position
    if stream[-1].event_type == "AgentSessionCompleted":
        health = "COMPLETED"
    elif stream[-1].event_type == "AgentSessionFailed":
        health = "NEEDS_RECONCILIATION"
    elif _decision_without_completion(stream):
        health = "NEEDS_RECONCILIATION"
    else:
        health = "IN_PROGRESS"

    tail = stream[-3:]
    verbatim_tail = [f"{e.event_type}:{e.stream_position}" for e in tail]

    return AgentContext(
        context_text=text,
        last_event_position=last_pos,
        pending_work=pending,
        session_health_status=health,
        verbatim_tail=verbatim_tail,
    )
