# Test strategy

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) component inventory.

## By area

| Area | What to cover |
|------|----------------|
| Schema + generator | Event types validate; generator produces coherent data |
| Event store | Append, load, OCC, outbox in one transaction |
| **Double-decision** | Two concurrent appends, one wins, one `OptimisticConcurrencyError` |
| Domain | State machine + six business rules |
| Projections | Lag under load (~50 concurrent handlers); `rebuild_from_scratch` |
| Upcasting | **Immutability**: DB payload unchanged after read-time upcast |
| Integrity | Hash chain detects tampering |
| Gas Town | Reconstruct context after 5 events without in-memory agent |
| MCP | Full lifecycle **via tools only**; resources hit projections |

## Pytest targets (repo)

| File | Phase |
|------|-------|
| `tests/test_schema_and_generator.py` | 0 |
| `tests/test_event_store.py` | 1 |
| `tests/test_domain.py` | 2 |
| `tests/test_narratives.py` | 3 |
| `tests/test_projections.py` | 4 |
| `tests/test_mcp.py` | 5 |

Add `test_concurrency`, `test_upcasting`, `test_gas_town`, `test_mcp_lifecycle` as you split modules.
