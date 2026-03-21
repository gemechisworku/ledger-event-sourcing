# Command handlers

Reference pattern:

1. `load` aggregates from `EventStore`
2. `validate` invariants
3. Build new events (pure)
4. `append` with correct `expected_version` and correlation/causation IDs

List concrete handlers: submit application, credit analysis completed, fraud screening, compliance, decision, human review, start agent session, etc.

**Registry:** `ledger/registry/client.py` — document applicant/profile lookups.
