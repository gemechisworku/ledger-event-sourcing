# Implementation plan — The Ledger

**Authority:** [`../ref_docs/requirements.md`](../ref_docs/requirements.md) and this [`spec/`](README.md) tree.

## How to use & update this file

1. **While implementing:** Check off `[ ]` → `[x]` when a step is **done** (merged to your main branch or agreed checkpoint).
2. **After each phase or milestone:** Add a line under **[Progress log](#progress-log)** with date + what moved.
3. **When files/tests are renamed:** Update [`00-index/traceability-matrix.md`](00-index/traceability-matrix.md) and the **Verification** column here.
4. **Optional:** Set **Owner** or **Target** dates in your team’s tracker; this doc stays the single checklist.

**Status legend:** `[ ]` not started · `[~]` in progress (optional) · `[x]` done

---

## Principles

1. **Tests gate depth** — don’t build large Phase *N+1* on failing Phase *N* tests.
2. **`DOMAIN_NOTES.md`** — align early ([`02-phase0-reconnaissance/domain-reconnaissance-questions.md`](02-phase0-reconnaissance/domain-reconnaissance-questions.md)).
3. **`DESIGN.md`** — update as you lock decisions ([`09-documentation/design-document-outline.md`](09-documentation/design-document-outline.md)).
4. **Traceability** — keep [`00-index/traceability-matrix.md`](00-index/traceability-matrix.md) in sync with real paths.

---

## Phase 0 — Reconnaissance & baseline

| # | Task | Spec / detail | Verification | Done |
|---|------|---------------|--------------|------|
| 0.1 | Tooling & env | `uv sync`, Postgres, `.env` from `.env.example` | `uv sync` OK; Postgres needed from Phase 1 onward | [x] |
| 0.2 | Schema & generator tests | [`04-domain-model/aggregates.md`](04-domain-model/aggregates.md) vs `ledger/schema/events.py` | `uv run pytest tests/test_schema_and_generator.py -v` | [x] |
| 0.3 | Domain notes doc | [`02-phase0-reconnaissance/`](02-phase0-reconnaissance/) | `DOMAIN_NOTES.md` at repo root answers six questions | [x] |

---

## Phase 1 — Event store core

| # | Task | Spec / detail | Verification | Done |
|---|------|---------------|--------------|------|
| 1.1 | SQL migrations | [`ledger/schema.sql`](../ledger/schema.sql), [`03-event-store/schema-contract.md`](03-event-store/schema-contract.md) | Applied on `EventStore.connect()` | [x] |
| 1.2 | `EventStore.append` | [`03-event-store/requirements.md`](03-event-store/requirements.md), [`concurrency-and-outbox.md`](03-event-store/concurrency-and-outbox.md) | OCC + same-tx outbox inserts | [x] |
| 1.3 | `load_stream` / `load_all` | Upcasting hook point (stub OK until Phase 4) | Streams replay in order; `load_all` batches | [x] |
| 1.4 | `stream_version`, `archive_stream`, `get_stream_metadata` | [`03-event-store/requirements.md`](03-event-store/requirements.md) | Implemented; checkpoints `save`/`load` for projections | [x] |
| 1.5 | `ApplicantRegistryClient` | [`04-domain-model/command-handlers.md`](04-domain-model/command-handlers.md) | `ledger/registry/client.py` matches tests | [x] |
| 1.6 | Concurrency test | [`03-event-store/double-decision-test.md`](03-event-store/double-decision-test.md) | Double-append test passes | [x] |
| 1.7 | Gate | — | `uv run pytest tests/test_event_store.py tests/test_applicant_registry_client.py -v` (+ `tests/phase1/` if used) | [x] |

**Primary code:** `ledger/event_store.py`, migrations under `ledger/` or `schema/`.

---

## Phase 2 — Domain logic

| # | Task | Spec / detail | Verification | Done |
|---|------|---------------|--------------|------|
| 2.1 | `LoanApplication` aggregate | [`04-domain-model/aggregate-reconstruction.md`](04-domain-model/aggregate-reconstruction.md), [`state-machines.md`](04-domain-model/state-machines.md), [`business-rules.md`](04-domain-model/business-rules.md) | State + rules enforced in domain | [ ] |
| 2.2 | `AgentSession` aggregate | [`business-rules.md`](04-domain-model/business-rules.md) rule 2 (Gas Town), rule 3 | Context-before-decision | [ ] |
| 2.3 | `ComplianceRecord` / `AuditLedger` | [`04-domain-model/aggregates.md`](04-domain-model/aggregates.md) | Streams `compliance-`, `audit-` | [ ] |
| 2.4 | Command handlers | [`04-domain-model/command-handlers.md`](04-domain-model/command-handlers.md) | load → validate → emit → append | [ ] |
| 2.5 | Gate | — | `uv run pytest tests/test_domain.py -v` | [ ] |

---

## Phase 3 — Agents & narratives

| # | Task | Spec / detail | Verification | Done |
|---|------|---------------|--------------|------|
| 3.1 | Agents on `base_agent.py` | [`04-domain-model/README.md`](04-domain-model/README.md), README roadmap | Fraud, compliance, orchestrator, doc processing per roadmap | [ ] |
| 3.2 | Gate | — | `uv run pytest tests/test_narratives.py -v` | [ ] |

**Primary code:** `ledger/agents/base_agent.py`, `ledger/agents/*`.

---

## Phase 4 — Projections, daemon, upcasting, integrity

| # | Task | Spec / detail | Verification | Done |
|---|------|---------------|--------------|------|
| 4.1 | `ProjectionDaemon` | [`05-projections-cqrs/daemon.md`](05-projections-cqrs/daemon.md), [`slo-and-lag.md`](05-projections-cqrs/slo-and-lag.md) | Checkpoints + fault tolerance + `get_lag` / `get_all_lags` | [ ] |
| 4.2 | ApplicationSummary | [`05-projections-cqrs/projections/application-summary.md`](05-projections-cqrs/projections/application-summary.md) | Table + upsert from events | [ ] |
| 4.3 | AgentPerformanceLedger | [`05-projections-cqrs/projections/agent-performance.md`](05-projections-cqrs/projections/agent-performance.md) | Metrics per agent + model version | [ ] |
| 4.4 | ComplianceAuditView | [`05-projections-cqrs/projections/compliance-audit.md`](05-projections-cqrs/projections/compliance-audit.md) | `get_current`, `get_compliance_at`, `rebuild_from_scratch` | [ ] |
| 4.5 | Upcaster registry | [`06-upcasting-integrity-memory/upcasting.md`](06-upcasting-integrity-memory/upcasting.md) | Load path calls registry; immutability test | [ ] |
| 4.6 | Audit chain | [`06-upcasting-integrity-memory/audit-chain.md`](06-upcasting-integrity-memory/audit-chain.md) | `run_integrity_check` | [ ] |
| 4.7 | Gas Town | [`06-upcasting-integrity-memory/gas-town.md`](06-upcasting-integrity-memory/gas-town.md) | `reconstruct_agent_context` + crash scenario test | [ ] |
| 4.8 | Gate | — | `uv run pytest tests/test_projections.py -v` + any `test_upcasting` / `test_gas_town` | [ ] |

**Primary code:** `ledger/projections/`, `ledger/upcasters.py`, optional `ledger/integrity/`.

---

## Phase 5 — MCP server

| # | Task | Spec / detail | Verification | Done |
|---|------|---------------|--------------|------|
| 5.1 | Eight tools | [`07-mcp-layer/tools-spec.md`](07-mcp-layer/tools-spec.md) | Each tool validates + appends | [ ] |
| 5.2 | Six resources | [`07-mcp-layer/resources-spec.md`](07-mcp-layer/resources-spec.md) | Reads from projections / justified stream loads | [ ] |
| 5.3 | Structured errors | [`07-mcp-layer/errors-for-llms.md`](07-mcp-layer/errors-for-llms.md) | Typed errors + preconditions in descriptions | [ ] |
| 5.4 | Lifecycle integration | [`07-mcp-layer/architecture.md`](07-mcp-layer/architecture.md) | Full flow via MCP only | [ ] |
| 5.5 | Gate | — | `uv run pytest tests/test_mcp.py -v` (+ `test_mcp_lifecycle` if split) | [ ] |

**Primary code:** `ledger/mcp_server.py`.

---

## Phase 6 — Optional extensions

| # | Task | Spec / detail | Verification | Done |
|---|------|---------------|--------------|------|
| 6.1 | What-if projector | [`08-bonus-phase6/what-if.md`](08-bonus-phase6/what-if.md) | No writes to prod store; demo scenario | [ ] |
| 6.2 | Regulatory package | [`08-bonus-phase6/regulatory-package.md`](08-bonus-phase6/regulatory-package.md) | JSON export self-consistent | [ ] |

**Only after Phase 4–5 stable.**

---

## Documentation (ongoing)

| Item | Spec | Done |
|------|------|------|
| `DESIGN.md` (6 sections) | [`09-documentation/design-document-outline.md`](09-documentation/design-document-outline.md) | [ ] |
| `DOMAIN_NOTES.md` | [`02-phase0-reconnaissance/`](02-phase0-reconnaissance/) | [ ] |
| Test strategy vs reality | [`09-documentation/test-strategy.md`](09-documentation/test-strategy.md) | [ ] |
| Traceability matrix | [`00-index/traceability-matrix.md`](00-index/traceability-matrix.md) | [ ] |

---

## Progress log

_Add a row when you complete a phase or merge a significant chunk._

| Date | What changed |
|------|----------------|
| 2026-03-19 | **Phase 0 complete:** `uv sync`; `pytest tests/test_schema_and_generator.py` **10 passed**; added root [`DOMAIN_NOTES.md`](../DOMAIN_NOTES.md) (six questions). Postgres not required for Phase 0 gate. |
| 2026-03-19 | **Phase 1 (EventStore):** `ledger/schema.sql` + PostgreSQL `EventStore` (append OCC, outbox, load_stream, load_all, checkpoints). `tests/test_event_store.py` vs Docker Postgres; integration tests **skip** if DB unreachable. `tests/phase1/test_event_store.py` **11 passed** (InMemory). |
| 2026-03-19 | **Phase 1 complete (1.5):** `ApplicantRegistryClient` implemented in `ledger/registry/client.py`; shared DDL in `ledger/registry/schema.py` (used by `datagen/generate_all.py`). `tests/test_applicant_registry_client.py` **6 passed** vs Postgres. Event store integration tests also accept `APPLICANT_REGISTRY_URL` as DB fallback. |

---

## Parking lot (optional follow-ups)

- [ ] Split `tests/test_concurrency.py` if merged from `test_event_store.py`
- [ ] Advisory locks / multi-worker projection runner (see `DESIGN.md`)
- [ ] Kafka outbox publisher service
