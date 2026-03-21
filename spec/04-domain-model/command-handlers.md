# Command handlers

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

## Pattern (required shape)

Every handler:

1. **Load** aggregates: `LoanApplicationAggregate.load(store, application_id)`, `AgentSessionAggregate.load(store, agent_id, session_id)` as needed.
2. **Validate** invariants (`assert_*` methods) — **before** emitting events.
3. **Build** new `BaseEvent` instances — pure logic, no I/O.
4. **`append`** to correct `stream_id` with `expected_version = aggregate.version`, plus `correlation_id` / `causation_id` from command.

## Example (reference — credit analysis)

```python
async def handle_credit_analysis_completed(
    cmd: CreditAnalysisCompletedCommand,
    store: EventStore,
) -> None:
    app = await LoanApplicationAggregate.load(store, cmd.application_id)
    agent = await AgentSessionAggregate.load(store, cmd.agent_id, cmd.session_id)

    app.assert_awaiting_credit_analysis()
    agent.assert_context_loaded()
    agent.assert_model_version_current(cmd.model_version)

    new_events = [
        CreditAnalysisCompleted(
            application_id=cmd.application_id,
            agent_id=cmd.agent_id,
            session_id=cmd.session_id,
            model_version=cmd.model_version,
            confidence_score=cmd.confidence_score,
            risk_tier=cmd.risk_tier,
            recommended_limit_usd=cmd.recommended_limit_usd,
            analysis_duration_ms=cmd.duration_ms,
            input_data_hash=hash_inputs(cmd.input_data),
        )
    ]

    await store.append(
        stream_id=f"loan-{cmd.application_id}",
        events=new_events,
        expected_version=app.version,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
    )
```

**Note:** If `CreditAnalysisCompleted` is stored on **AgentSession** stream per catalogue, adjust stream target — **your** `ledger/schema/events.py` and requirements must agree; multi-stream appends may need **sagas** or **ordered steps** (document).

## Commands to implement (minimum set)

- `submit_application`
- `credit_analysis_completed`
- `fraud_screening_completed`
- `compliance_check` (pass/fail)
- `generate_decision`
- `human_review_completed`
- `start_agent_session` (emits `AgentContextLoaded`)

## ApplicantRegistryClient

- `ledger/registry/client.py` — lookup applicant profile, duplicate `application_id`, etc. as required by tests.
