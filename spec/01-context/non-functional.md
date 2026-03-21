# Non-functional constraints

## Platform

- **DB:** PostgreSQL — schema in [`../03-event-store/schema-contract.md`](../03-event-store/schema-contract.md).
- **Runtime:** Python 3.10+, async (`asyncpg`), `uv` per `pyproject.toml`.

## SLOs (from requirements)

| Projection | Lag target (normal) |
|------------|---------------------|
| ApplicationSummary | &lt; 500ms |
| ComplianceAuditView | up to ~2s |

- Daemon must expose **per-projection lag** (`get_lag` / `get_all_lags`).
- Tests should stress **50 concurrent command handlers** and assert lag stays within bounds where feasible.

## Realtime / ops (optional later)

- Requirements mention PostgreSQL `LISTEN/NOTIFY` for subscriptions — not mandatory for MVP if polling daemon is used.

## Documentation

- **Every schema column** justified in `DESIGN.md` (per requirements).
