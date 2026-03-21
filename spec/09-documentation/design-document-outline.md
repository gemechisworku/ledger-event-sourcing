# DESIGN.md — suggested sections

1. Aggregate boundary justification (e.g. ComplianceRecord vs LoanApplication).
2. Projection strategy: inline vs async; SLO; ComplianceAuditView snapshot strategy.
3. Concurrency analysis: peak load, expected OCC rate, retry budget.
4. Upcasting inference: error rates, null vs inference.
5. EventStoreDB (or equivalent) mapping for Postgres design.
6. **What you would do differently** — main retrospective point.
