"""
tests/test_narratives.py
========================
Narrative scenario tests — primary correctness gate for the agent pipeline.

Run: pytest tests/test_narratives.py -v -s
"""
from __future__ import annotations

import asyncio
import sys
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
from src.event_store import EventStore
from src.schema.events import (
    AgentType,
    ApplicationSubmitted,
    DocumentType,
    ExtractionCompleted,
    FinancialFacts,
    LoanPurpose,
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
    """Deterministic credit JSON — no real Anthropic call."""

    async def fake_create(*_args, **_kwargs):
        class Usage:
            input_tokens = 100
            output_tokens = 200

        class Block:
            text = (
                '{"risk_tier":"MEDIUM","recommended_limit_usd":400000,'
                '"confidence":0.82,"rationale":"Concurrent test run — deterministic JSON.",'
                '"key_concerns":[],"data_quality_caveats":[],"policy_overrides_applied":[]}'
            )

        class Resp:
            content = [Block()]
            usage = Usage()

        return Resp()

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=fake_create)
    return client


@pytest.mark.asyncio
async def test_narr01_concurrent_occ_collision(store):
    """
    NARR-01: Two CreditAnalysisAgent instances run simultaneously.
    Expected: exactly one CreditAnalysisCompleted in credit stream (not two),
              second agent gets OCC, reloads, retries successfully.
    """
    app_id = "test-narr01-APP-001"

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
            registry=MagicMock(),
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
async def test_narr02_document_extraction_failure():
    """
    NARR-02: Income statement PDF with missing EBITDA line.
    Expected: DocumentQualityFlagged with critical_missing_fields=['ebitda'],
              CreditAnalysisCompleted.confidence <= 0.75,
              CreditAnalysisCompleted.data_quality_caveats is non-empty.
    """
    pytest.skip("Implement after DocumentProcessingAgent + CreditAnalysisAgent working")


@pytest.mark.asyncio
async def test_narr03_agent_crash_recovery():
    """
    NARR-03: FraudDetectionAgent crashes mid-session.
    Expected: only ONE FraudScreeningCompleted event in fraud stream,
              second AgentSessionStarted has context_source starting with 'prior_session_replay:',
              no duplicate analysis work.
    """
    pytest.skip("Implement after FraudDetectionAgent + crash recovery implemented")


@pytest.mark.asyncio
async def test_narr04_compliance_hard_block():
    """
    NARR-04: Montana applicant (jurisdiction='MT') triggers REG-003.
    Expected: ComplianceRuleFailed(rule_id='REG-003', is_hard_block=True),
              NO DecisionGenerated event,
              ApplicationDeclined with adverse_action_notice_required=True.
    """
    pytest.skip("Implement after ComplianceAgent is working")


@pytest.mark.asyncio
async def test_narr05_human_override():
    """
    NARR-05: Orchestrator recommends DECLINE; human loan officer overrides to APPROVE.
    Expected: DecisionGenerated(recommendation='DECLINE'),
              HumanReviewCompleted(override=True, reviewer_id='LO-Sarah-Chen'),
              ApplicationApproved(approved_amount_usd=750000, conditions has 2 items).
    """
    pytest.skip("Implement after all agents + HumanReviewCompleted command handler working")
