# Concurrency & outbox

- **`expected_version`:** `-1` = expect empty/new stream; `N` = stream must be exactly at `N` before append.
- **Conflict:** raise **`OptimisticConcurrencyError`** with enough context for MCP callers.
- **Outbox:** same transaction as `events` insert; separate process publishes from `outbox` (e.g. Kafka bridge — note in `DESIGN.md`).
