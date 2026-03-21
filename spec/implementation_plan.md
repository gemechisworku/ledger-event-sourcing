# Implementation plan — The Ledger

**Status:** Draft — refine as work progresses.  
**Authority:** [`../ref_docs/requirements.md`](../ref_docs/requirements.md) and the `spec/` tree.

---

## Principles

1. **Complete each phase’s tests** before building heavily on the next layer.
2. **`DOMAIN_NOTES.md`** during early domain work — see `02-phase0-reconnaissance/`.
3. **`DESIGN.md` in parallel** — capture tradeoffs as you decide (`09-documentation/design-document-outline.md`).
4. **Update `00-index/traceability-matrix.md`** when paths or tests change.

---

## Phase 0 — Reconnaissance & baseline

| Step | Action | Artifact |
|------|--------|------------|
| 0.1 | Env: `uv sync`, Postgres, `.env` | — |
| 0.2 | Run schema/generator tests | `uv run pytest tests/test_schema_and_generator.py -v` |
| 0.3 | **`DOMAIN_NOTES.md`** (six questions) | `02-phase0-reconnaissance/domain-reconnaissance-questions.md` |

---

## Phase 1 — Event store core

| Step | Action | Artifact |
|------|--------|----------|
| 1.1 | PostgreSQL schema: `events`, `event_streams`, `projection_checkpoints`, `outbox` | `spec/03-event-store/` |
| 1.2 | **`ledger/event_store.py`**: append (OCC + transactional outbox), `load_stream`, `load_all`, etc. | — |
| 1.3 | **`ledger/registry/client.py`** as needed by tests | — |
| 1.4 | Concurrency: double-append behaviour | `uv run pytest tests/test_event_store.py -v` |

---

## Phase 2 — Domain logic

| Step | Action | Artifact |
|------|--------|----------|
| 2.1 | Aggregates: `LoanApplication`, `AgentSession`; extend `ledger/domain/aggregates/` | `04-domain-model/` |
| 2.2 | Command handlers: load → validate → emit → append | `04-domain-model/command-handlers.md` |
| 2.3 | **ComplianceRecord**, **AuditLedger** aggregates | — |
| 2.4 | Tests | `uv run pytest tests/test_domain.py -v` (when present) |

---

## Phase 3 — Agents & narratives

| Step | Action | Artifact |
|------|--------|----------|
| 3.1 | Agents in **`ledger/agents/base_agent.py`** | — |
| 3.2 | Tests | `uv run pytest tests/test_narratives.py -v` |

---

## Phase 4 — Projections, daemon, upcasting

| Step | Action | Artifact |
|------|--------|----------|
| 4.1 | **`ledger/projections/`**: daemon, checkpoints, fault handling, lag | `05-projections-cqrs/` |
| 4.2 | Three projections: ApplicationSummary, AgentPerformanceLedger, ComplianceAuditView | — |
| 4.3 | **`ledger/upcasters.py`**: registry + load path; immutability test | `06-upcasting-integrity-memory/` |
| 4.4 | Integrity + Gas Town: audit chain, `reconstruct_agent_context` | — |
| 4.5 | Tests | `uv run pytest tests/test_projections.py -v` |

---

## Phase 5 — MCP server

| Step | Action | Artifact |
|------|--------|----------|
| 5.1 | **`ledger/mcp_server.py`**: tools, resources, structured errors | `07-mcp-layer/` |
| 5.2 | Full lifecycle via MCP only | — |
| 5.3 | Tests | `uv run pytest tests/test_mcp.py -v` |

---

## Phase 6 — Optional extensions

| Step | Action | Artifact |
|------|--------|----------|
| 6.1 | What-if / counterfactual projector | `08-bonus-phase6/what-if.md` |
| 6.2 | Regulatory examination package | `08-bonus-phase6/regulatory-package.md` |

**After Phases 1–5 are stable.**

---

## Documentation (ongoing)

| Item | When |
|------|------|
| **`DESIGN.md`** | Throughout Phases 1–5 |
| **`DOMAIN_NOTES.md`** | Early |
| **`spec/00-index/traceability-matrix.md`** | When modules move |

---

## Refinement (TODO)

- [ ] Concrete file paths per step once modules exist.
- [ ] Test file names for concurrency, upcasting, MCP lifecycle if split out.
- [ ] Milestones / release tags as needed.
