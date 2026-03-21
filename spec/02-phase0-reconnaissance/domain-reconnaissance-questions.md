# DOMAIN_NOTES — six questions

Answer in **`DOMAIN_NOTES.md`** with concrete examples. Use this as a checklist.

1. **EDA vs ES** — Tracing/callbacks vs Ledger; what changes in architecture; what you gain.
2. **Aggregate boundary** — Four aggregates; one alternative boundary you rejected; coupling failure mode.
3. **Concurrency** — Two writers `append` with same `expected_version`; sequence; what the loser receives; next step.
4. **Projection lag** — Stale read right after a write; UX/system behaviour.
5. **Upcasting** — Example event evolving across schema versions; sample upcaster; inference vs null for missing fields.
6. **Distributed projections** — Multiple workers processing projections; coordination; failure modes.
