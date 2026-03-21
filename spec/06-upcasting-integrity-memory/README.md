# Upcasting, integrity, Gas Town (Phase 4)

| Doc | Purpose |
|-----|---------|
| `upcasting.md` | `UpcasterRegistry`, register decorators, version chains; events to upcast |
| `audit-chain.md` | `run_integrity_check`, SHA-256 chain, `AuditIntegrityCheckRun` |
| `gas-town.md` | `reconstruct_agent_context`, token budget, `NEEDS_RECONCILIATION` |

**Code:** `ledger/upcasters.py` (+ split `ledger/upcasting/` if you refactor); new `ledger/integrity/` optional.
