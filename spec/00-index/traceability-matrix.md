# Traceability matrix

**Requirements source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

| Phase | Scope | Primary code | Tests |
|-------|--------|--------------|--------|
| 0 | Schema, generator, validation | `src/schema/events.py`, `datagen/*` | `tests/test_schema_and_generator.py` |
| 1 | Postgres DDL, `EventStore`, OCC, outbox | `src/event_store.py`, migrations | `tests/test_event_store.py`, concurrency |
| 1 | Registry lookups | `src/registry/client.py` | same |
| 2 | Aggregates, command handlers, rules | `src/domain/aggregates/*`, handlers | `tests/test_domain.py` |
| 3 | Agents, narratives | `src/agents/*` | `tests/test_narratives.py` |
| 4 | Daemon, 3 projections, upcasters, integrity, Gas Town | `src/projections/`, `src/upcasters.py`, `src/integrity/` | `tests/test_projections.py`, dedicated tests |
| 5 | MCP tools + resources | `src/mcp_server.py` | `tests/test_mcp.py`, lifecycle |
| 6 | What-if, regulatory package | `src/what_if/`, `src/regulatory/` | optional suites |

## Requirements → spec map

| Requirements section | Spec folder |
|---------------------|-------------|
| Phase 0 concepts | `01-context/`, `02-phase0-reconnaissance/` |
| Phase 1 schema + EventStore | `03-event-store/` |
| Phase 2 domain | `04-domain-model/` |
| Phase 3 projections | `05-projections-cqrs/` |
| Phase 4 upcast + integrity + Gas Town | `06-upcasting-integrity-memory/` |
| Phase 5 MCP | `07-mcp-layer/` |
| Phase 6 optional | `08-bonus-phase6/` |

## External layout

Generic `src/…` trees → see [`../mappings/repo-layout-mapping.md`](../mappings/repo-layout-mapping.md).
