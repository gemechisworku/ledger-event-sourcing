# Domain model

| Doc | Purpose |
|-----|---------|
| [`aggregates.md`](aggregates.md) | Four aggregates, full event catalogue table, invariants |
| [`streams-and-events.md`](streams-and-events.md) | Stream IDs, metadata, multi-stream workflows |
| [`state-machines.md`](state-machines.md) | Loan application states |
| [`business-rules.md`](business-rules.md) | Six domain rules (verbatim requirements) |
| [`command-handlers.md`](command-handlers.md) | Handler pattern + example + command list |
| [`aggregate-reconstruction.md`](aggregate-reconstruction.md) | `load` / `_apply` / `_on_*` pattern |

**Code:** `src/domain/aggregates/`, `src/agents/base_agent.py`, `src/registry/client.py`.
