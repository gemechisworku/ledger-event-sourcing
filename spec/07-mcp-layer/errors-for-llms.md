# Structured errors for LLM consumers

- Return **typed** objects: e.g. `error_type`, `message`, fields like `expected_version`, `actual_version`, `suggested_action`.
- **Preconditions** belong in **tool description** strings (not only runtime).

**Examples:** `OptimisticConcurrencyError`, `PreconditionFailed`, `DomainError` — align with `ledger/schema` or a dedicated `ledger/errors.py`.
