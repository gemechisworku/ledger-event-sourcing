# SLOs & lag

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Targets

| Projection | Max lag (normal ops) |
|------------|----------------------|
| ApplicationSummary | **500ms** |
| ComplianceAuditView | **2s** |

## Load testing

- Simulate **50 concurrent command handlers** appending events.
- Assert projection lag stays within SLO (or document degradation).

## Metrics

- **`get_lag()`** per projection — ms from “latest event in store” to “last processed by this projection”.
- Expose via daemon; surface on health resource.
