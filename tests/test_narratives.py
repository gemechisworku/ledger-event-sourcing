"""
tests/test_narratives.py
========================
Narrative scenario tests — primary correctness gate for the agent pipeline.

Run: pytest tests/test_narratives.py -v -s
"""
from __future__ import annotations

import asyncio
import sys
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from src.agents.credit_analysis_agent import CreditAnalysisAgent
from src.agents.compliance_agent import ComplianceAgent
from src.agents.decision_orchestrator_agent import DecisionOrchestratorAgent
from src.agents.document_processing_agent import DocumentProcessingAgent
from src.agents.fraud_detection_agent import FraudDetectionAgent
from src.domain.handlers import (
    handle_application_approved,
    handle_compliance_pipeline,
    handle_decision_requested,
    handle_human_review_completed,
    handle_record_fraud_screening,
    handle_submit_application,
)
from src.event_store import EventStore
from src.registry.client import CompanyProfile
from src.schema.events import (
    AgentType,
    ApplicationSubmitted,
    ComplianceCheckRequested,
    CreditAnalysisCompleted,
    CreditAnalysisRequested,
    CreditDecision,
    DocumentType,
    ExtractionCompleted,
    FinancialFacts,
    FraudScreeningRequested,
    LoanPurpose,
    RiskTier,
)
from tests.pg_helpers import candidate_postgres_urls


async def _cleanup_narr_streams(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM outbox o
            WHERE o.event_id IN (
                SELECT event_id FROM events WHERE stream_id LIKE 'test-narr%'
            )
            """
        )
        await conn.execute("DELETE FROM events WHERE stream_id LIKE 'test-narr%'")
        await conn.execute("DELETE FROM event_streams WHERE stream_id LIKE 'test-narr%'")


@pytest.fixture
async def store():
    last_exc: Exception | None = None
    for url in candidate_postgres_urls():
        s = EventStore(url)
        try:
            await s.connect()
            assert s._pool is not None
            await _cleanup_narr_streams(s._pool)
            yield s
            await _cleanup_narr_streams(s._pool)
            await s.close()
            return
        except Exception as exc:
            last_exc = exc
            if getattr(s, "_pool", None) is not None:
                await s.close()
    pytest.skip(
        "PostgreSQL not reachable (tried TEST_DB_URL, DATABASE_URL, APPLICANT_REGISTRY_URL, default): "
        f"{last_exc!r}"
    )


def _llm_json_response() -> MagicMock:
    """Deterministic credit JSON — mock for OpenAI SDK format."""

    async def fake_create(*_args, **_kwargs):
        msg = MagicMock()
        msg.content = (
            '{"risk_tier":"MEDIUM","recommended_limit_usd":400000,'
            '"confidence":0.82,"rationale":"Concurrent test run — deterministic JSON.",'
            '"key_concerns":[],"data_quality_caveats":[],"policy_overrides_applied":[]}'
        )
        msg.tool_calls = None
        choice = MagicMock()
        choice.message = msg
        choice.finish_reason = "stop"
        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 200
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    client = MagicMock()
    completions = MagicMock()
    completions.create = AsyncMock(side_effect=fake_create)
    chat = MagicMock()
    chat.completions = completions
    client.chat = chat
    return client


def _fraud_llm_json_response() -> MagicMock:
    async def fake_create(*_args, **_kwargs):
        msg = MagicMock()
        msg.content = (
            '{"fraud_score":0.1,"recommendation":"CLEAR",'
            '"anomalies":[{"severity":"LOW","evidence":"none","fields":[]}]}'
        )
        msg.tool_calls = None
        choice = MagicMock()
        choice.message = msg
        choice.finish_reason = "stop"
        usage = MagicMock()
        usage.prompt_tokens = 50
        usage.completion_tokens = 80
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    client = MagicMock()
    completions = MagicMock()
    completions.create = AsyncMock(side_effect=fake_create)
    chat = MagicMock()
    chat.completions = completions
    client.chat = chat
    return client


def _orch_llm_decline_response() -> MagicMock:
    async def fake_create(*_args, **_kwargs):
        msg = MagicMock()
        msg.content = (
            '{"recommendation":"DECLINE","confidence":0.72,'
            '"executive_summary":"Deterministic orchestrator decline for narrative test."}'
        )
        msg.tool_calls = None
        choice = MagicMock()
        choice.message = msg
        choice.finish_reason = "stop"
        usage = MagicMock()
        usage.prompt_tokens = 60
        usage.completion_tokens = 120
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    client = MagicMock()
    completions = MagicMock()
    completions.create = AsyncMock(side_effect=fake_create)
    chat = MagicMock()
    chat.completions = completions
    client.chat = chat
    return client


def _narr_company_profile(*, company_id: str, jurisdiction: str = "WA") -> CompanyProfile:
    return CompanyProfile(
        company_id=company_id,
        name="Narrative Test Co",
        industry="Retail",
        naics="441110",
        jurisdiction=jurisdiction,
        legal_type="LLC",
        founded_year=2010,
        employee_count=42,
        risk_segment="MEDIUM",
        trajectory="STABLE",
        submission_channel="web",
        ip_region="US-WA",
    )


def _credit_registry_mock(applicant_id: str) -> MagicMock:
    """ApplicantRegistry-compatible mock: get_company and related calls are async."""
    reg = MagicMock()
    reg.get_company = AsyncMock(return_value=_narr_company_profile(company_id=applicant_id))
    reg.get_financial_history = AsyncMock(return_value=[])
    reg.get_compliance_flags = AsyncMock(return_value=[])
    reg.get_loan_relationships = AsyncMock(return_value=[])
    return reg


@pytest.mark.asyncio
async def test_narr01_concurrent_occ_collision(store):
    """
    NARR-01: Two CreditAnalysisAgent instances run simultaneously.
    Expected: exactly one CreditAnalysisCompleted in credit stream (not two),
              second agent gets OCC, reloads, retries successfully.
    """
    app_id = f"test-narr01-{uuid4().hex[:10]}"

    sub = ApplicationSubmitted(
        application_id=app_id,
        applicant_id="COMP-NARR01",
        requested_amount_usd=Decimal("500000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=36,
        submission_channel="web",
        contact_email="narr01@test.invalid",
        contact_name="Narr01 Test",
        submitted_at=datetime.now(timezone.utc),
        application_reference="NARR-01",
    ).to_store_dict()
    await store.append(f"loan-{app_id}", [sub], expected_version=-1)

    facts = FinancialFacts(
        total_revenue=Decimal("5000000"),
        net_income=Decimal("400000"),
        total_assets=Decimal("8000000"),
    )
    ext = ExtractionCompleted(
        package_id=f"pkg-{app_id}",
        document_id="doc-1",
        document_type=DocumentType.INCOME_STATEMENT,
        facts=facts,
        raw_text_length=100,
        tables_extracted=1,
        processing_ms=10,
        completed_at=datetime.now(timezone.utc),
    ).to_store_dict()
    await store.append(f"docpkg-{app_id}", [ext], expected_version=-1)

    client = _llm_json_response()

    def make_agent() -> CreditAnalysisAgent:
        return CreditAnalysisAgent(
            agent_id="credit-test",
            agent_type=AgentType.CREDIT_ANALYSIS.value,
            store=store,
            registry=_credit_registry_mock("COMP-NARR01"),
            client=client,
        )

    await asyncio.gather(
        make_agent().process_application(app_id),
        make_agent().process_application(app_id),
    )

    credit = await store.load_stream(f"credit-{app_id}")
    completed = [e for e in credit if e.event_type == "CreditAnalysisCompleted"]
    assert len(completed) == 1

    loan = await store.load_stream(f"loan-{app_id}")
    fraud_req = [e for e in loan if e.event_type == "FraudScreeningRequested"]
    assert len(fraud_req) == 1


@pytest.mark.asyncio
async def test_narr02_document_extraction_failure(store):
    """
    NARR-02: Income statement PDF with missing EBITDA line.
    Expected: DocumentQualityFlagged with critical_missing_fields=['ebitda'],
              CreditAnalysisCompleted.confidence <= 0.75,
              CreditAnalysisCompleted.data_quality_caveats is non-empty.
    """
    app_id = f"test-narr02-{uuid4().hex[:10]}"
    sub = ApplicationSubmitted(
        application_id=app_id,
        applicant_id="COMP-001",
        requested_amount_usd=Decimal("500000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=36,
        submission_channel="web",
        contact_email="narr02@test.invalid",
        contact_name="Narr02 Test",
        submitted_at=datetime.now(timezone.utc),
        application_reference="NARR-02",
    ).to_store_dict()
    await store.append(f"loan-{app_id}", [sub], expected_version=-1)

    doc_agent = DocumentProcessingAgent(
        agent_id="doc-test",
        agent_type=AgentType.DOCUMENT_PROCESSING.value,
        store=store,
        registry=MagicMock(),
        client=MagicMock(),
    )
    await doc_agent.process_application(app_id)

    docpkg = await store.load_stream(f"docpkg-{app_id}")
    flagged = [e for e in docpkg if e.event_type == "DocumentQualityFlagged"]
    assert len(flagged) == 1
    assert flagged[0].payload.get("critical_missing_fields") == ["ebitda"]

    client = _llm_json_response()
    registry = AsyncMock()
    registry.get_company = AsyncMock(return_value=_narr_company_profile(company_id="COMP-001"))
    registry.get_financial_history = AsyncMock(return_value=[])
    registry.get_compliance_flags = AsyncMock(return_value=[])
    registry.get_loan_relationships = AsyncMock(return_value=[])

    credit = CreditAnalysisAgent(
        agent_id="credit-test",
        agent_type=AgentType.CREDIT_ANALYSIS.value,
        store=store,
        registry=registry,
        client=client,
    )
    await credit.process_application(app_id)

    credit_evs = await store.load_stream(f"credit-{app_id}")
    completed = [e for e in credit_evs if e.event_type == "CreditAnalysisCompleted"]
    assert len(completed) == 1
    dec = completed[0].payload.get("decision") or {}
    assert float(dec.get("confidence", 1.0)) <= 0.75
    assert len(dec.get("data_quality_caveats") or []) >= 1


@pytest.mark.asyncio
async def test_narr03_agent_crash_recovery(store):
    """
    NARR-03: FraudDetectionAgent crashes mid-session.
    Expected: only ONE FraudScreeningCompleted event in fraud stream,
              second AgentSessionStarted has context_source starting with 'prior_session_replay:',
              no duplicate analysis work.
    """
    app_id = f"test-narr03-{uuid4().hex[:10]}"
    sub = ApplicationSubmitted(
        application_id=app_id,
        applicant_id="COMP-N03",
        requested_amount_usd=Decimal("400000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=24,
        submission_channel="web",
        contact_email="narr03@test.invalid",
        contact_name="Narr03 Test",
        submitted_at=datetime.now(timezone.utc),
        application_reference="NARR-03",
    ).to_store_dict()
    await store.append(f"loan-{app_id}", [sub], expected_version=-1)

    facts = FinancialFacts(
        total_revenue=Decimal("3000000"),
        net_income=Decimal("200000"),
        total_assets=Decimal("5000000"),
    )
    ext = ExtractionCompleted(
        package_id=f"pkg-{app_id}",
        document_id="doc-1",
        document_type=DocumentType.INCOME_STATEMENT,
        facts=facts,
        raw_text_length=100,
        tables_extracted=1,
        processing_ms=10,
        completed_at=datetime.now(timezone.utc),
    ).to_store_dict()
    await store.append(f"docpkg-{app_id}", [ext], expected_version=-1)

    loan_sid = f"loan-{app_id}"
    v = await store.stream_version(loan_sid)
    await store.append(
        loan_sid,
        [
            CreditAnalysisRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                requested_by="test",
            ).to_store_dict()
        ],
        expected_version=v,
    )
    v = await store.stream_version(loan_sid)
    await store.append(
        loan_sid,
        [
            FraudScreeningRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                triggered_by_event_id="credit-sess",
            ).to_store_dict()
        ],
        expected_version=v,
    )

    registry = AsyncMock()
    registry.get_company = AsyncMock(return_value=_narr_company_profile(company_id="COMP-N03"))
    registry.get_financial_history = AsyncMock(return_value=[])
    registry.get_compliance_flags = AsyncMock(return_value=[])
    registry.get_loan_relationships = AsyncMock(return_value=[])

    client = _fraud_llm_json_response()
    a1 = FraudDetectionAgent(
        agent_id="fraud-test",
        agent_type=AgentType.FRAUD_DETECTION.value,
        store=store,
        registry=registry,
        client=client,
        crash_before_complete=True,
    )
    try:
        await a1.process_application(app_id)
    except RuntimeError:
        pass
    failed_sid = a1.session_id

    a2 = FraudDetectionAgent(
        agent_id="fraud-test",
        agent_type=AgentType.FRAUD_DETECTION.value,
        store=store,
        registry=registry,
        client=_fraud_llm_json_response(),
        crash_before_complete=False,
    )
    await a2.process_application(app_id, prior_session_id=failed_sid)

    fraud = await store.load_stream(f"fraud-{app_id}")
    completed = [e for e in fraud if e.event_type == "FraudScreeningCompleted"]
    assert len(completed) == 1

    sess = await store.load_stream(f"agent-{a2.agent_type}-{a2.session_id}")
    started = [e for e in sess if e.event_type == "AgentSessionStarted"]
    assert len(started) == 1
    ctx = started[0].payload.get("context_source") or ""
    assert str(ctx).startswith("prior_session_replay:")


@pytest.mark.asyncio
async def test_narr04_compliance_hard_block(store):
    """
    NARR-04: Montana applicant (jurisdiction='MT') triggers REG-003.
    Expected: ComplianceRuleFailed(rule_id='REG-003', is_hard_block=True),
              NO DecisionGenerated event,
              ApplicationDeclined with adverse_action_notice_required=True.
    """
    app_id = f"test-narr04-{uuid4().hex[:10]}"
    sub = ApplicationSubmitted(
        application_id=app_id,
        applicant_id="COMP-MT",
        requested_amount_usd=Decimal("350000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=36,
        submission_channel="web",
        contact_email="narr04@test.invalid",
        contact_name="Narr04 Test",
        submitted_at=datetime.now(timezone.utc),
        application_reference="NARR-04",
    ).to_store_dict()
    await store.append(f"loan-{app_id}", [sub], expected_version=-1)
    loan_sid = f"loan-{app_id}"
    v = await store.stream_version(loan_sid)
    await store.append(
        loan_sid,
        [
            ComplianceCheckRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                triggered_by_event_id="fraud-sess",
                regulation_set_version="2026-Q1",
                rules_to_evaluate=[f"REG-00{i}" for i in range(1, 7)],
            ).to_store_dict()
        ],
        expected_version=v,
    )

    registry = AsyncMock()
    registry.get_company = AsyncMock(return_value=_narr_company_profile(company_id="COMP-MT", jurisdiction="MT"))
    registry.get_financial_history = AsyncMock(return_value=[])
    registry.get_compliance_flags = AsyncMock(return_value=[])

    agent = ComplianceAgent(
        agent_id="comp-test",
        agent_type=AgentType.COMPLIANCE.value,
        store=store,
        registry=registry,
        client=MagicMock(),
    )
    await agent.process_application(app_id)

    comp = await store.load_stream(f"compliance-{app_id}")
    failed = [e for e in comp if e.event_type == "ComplianceRuleFailed" and e.payload.get("rule_id") == "REG-003"]
    assert len(failed) == 1
    assert failed[0].payload.get("is_hard_block") is True

    loan = await store.load_stream(f"loan-{app_id}")
    assert not any(e.event_type == "DecisionGenerated" for e in loan)
    declined = [e for e in loan if e.event_type == "ApplicationDeclined"]
    assert len(declined) == 1
    assert declined[0].payload.get("adverse_action_notice_required") is True


@pytest.mark.asyncio
async def test_narr05_human_override(store):
    """
    NARR-05: Orchestrator recommends DECLINE; human loan officer overrides to APPROVE.
    Expected: DecisionGenerated(recommendation='DECLINE'),
              HumanReviewCompleted(override=True, reviewer_id='LO-Sarah-Chen'),
              ApplicationApproved(approved_amount_usd=750000, conditions has 2 items).
    """
    app_id = f"test-narr05-{uuid4().hex[:10]}"
    await handle_submit_application(
        store,
        application_id=app_id,
        applicant_id="COMP-N05",
        requested_amount_usd=Decimal("800000"),
        loan_purpose=LoanPurpose.WORKING_CAPITAL,
        loan_term_months=60,
        submission_channel="web",
        contact_email="narr05@test.invalid",
        contact_name="Narr05 Test",
        application_reference="NARR-05",
    )

    loan_sid = f"loan-{app_id}"
    v = await store.stream_version(loan_sid)
    await store.append(
        loan_sid,
        [
            CreditAnalysisRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                requested_by="test",
            ).to_store_dict()
        ],
        expected_version=v,
    )

    credit_ev = CreditAnalysisCompleted(
        application_id=app_id,
        session_id="sess-n05-cred",
        decision=CreditDecision(
            risk_tier=RiskTier.MEDIUM,
            recommended_limit_usd=Decimal("600000"),
            confidence=0.78,
            rationale="Seeded credit outcome for narrative.",
            key_concerns=[],
            data_quality_caveats=[],
            policy_overrides_applied=[],
        ),
        model_version="test",
        model_deployment_id="dep-test",
        input_data_hash="hash-n05",
        analysis_duration_ms=50,
        completed_at=datetime.now(timezone.utc),
    ).to_store_dict()
    await store.append(f"credit-{app_id}", [credit_ev], expected_version=-1)

    v = await store.stream_version(loan_sid)
    await store.append(
        loan_sid,
        [
            FraudScreeningRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                triggered_by_event_id="sess-n05-cred",
            ).to_store_dict()
        ],
        expected_version=v,
    )

    await handle_record_fraud_screening(
        store,
        application_id=app_id,
        session_id="sess-n05-fraud",
        fraud_score=0.12,
    )

    v = await store.stream_version(loan_sid)
    await store.append(
        loan_sid,
        [
            ComplianceCheckRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                triggered_by_event_id="sess-n05-fraud",
                regulation_set_version="2026-Q1",
                rules_to_evaluate=[f"REG-00{i}" for i in range(1, 7)],
            ).to_store_dict()
        ],
        expected_version=v,
    )

    await handle_compliance_pipeline(
        store,
        application_id=app_id,
        session_id="sess-n05-comp",
        rules_to_evaluate=[f"REG-00{i}" for i in range(1, 7)],
    )

    await handle_decision_requested(
        store,
        application_id=app_id,
        triggered_by_event_id="sess-n05-comp",
    )

    orch = DecisionOrchestratorAgent(
        agent_id="orch-test",
        agent_type=AgentType.DECISION_ORCHESTRATOR.value,
        store=store,
        registry=MagicMock(),
        client=_orch_llm_decline_response(),
    )
    await orch.process_application(app_id)

    loan = await store.load_stream(loan_sid)
    decisions = [e for e in loan if e.event_type == "DecisionGenerated"]
    assert len(decisions) == 1
    assert (decisions[0].payload.get("recommendation") or "").upper() == "DECLINE"

    await handle_human_review_completed(
        store,
        application_id=app_id,
        reviewer_id="LO-Sarah-Chen",
        override=True,
        original_recommendation="DECLINE",
        final_decision="APPROVED",
        override_reason="Counterparty risk mitigated by additional collateral; officer override.",
    )

    await handle_application_approved(
        store,
        application_id=app_id,
        approved_amount_usd=Decimal("750000"),
        conditions=[
            "Annual audited financial statements required within 90 days.",
            "Loan amount subject to 1.25x minimum debt service coverage.",
        ],
        approved_by="LO-Sarah-Chen",
    )

    loan = await store.load_stream(loan_sid)
    reviews = [e for e in loan if e.event_type == "HumanReviewCompleted"]
    assert len(reviews) == 1
    assert reviews[0].payload.get("override") is True
    assert reviews[0].payload.get("reviewer_id") == "LO-Sarah-Chen"

    approvals = [e for e in loan if e.event_type == "ApplicationApproved"]
    assert len(approvals) == 1
    amt = approvals[0].payload.get("approved_amount_usd")
    assert amt in ("750000", 750000, Decimal("750000")) or str(amt) == "750000"
    cond = approvals[0].payload.get("conditions") or []
    assert len(cond) == 2
