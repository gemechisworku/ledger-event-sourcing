# DOMAIN_NOTES — The Ledger

Answers below align implementation with [`ref_docs/requirements.md`](ref_docs/requirements.md) and [`spec/`](spec/README.md).

---

## 1. EDA vs ES — callbacks / traces vs the Ledger

**Classification:** LangChain-style **callbacks and traces** are **event-driven architecture (EDA)**: they observe execution and may emit telemetry, but they are **not** the system’s source of truth. Events can be dropped, truncated, or never correlated with business outcomes.

**If we redesigned with the Ledger:**

- Every **business fact** (application submitted, analysis completed, compliance verdict, decision) would be an **append-only event** in PostgreSQL with a stable `stream_id`, `stream_position`, and `global_position`.
- Agent “traces” would either **reference** event IDs or be stored as **secondary** streams, not as a substitute for loan/compliance history.
- **Gain:** reproducible audit trail, optimistic concurrency on shared streams, projections built from the same history regulators see, and no silent loss of decisions when a process restarts.

---

## 2. Aggregate boundary — alternative rejected

**Alternative considered:** One **mega-aggregate** “LoanCase” folding LoanApplication + ComplianceRecord + all AgentSessions into a single stream.

**Rejected because:** Compliance and credit/fraud work **proceeds at different cadences** and **different writers** (compliance rules vs agent sessions). A single stream would force **artificial sequencing** and inflate **optimistic concurrency collisions** on unrelated concerns (e.g. two compliance rule writes conflicting with an unrelated agent append).

**Chosen boundaries (four aggregates):** `loan-{id}`, `agent-{agent}-{session}`, `compliance-{id}`, `audit-{type}-{id}`.

**Coupling prevented:** Compliance evolution and agent tooling can change **without** rewriting loan lifecycle ordering; concurrent updates hit **different streams** where possible, and cross-stream rules are enforced by **reading** related streams or projections in command handlers, not by merging streams.

---

## 3. Concurrency — two appends with `expected_version=3`

**Sequence (same stream, both think version is 3):**

1. Task A begins transaction T₁: reads `current_version == 3`, prepares append of event at position 4.
2. Task B begins T₂: reads `current_version == 3`, prepares append of event at position 4.
3. T₁ **commits first**: inserts row `stream_position=4`, bumps `event_streams.current_version` to **4**, commits outbox in same transaction.
4. T₂ **validates** `expected_version=3` against **current** `current_version` → sees **4** → **does not** insert (or rolls back).

**Loser receives:** `OptimisticConcurrencyError` (or equivalent) with `expected_version=3`, `actual_version=4`, `stream_id`.

**Loser must:** `load_stream` (or reload aggregate), recompute decision against new state at version 4, then `append(..., expected_version=4)` if the operation is still valid.

---

## 4. Projection lag (~200ms) — stale “available credit”

**System behaviour:** The write path appends to the event store **immediately**; the **ApplicationSummary** (or credit-limit projection) updates **asynchronously** within the SLO (e.g. &lt;500ms). The read is **eventually consistent**.

**UI / product:**

- Show **last_updated** or **projection_lag_ms** on dashboard tiles (from daemon health).
- For high-stakes reads, optionally **poll** until lag &lt; threshold or **read-your-writes** via returning **computed values from the command response** when the use case requires (documented exception), or block on **inline projection** for that command only (tradeoff: latency).
- Copy: “Figures may take a moment to reflect the latest decision” with link to **event timeline** (source of truth) if dispute.

---

## 5. Upcasting — `CreditDecisionMade` v1 → v2

**v1 payload:** `{ application_id, decision, reason }`  
**v2 adds:** `model_version`, `confidence_score`, `regulatory_basis`

**Sketch (chain from v1):**

```python
@registry.register("CreditDecisionMade", from_version=1)
def upcast_credit_decision_v1_to_v2(payload: dict) -> dict:
    return {
        **payload,
        "model_version": None,  # unknown for legacy — see below
        "confidence_score": None,
        "regulatory_basis": infer_regulatory_basis(payload.get("reason"), recorded_at_context),
    }
```

**Inference strategy for `model_version` on historical events:**

- Prefer **null** (or `"legacy-unknown"`) when no reliable signal exists — **do not fabricate** a version string that could mislead regulators.
- If policy allows: derive a **bucket** from `recorded_at` (e.g. “pre-2026-pool”) only when documented in `DESIGN.md`, with stated error rate.
- **`confidence_score`:** null in v1 — **null in v2** unless we have a side table or external audit log; fabrication is worse than null for compliance.

---

## 6. Distributed projections — Python parallel to Marten’s daemon

**Goal:** Multiple workers process **disjoint slices** of the global event stream without double-applying or skipping.

**Approach:**

- **Single-leader election** via **PostgreSQL advisory lock** or a **`projection_leases`** row (lease owner, expiry). Only the leader runs the daemon **or** workers claim **partition keys** (e.g. `hash(stream_id) % N`).
- **Alternative:** One writer daemon + horizontal **read replicas** for queries only (simpler).

**Coordination primitive:** `SELECT pg_try_advisory_lock(hashtext('ledger-projections'))` with TTL/heartbeat, or **SKIP LOCKED** job queue for per-batch work.

**Failure mode prevented:** **Split brain** — two nodes advancing the same `projection_checkpoints` differently. Locks + monotonic `global_position` checkpoints ensure **at-most-one** writer per projection batch or **partition-scoped** idempotency.

---

## Phase 0 verification

- `uv run pytest tests/test_schema_and_generator.py -v` — **10 passed** (run after env sync).
