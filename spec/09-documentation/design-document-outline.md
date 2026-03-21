# DESIGN.md — recommended sections

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

1. **Aggregate boundary justification** — Why `ComplianceRecord` is separate from `LoanApplication`. What breaks if merged? Cite a **concurrent write** failure mode.

2. **Projection strategy** — Per projection: inline vs async; **SLO**. For ComplianceAuditView: **snapshot strategy** (event-count, time, manual), invalidation rules.

3. **Concurrency analysis** — e.g. 100 concurrent applications × 4 agents: expected **`OptimisticConcurrencyError` rate**, **retry policy**, **max retries** before surfacing failure.

4. **Upcasting inference** — Per inferred field: likely error rate, downstream impact, when **`null` beats guessing**.

5. **EventStoreDB mapping** — Streams → stream IDs; `load_all` → $all subscription; daemon → persistent subscriptions; what EventStoreDB gives you **for free** vs your Postgres build.

6. **Retrospective** — Single biggest architectural decision you’d revisit with more time.
