"""
DocumentProcessingAgent — minimal doc pipeline for narratives and integration tests.
Emits extraction + quality events on docpkg-{application_id} and CreditAnalysisRequested on loan.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.base_agent import BaseApexAgent
from src.schema.events import (
    CreditAnalysisRequested,
    DocumentFormatValidated,
    DocumentQualityFlagged,
    DocumentType,
    ExtractionCompleted,
    FinancialFacts,
    PackageReadyForAnalysis,
    QualityAssessmentCompleted,
)


class DocProcState(TypedDict):
    application_id: str
    session_id: str
    agent_id: str
    package_id: str
    document_id: str
    errors: list[str]
    output_events_written: list
    next_agent_triggered: str | None


class DocumentProcessingAgent(BaseApexAgent):
    """Synthetic extraction + quality for environments without Week 3 PDF binaries."""

    def build_graph(self) -> Any:
        g = StateGraph(DocProcState)
        g.add_node("validate_inputs", self._node_validate_inputs)
        g.add_node("validate_document_format", self._node_validate_format)
        g.add_node("run_week3_extraction", self._node_extract)
        g.add_node("assess_quality", self._node_assess_quality)
        g.add_node("write_output", self._node_write_output)
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs", "validate_document_format")
        g.add_edge("validate_document_format", "run_week3_extraction")
        g.add_edge("run_week3_extraction", "assess_quality")
        g.add_edge("assess_quality", "write_output")
        g.add_edge("write_output", END)
        return g.compile()

    def _initial_state(self, application_id: str) -> DocProcState:
        return DocProcState(
            application_id=application_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            package_id=f"pkg-{application_id}",
            document_id=f"doc-is-{application_id}",
            errors=[],
            output_events_written=[],
            next_agent_triggered=None,
        )

    async def _node_validate_inputs(self, state: DocProcState) -> DocProcState:
        t = time.time()
        loan = await self.store.load_stream(f"loan-{state['application_id']}")
        if not any(e.event_type == "ApplicationSubmitted" for e in loan):
            await self._record_input_failed(["application_id"], ["ApplicationSubmitted missing on loan stream"])
            raise ValueError("ApplicationSubmitted required before document processing")
        ms = int((time.time() - t) * 1000)
        await self._record_input_validated(["application_id"], ms)
        await self._record_node_execution("validate_inputs", ["loan_stream"], ["application_id"], ms)
        return state

    async def _node_validate_format(self, state: DocProcState) -> DocProcState:
        t = time.time()
        ev = DocumentFormatValidated(
            package_id=state["package_id"],
            document_id=state["document_id"],
            document_type=DocumentType.INCOME_STATEMENT,
            page_count=3,
            detected_format="pdf",
            validated_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(f"docpkg-{state['application_id']}", [ev])
        ms = int((time.time() - t) * 1000)
        await self._record_tool_call("format_check", "income_statement", "validated", ms)
        await self._record_node_execution("validate_document_format", ["document_id"], ["format_ok"], ms)
        return state

    async def _node_extract(self, state: DocProcState) -> DocProcState:
        t = time.time()
        # NARR-02: revenue / net income / assets present; EBITDA line intentionally absent
        facts = FinancialFacts(
            total_revenue=Decimal("5000000"),
            net_income=Decimal("400000"),
            total_assets=Decimal("8000000"),
            ebitda=None,
            extraction_notes=["ebitda_line_not_found_in_source_pdf"],
        )
        ext = ExtractionCompleted(
            package_id=state["package_id"],
            document_id=state["document_id"],
            document_type=DocumentType.INCOME_STATEMENT,
            facts=facts,
            raw_text_length=1200,
            tables_extracted=2,
            processing_ms=15,
            completed_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(f"docpkg-{state['application_id']}", [ext])
        ms = int((time.time() - t) * 1000)
        await self._record_tool_call("week3_extraction_pipeline", "income_statement", "ExtractionCompleted", ms)
        await self._record_node_execution("run_week3_extraction", ["document_id"], ["facts"], ms)
        return state

    async def _node_assess_quality(self, state: DocProcState) -> DocProcState:
        t = time.time()
        crit = ["ebitda"]
        qa = QualityAssessmentCompleted(
            package_id=state["package_id"],
            document_id=state["document_id"],
            overall_confidence=0.72,
            is_coherent=True,
            anomalies=["ebitda_not_reported"],
            critical_missing_fields=crit,
            reextraction_recommended=False,
            auditor_notes="EBITDA line missing from income statement extraction.",
            assessed_at=datetime.now(timezone.utc),
        ).to_store_dict()
        flagged = DocumentQualityFlagged(
            package_id=state["package_id"],
            application_id=state["application_id"],
            document_id=state["document_id"],
            critical_missing_fields=crit,
            flag_reason="Critical financial field EBITDA missing from extracted facts.",
            flagged_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(f"docpkg-{state['application_id']}", [qa, flagged])
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("assess_quality", ["facts"], ["quality_assessment"], ms)
        return state

    async def _node_write_output(self, state: DocProcState) -> DocProcState:
        t = time.time()
        app_id = state["application_id"]
        doc_sid = f"docpkg-{app_id}"
        loan_sid = f"loan-{app_id}"
        ready = PackageReadyForAnalysis(
            package_id=state["package_id"],
            application_id=app_id,
            documents_processed=1,
            has_quality_flags=True,
            quality_flag_count=1,
            ready_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(doc_sid, [ready])
        loan_evs = await self.store.load_stream(loan_sid)
        if not any(e.event_type == "CreditAnalysisRequested" for e in loan_evs):
            car = CreditAnalysisRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                requested_by=f"document-processing:{self.agent_id}",
            ).to_store_dict()
            await self._append_with_retry(loan_sid, [car])
        summary = "PackageReadyForAnalysis + CreditAnalysisRequested"
        await self._record_output_written(["PackageReadyForAnalysis", "CreditAnalysisRequested"], summary)
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("write_output", ["docpkg", "loan"], ["downstream_credit"], ms)
        return {**state, "next_agent_triggered": "credit_analysis"}
