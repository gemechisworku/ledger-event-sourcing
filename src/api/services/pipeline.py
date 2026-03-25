"""
Pipeline orchestrator — runs agent stages in order; yields progress dicts for SSE.

Stages match loan flow: document → credit → fraud → compliance → decision.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic
from unittest.mock import AsyncMock

from src.registry.client import ApplicantRegistryClient, CompanyProfile

DEFAULT_STAGES = ["document", "credit", "fraud", "compliance", "decision"]


def build_registry_client(store: Any) -> Any:
    """Real registry when Postgres pool exists; otherwise async mock for tests."""
    pool = getattr(store, "_pool", None) or getattr(store, "pool", None)
    if pool is not None:
        return ApplicantRegistryClient(pool)

    async def _company(company_id: str) -> CompanyProfile:
        return CompanyProfile(
            company_id=company_id,
            name="API Test Co",
            industry="Retail",
            naics="441110",
            jurisdiction="WA",
            legal_type="LLC",
            founded_year=2010,
            employee_count=10,
            risk_segment="MEDIUM",
            trajectory="STABLE",
            submission_channel="web",
            ip_region="US",
        )

    m = AsyncMock()
    m.get_company = AsyncMock(side_effect=_company)
    m.get_financial_history = AsyncMock(return_value=[])
    m.get_compliance_flags = AsyncMock(return_value=[])
    m.get_loan_relationships = AsyncMock(return_value=[])
    return m


async def run_pipeline_events(
    application_id: str,
    store: Any,
    anthropic_client: AsyncAnthropic | Any,
    stages: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    from src.agents.compliance_agent import ComplianceAgent
    from src.agents.credit_analysis_agent import CreditAnalysisAgent
    from src.agents.decision_orchestrator_agent import DecisionOrchestratorAgent
    from src.agents.document_processing_agent import DocumentProcessingAgent
    from src.agents.fraud_detection_agent import FraudDetectionAgent
    from src.schema.events import AgentType

    use_stages = list(stages) if stages else list(DEFAULT_STAGES)
    total = len(use_stages)
    if total == 0:
        yield {"type": "error", "message": "No stages to run"}
        return

    loan = await store.load_stream(f"loan-{application_id}")
    if not any(e.event_type == "ApplicationSubmitted" for e in loan):
        yield {
            "type": "error",
            "message": "ApplicationSubmitted missing — create the application first (POST /v1/applications).",
        }
        return

    reg = build_registry_client(store)

    for i, stage in enumerate(use_stages):
        yield {
            "type": "progress",
            "stage": stage,
            "index": i + 1,
            "total": total,
            "pct": int(100 * i / total) if total else 0,
            "message": f"Starting {stage}",
            "application_id": application_id,
        }

        if stage == "document":
            agent = DocumentProcessingAgent(
                agent_id="api-document",
                agent_type=AgentType.DOCUMENT_PROCESSING.value,
                store=store,
                registry=reg,
                client=anthropic_client,
            )
            await agent.process_application(application_id)
        elif stage == "credit":
            agent = CreditAnalysisAgent(
                agent_id="api-credit",
                agent_type=AgentType.CREDIT_ANALYSIS.value,
                store=store,
                registry=reg,
                client=anthropic_client,
            )
            await agent.process_application(application_id)
        elif stage == "fraud":
            agent = FraudDetectionAgent(
                agent_id="api-fraud",
                agent_type=AgentType.FRAUD_DETECTION.value,
                store=store,
                registry=reg,
                client=anthropic_client,
            )
            await agent.process_application(application_id)
        elif stage == "compliance":
            agent = ComplianceAgent(
                agent_id="api-compliance",
                agent_type=AgentType.COMPLIANCE.value,
                store=store,
                registry=reg,
                client=anthropic_client,
            )
            await agent.process_application(application_id)
        elif stage == "decision":
            agent = DecisionOrchestratorAgent(
                agent_id="api-orchestrator",
                agent_type=AgentType.DECISION_ORCHESTRATOR.value,
                store=store,
                registry=reg,
                client=anthropic_client,
            )
            await agent.process_application(application_id)
        else:
            yield {"type": "error", "message": f"Unknown stage: {stage!r}"}
            return

        yield {
            "type": "progress",
            "stage": stage,
            "index": i + 1,
            "total": total,
            "pct": int(100 * (i + 1) / total) if total else 100,
            "message": f"Completed {stage}",
            "application_id": application_id,
        }

    yield {"type": "complete", "application_id": application_id}
