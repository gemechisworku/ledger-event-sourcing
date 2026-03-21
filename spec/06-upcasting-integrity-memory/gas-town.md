# Gas Town — agent memory

- **`reconstruct_agent_context(store, agent_id, session_id, token_budget)`** → summary + last positions + pending work + health.
- **Crash test:** append N events without in-memory agent; reconstruct and assert continuation is possible.
- Align with **AgentSession** events in `ledger/schema/events.py`.
