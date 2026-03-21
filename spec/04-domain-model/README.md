# Domain model (Phase 2+)

| Doc | Purpose |
|-----|---------|
| `aggregates.md` | LoanApplication, AgentSession, ComplianceRecord, AuditLedger — streams, invariants |
| `streams-and-events.md` | Stream formats; catalogue vs `ledger/schema/events.py` |
| `state-machines.md` | Loan application valid transitions |
| `business-rules.md` | Six rules + where enforced (aggregate vs handler) |
| `command-handlers.md` | Command types; load → validate → emit → append |

**Code:** `ledger/domain/aggregates/`, `ledger/agents/base_agent.py`, `ledger/registry/client.py`.
