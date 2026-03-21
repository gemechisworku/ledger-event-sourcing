# What-if projector

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 6.

## `run_what_if`

```python
async def run_what_if(
    store: EventStore,
    application_id: str,
    branch_at_event_type: str,  # e.g. "CreditAnalysisCompleted"
    counterfactual_events: list[BaseEvent],
    projections: list[Projection],
) -> WhatIfResult:
    """
    1. Load application stream events up to branch point
    2. Replace with counterfactual_events at branch
    3. Replay real events causally INDEPENDENT of branch
    4. Skip events DEPENDENT on branched events (via causation_id chain)
    5. Apply merged history to in-memory projections
    6. Return real_outcome, counterfactual_outcome, divergence_events[]

    NEVER persist counterfactuals to the real store.
    """
```

## Demo scenario

**Q:** What if credit analysis had `risk_tier='HIGH'` instead of `'MEDIUM'`?

**Expect:** **Materially different** `ApplicationSummary` — proves rules cascade through the counterfactual.

## Causal dependency

Event **E** depends on branch if `causation_id` traces to an event at or after the branch point.
