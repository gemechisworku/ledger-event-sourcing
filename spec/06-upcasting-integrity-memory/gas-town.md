# Gas Town — agent memory recovery

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 4C.

## `reconstruct_agent_context`

```python
async def reconstruct_agent_context(
    store: EventStore,
    agent_id: str,
    session_id: str,
    token_budget: int = 8000,
) -> AgentContext:
    """
    1. Load full AgentSession stream: agent-{agent_id}-{session_id}
    2. Identify last completed action, pending work, current application state
    3. Summarise older events into prose (token-efficient)
    4. Verbatim: last 3 events; any PENDING or ERROR state events
    5. Return AgentContext:
       - context_text
       - last_event_position
       - pending_work[]
       - session_health_status

    If last event implies partial decision without completion → NEEDS_RECONCILIATION
    """
```

## Test scenario

1. Start session; append **5** events **without** in-memory agent object.
2. Call `reconstruct_agent_context`.
3. Assert returned context is sufficient to resume work (positions, pending items, health).
