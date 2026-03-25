# Phase 3 — Agents & narrative coverage (NARR-02 … NARR-05)

## Goals

- Un-skip **`tests/test_narratives.py`** for **NARR-02** through **NARR-05** with real Postgres-backed `EventStore` fixtures.
- Ship minimal but coherent **DocumentProcessing**, **FraudDetection**, **Compliance**, and **DecisionOrchestrator** agents aligned with `CreditAnalysisAgent` patterns.

## Design choices

1. **`DocumentQualityFlagged`** — Add a dedicated doc-package event (narrative name) alongside **`QualityAssessmentCompleted`**, which already carries `critical_missing_fields`. Document processing emits both for clarity.
2. **Credit policy (NARR-02)** — In **`CreditAnalysisAgent._node_policy`**, when document quality flags include missing **EBITDA** (`CRITICAL_MISSING:ebitda` or `ebitda` in critical missing lists), cap **`confidence`** at **0.75** and ensure **`data_quality_caveats`** is non-empty.
3. **Fraud crash / replay (NARR-03)** — Extend **`BaseApexAgent.process_application`** with optional **`prior_session_id`**. **`AgentSessionStarted.context_source`** becomes `prior_session_replay:{prior_session_id}`. Fraud **`write_output`** is idempotent: if **`FraudScreeningInitiated`** exists without **`FraudScreeningCompleted`**, do not append a second **`FraudScreeningInitiated`**; append completion only.
4. **Compliance REG-003 (NARR-04)** — **`ComplianceAgent`** loads **`CompanyProfile`** from **`registry.get_company`**, evaluates deterministic rules (reuse logic from former `stub_agents.REGULATIONS`). On hard block: **`ComplianceRuleFailed`**, **`ComplianceCheckCompleted`** with **`BLOCKED`**, **`ApplicationDeclined`** — **no** **`DecisionGenerated`**. Tests use **`AsyncMock`** registry returning **`jurisdiction='MT'`**.
5. **Human override (NARR-05)** — **`DecisionGenerated`** with **`DECLINE`** leaves the loan in **`DECLINED`**. Append **`HumanReviewRequested`** (new handler) so state becomes **`PENDING_HUMAN_REVIEW`**, then **`handle_human_review_completed`** + **`handle_application_approved`** (with **`conditions`**). **`handle_application_approved`** gains an optional **`conditions`** argument.

## Implementation order

1. Schema: **`DocumentQualityFlagged`** + registry entry.
2. **`BaseApexAgent`**: **`prior_session_id`** on **`process_application`** / **`_start_session`**.
3. **`document_processing_agent.py`**, **`fraud_detection_agent.py`**, **`compliance_agent.py`**, **`decision_orchestrator_agent.py`**.
4. **`handlers.py`**: **`handle_human_review_requested`**, extend **`handle_application_approved`**.
5. **`credit_analysis_agent.py`**: EBITDA quality policy.
6. **`base_agent.py`**: replace inline stubs with imports from new modules.
7. **`tests/test_narratives.py`**: implement NARR-02 … NARR-05; keep NARR-01 as-is.

## Verification

```bash
uv run pytest tests/test_narratives.py -v
```
