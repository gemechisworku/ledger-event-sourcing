# Specification index — The Ledger

Modular **design specs** for the Ledger. Authoritative requirements are summarized in [`../ref_docs/requirements.md`](../ref_docs/requirements.md); this tree traces **features → code → tests**.

**Execution order:** [`implementation_plan.md`](implementation_plan.md)

## Layout

| Path | Purpose |
|------|---------|
| [`00-index/`](00-index/) | Traceability: phases, repo paths, tests |
| [`01-context/`](01-context/) | Scenario, terminology, non-functional constraints |
| [`02-phase0-reconnaissance/`](02-phase0-reconnaissance/) | Domain reconnaissance + `DOMAIN_NOTES.md` |
| [`03-event-store/`](03-event-store/) | Postgres schema, `EventStore`, OCC, outbox |
| [`04-domain-model/`](04-domain-model/) | Aggregates, streams, state machines, business rules, commands |
| [`05-projections-cqrs/`](05-projections-cqrs/) | Daemon, three projections, temporal compliance, SLOs |
| [`06-upcasting-integrity-memory/`](06-upcasting-integrity-memory/) | Upcasters, hash chain, Gas Town recovery |
| [`07-mcp-layer/`](07-mcp-layer/) | MCP tools/resources, structured errors, LLM preconditions |
| [`08-bonus-phase6/`](08-bonus-phase6/) | Optional: what-if projector, regulatory package |
| [`09-documentation/`](09-documentation/) | Test strategy, architecture doc outline, documentation checklist |
| [`mappings/`](mappings/) | External `src/` layout → this repo |

## Repo layout

Some references use a generic `src/…` tree. **This codebase uses `ledger/…` and `datagen/…`.** See [`mappings/repo-layout-mapping.md`](mappings/repo-layout-mapping.md).

## Workflow

1. Align **`01-context`** and **`02-phase0-reconnaissance`** before deep implementation.
2. For each phase, update the matching **`03`–`07`** docs and **`00-index/traceability-matrix.md`**.
3. Keep **`mappings/phase-to-tests.md`** in sync when tests are added or renamed.
