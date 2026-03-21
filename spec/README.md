# Specification index — The Ledger

Modular **design specs** derived from [`../ref_docs/requirements.md`](../ref_docs/requirements.md). Use that file as the **normative** long-form spec; this tree breaks it into implementable slices (**features → code → tests**).

**Execution order:** [`implementation_plan.md`](implementation_plan.md)

## Layout

| Path | Purpose |
|------|---------|
| [`00-index/`](00-index/) | Traceability matrix, requirements → spec map |
| [`01-context/`](01-context/) | Vision, glossary, NFRs, SLOs |
| [`02-phase0-reconnaissance/`](02-phase0-reconnaissance/) | `DOMAIN_NOTES` questions |
| [`03-event-store/`](03-event-store/) | DDL, `EventStore` API, OCC, outbox, double-decision test |
| [`04-domain-model/`](04-domain-model/) | Aggregates, event catalogue, rules, commands, reconstruction |
| [`05-projections-cqrs/`](05-projections-cqrs/) | Daemon, three projections, lag SLOs |
| [`06-upcasting-integrity-memory/`](06-upcasting-integrity-memory/) | Registry, audit chain, Gas Town |
| [`07-mcp-layer/`](07-mcp-layer/) | Tools, resources, LLM errors |
| [`08-bonus-phase6/`](08-bonus-phase6/) | What-if, regulatory package |
| [`09-documentation/`](09-documentation/) | Test strategy, `DESIGN.md` outline |
| [`mappings/`](mappings/) | `src/` → `ledger/` layout |

## Repo layout

See [`mappings/repo-layout-mapping.md`](mappings/repo-layout-mapping.md).

## Workflow

1. Align **`01-context`** + **`02-phase0-reconnaissance`** before deep coding.
2. Implement phase-by-phase; update **`00-index/traceability-matrix.md`** when paths change.
3. Keep **`09-documentation/test-strategy.md`** in sync with real test files.
