# Structured errors for LLM consumers

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Preconditions in tool **description**

Example text to embed in MCP tool docstrings:

> Requires an active agent session from `start_agent_session`. Calling without it returns `PreconditionFailed`.

LLMs only see descriptions — **preconditions must be explicit there**.

## Error payload shape

Return **typed** objects, not plain strings:

```json
{
  "error_type": "OptimisticConcurrencyError",
  "message": "...",
  "stream_id": "loan-APP-001",
  "expected_version": 3,
  "actual_version": 5,
  "suggested_action": "reload_stream_and_retry"
}
```

## Common types

| error_type | When |
|------------|------|
| `OptimisticConcurrencyError` | OCC mismatch |
| `PreconditionFailed` | Missing session, wrong order |
| `DomainError` | Invalid state transition |
| `ValidationError` | Pydantic / schema |
