"""
FraudDetectionAgent — registry cross-check + LLM narrative; idempotent completion + resume.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.base_agent import BaseApexAgent
from src.schema.events import (
    ComplianceCheckRequested,
    FraudAnomaly,
    FraudAnomalyDetected,
    FraudAnomalyType,
    FraudScreeningCompleted,
    FraudScreeningInitiated,
)


class FraudState(TypedDict):
    application_id: str
    session_id: str
    agent_id: str
    extracted_facts: dict | None
    registry_profile: dict | None
    historical_financials: list[dict] | None
    fraud_score: float | None
    anomalies: list[dict] | None
    recommendation: str | None
    errors: list[str]
    output_events_written: list
    next_agent_triggered: str | None


class FraudDetectionAgent(BaseApexAgent):
    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        store,
        registry,
        client,
        model: str | None = None,
        crash_before_complete: bool = False,
    ):
        super().__init__(agent_id, agent_type, store, registry, client, model=model)
        self._crash_before_complete = crash_before_complete

    def build_graph(self) -> Any:
        g = StateGraph(FraudState)
        for name in (
            "validate_inputs",
            "load_document_facts",
            "cross_reference_registry",
            "analyze_fraud_patterns",
            "write_output",
        ):
            g.add_node(name, getattr(self, f"_node_{name}"))
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs", "load_document_facts")
        g.add_edge("load_document_facts", "cross_reference_registry")
        g.add_edge("cross_reference_registry", "analyze_fraud_patterns")
        g.add_edge("analyze_fraud_patterns", "write_output")
        g.add_edge("write_output", END)
        return g.compile()

    def _initial_state(self, application_id: str) -> FraudState:
        return FraudState(
            application_id=application_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            extracted_facts=None,
            registry_profile=None,
            historical_financials=None,
            fraud_score=None,
            anomalies=None,
            recommendation=None,
            errors=[],
            output_events_written=[],
            next_agent_triggered=None,
        )

    async def _node_validate_inputs(self, state: FraudState) -> FraudState:
        t = time.time()
        loan = await self.store.load_stream(f"loan-{state['application_id']}")
        if not any(e.event_type == "FraudScreeningRequested" for e in loan):
            await self._record_input_failed(["loan_stream"], ["FraudScreeningRequested missing"])
            raise ValueError("FraudScreeningRequested required")
        ms = int((time.time() - t) * 1000)
        await self._record_input_validated(["application_id"], ms)
        await self._record_node_execution("validate_inputs", ["loan_stream"], ["ok"], ms)
        return state

    async def _node_load_document_facts(self, state: FraudState) -> FraudState:
        t = time.time()
        app_id = state["application_id"]
        pkg = await self.store.load_stream(f"docpkg-{app_id}")
        merged: dict = {}
        for ev in pkg:
            if ev.event_type != "ExtractionCompleted":
                continue
            facts = (ev.payload or {}).get("facts") or {}
            for k, v in facts.items():
                if v is not None and k not in merged:
                    merged[k] = v
        ms = int((time.time() - t) * 1000)
        await self._record_tool_call("load_event_store_stream", f"docpkg-{app_id}", f"{len(merged)} fields", ms)
        await self._record_node_execution("load_document_facts", ["docpkg"], ["extracted_facts"], ms)
        return {**state, "extracted_facts": merged}

    async def _node_cross_reference_registry(self, state: FraudState) -> FraudState:
        t = time.time()
        app_id = state["application_id"]
        loan = await self.store.load_stream(f"loan-{app_id}")
        sub = next((e for e in loan if e.event_type == "ApplicationSubmitted"), None)
        if not sub:
            raise ValueError("ApplicationSubmitted missing")
        applicant_id = (sub.payload or {}).get("applicant_id")
        profile = await self.registry.get_company(applicant_id)
        if profile is None:
            raise ValueError(f"Unknown applicant {applicant_id!r}")
        hist = await self.registry.get_financial_history(applicant_id)
        prof = {
            "company_id": profile.company_id,
            "name": profile.name,
            "jurisdiction": profile.jurisdiction,
            "industry": profile.industry,
        }
        hf = [
            {
                "fiscal_year": h.fiscal_year,
                "total_revenue": h.total_revenue,
                "net_income": h.net_income,
            }
            for h in hist
        ]
        ms = int((time.time() - t) * 1000)
        await self._record_tool_call("registry", applicant_id, f"{len(hf)} fy", ms)
        await self._record_node_execution("cross_reference_registry", ["applicant_id"], ["profile"], ms)
        return {**state, "registry_profile": prof, "historical_financials": hf}

    async def _node_analyze_fraud_patterns(self, state: FraudState) -> FraudState:
        t = time.time()
        SYSTEM = """You are a fraud screening assistant. Respond ONLY with JSON:
{"fraud_score": <0-1 float>, "recommendation": "CLEAR"|"FLAG_FOR_REVIEW"|"DECLINE",
 "anomalies": [{"type":"revenue_discrepancy","severity":"LOW","evidence":"...","fields":[]}]}"""
        USER = json.dumps(
            {
                "extracted_facts": state.get("extracted_facts") or {},
                "registry_profile": state.get("registry_profile") or {},
                "historical_financials": state.get("historical_financials") or [],
            },
            default=str,
        )
        try:
            content, ti, to, cost = await self._call_llm(SYSTEM, USER, max_tokens=1024)
            data = self._parse_json(content) or {}
        except Exception:
            data = {}
            ti = to = 0
            cost = 0.0
        score = float(data.get("fraud_score", 0.08))
        score = max(0.0, min(1.0, score))
        rec = str(data.get("recommendation", "CLEAR")).upper()
        anoms = list(data.get("anomalies") or [])
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution(
            "analyze_fraud_patterns",
            ["facts", "registry"],
            ["fraud_score"],
            ms,
            ti,
            to,
            cost,
        )
        return {
            **state,
            "fraud_score": score,
            "recommendation": rec,
            "anomalies": anoms,
        }

    async def _node_write_output(self, state: FraudState) -> FraudState:
        t = time.time()
        app_id = state["application_id"]
        fraud_sid = f"fraud-{app_id}"
        loan_sid = f"loan-{app_id}"
        existing = await self.store.load_stream(fraud_sid)
        has_init = any(e.event_type == "FraudScreeningInitiated" for e in existing)
        has_done = any(e.event_type == "FraudScreeningCompleted" for e in existing)
        if has_done:
            await self._record_output_written([], "FraudScreeningCompleted already present")
            ms = int((time.time() - t) * 1000)
            await self._record_node_execution("write_output", ["fraud_stream"], ["noop"], ms)
            return {**state, "next_agent_triggered": "compliance"}

        events: list[dict] = []
        if not has_init:
            events.append(
                FraudScreeningInitiated(
                    application_id=app_id,
                    session_id=self.session_id,
                    screening_model_version="fraud-v1",
                    initiated_at=datetime.now(timezone.utc),
                ).to_store_dict()
            )
            await self._append_with_retry(fraud_sid, events)
            events = []

        if self._crash_before_complete:
            raise RuntimeError("simulated crash before FraudScreeningCompleted")

        score = float(state.get("fraud_score") or 0.1)
        anomalies = state.get("anomalies") or []
        extra: list[dict] = []
        for a in anomalies:
            if not isinstance(a, dict):
                continue
            an = FraudAnomaly(
                anomaly_type=FraudAnomalyType.REVENUE_DISCREPANCY,
                description=str(a.get("evidence", "anomaly")),
                severity=str(a.get("severity", "LOW")),
                evidence=str(a.get("evidence", "")),
                affected_fields=list(a.get("fields") or []),
            )
            extra.append(
                FraudAnomalyDetected(
                    application_id=app_id,
                    session_id=self.session_id,
                    anomaly=an,
                    detected_at=datetime.now(timezone.utc),
                ).to_store_dict()
            )
        if extra:
            await self._append_with_retry(fraud_sid, extra)

        done = FraudScreeningCompleted(
            application_id=app_id,
            session_id=self.session_id,
            fraud_score=score,
            risk_level="LOW" if score < 0.3 else "MEDIUM",
            anomalies_found=len(extra),
            recommendation=str(state.get("recommendation") or "CLEAR"),
            screening_model_version="fraud-v1",
            input_data_hash=self._sha(state),
            completed_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(fraud_sid, [done])

        loan_evs = await self.store.load_stream(loan_sid)
        if not any(e.event_type == "ComplianceCheckRequested" for e in loan_evs):
            ccr = ComplianceCheckRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                triggered_by_event_id=self.session_id,
                regulation_set_version="2026-Q1",
                rules_to_evaluate=[
                    "REG-001",
                    "REG-002",
                    "REG-003",
                    "REG-004",
                    "REG-005",
                    "REG-006",
                ],
            ).to_store_dict()
            await self._append_with_retry(loan_sid, [ccr])

        await self._record_output_written(
            ["FraudScreeningCompleted", "ComplianceCheckRequested"],
            "Fraud screening complete",
        )
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("write_output", ["fraud", "loan"], ["downstream_compliance"], ms)
        return {**state, "next_agent_triggered": "compliance"}
