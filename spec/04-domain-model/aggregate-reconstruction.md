# Aggregate reconstruction

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Required pattern

```python
class LoanApplicationAggregate:
    @classmethod
    async def load(cls, store: EventStore, application_id: str) -> "LoanApplicationAggregate":
        events = await store.load_stream(f"loan-{application_id}")
        agg = cls(application_id=application_id)
        for event in events:
            agg._apply(event)
        return agg

    def _apply(self, event: StoredEvent) -> None:
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event)
        self.version = event.stream_position

    def _on_ApplicationSubmitted(self, event: StoredEvent) -> None:
        self.state = ApplicationState.SUBMITTED
        self.applicant_id = event.payload["applicant_id"]
        self.requested_amount = event.payload["requested_amount_usd"]
```

- **`event.event_type`** must match handler suffix (use consistent casing — often PascalCase from schema).
- **`version`** tracks last applied `stream_position` for `append(..., expected_version=...)`.

## Upcasting

- `load_stream` returns **upcasted** `StoredEvent`; aggregates see current schema version.
