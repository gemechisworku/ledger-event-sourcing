# Upcasting

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 4A.

## Registry API

```python
class UpcasterRegistry:
    def __init__(self):
        self._upcasters: dict[tuple[str, int], Callable] = {}

    def register(self, event_type: str, from_version: int):
        def decorator(fn: Callable[[dict], dict]) -> Callable:
            self._upcasters[(event_type, from_version)] = fn
            return fn
        return decorator

    def upcast(self, event: StoredEvent) -> StoredEvent:
        current = event
        v = event.event_version
        while (event.event_type, v) in self._upcasters:
            new_payload = self._upcasters[(event.event_type, v)](current.payload)
            current = current.with_payload(new_payload, version=v + 1)
            v += 1
        return current
```

- **Call site:** `EventStore.load_stream` / `load_all` — **before** aggregate `_apply`.
- Callers never invoke upcasters manually.

## Required upcasters

### CreditAnalysisCompleted v1 → v2

Add fields:

- `model_version` — e.g. infer from `recorded_at` bucket or `"legacy-pre-2026"`
- `confidence_score` — **`null`** if unknown (do not fabricate)
- `regulatory_basis` — infer from rule versions active at `recorded_at` where possible

### DecisionGenerated v1 → v2

- Add `model_versions{}` — may require **loading AgentSession** streams for `contributing_agent_sessions` to read `AgentContextLoaded` — **document performance** (N+1 lookups).

## Immutability test (required)

1. Insert v1 payload **directly** in DB (or via append with version 1).
2. `load_stream` → consumer sees **v2-shaped** event.
3. Raw SQL read of `events.payload` → **unchanged** v1 bytes.

If upcast mutates stored rows, **event sourcing guarantee is broken**.
