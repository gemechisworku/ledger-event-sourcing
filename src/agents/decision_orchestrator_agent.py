"""
DecisionOrchestratorAgent — reads prior agent streams, emits DecisionGenerated + HumanReviewRequested.
"""
from __future__ import annotations

import json
import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.base_agent import BaseApexAgent
from src.domain.handlers import handle_decision_generated, handle_human_review_requested


class OrchState(TypedDict):
    application_id: str
    session_id: str
    agent_id: str
    credit_session_id: str | None
    credit_analysis: dict | None
    fraud_screening: dict | None
    compliance: dict | None
    executive_summary: str | None
    final_recommendation: str | None
    final_confidence: float | None
    errors: list[str]
    output_events_written: list
    next_agent_triggered: str | None


class DecisionOrchestratorAgent(BaseApexAgent):
    async def process_application(self, application_id: str, prior_session_id: str | None = None) -> None:
        loan = await self.store.load_stream(f"loan-{application_id}")
        if any(e.event_type == "DecisionGenerated" for e in loan):
            return
        await super().process_application(application_id, prior_session_id=prior_session_id)

    def build_graph(self) -> Any:
        g = StateGraph(OrchState)
        for name in (
            "validate_inputs",
            "load_all_analyses",
            "synthesize_decision",
            "apply_hard_constraints",
            "write_output",
        ):
            g.add_node(name, getattr(self, f"_node_{name}"))
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs", "load_all_analyses")
        g.add_edge("load_all_analyses", "synthesize_decision")
        g.add_edge("synthesize_decision", "apply_hard_constraints")
        g.add_edge("apply_hard_constraints", "write_output")
        g.add_edge("write_output", END)
        return g.compile()

    def _initial_state(self, application_id: str) -> OrchState:
        return OrchState(
            application_id=application_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            credit_session_id=None,
            credit_analysis=None,
            fraud_screening=None,
            compliance=None,
            executive_summary=None,
            final_recommendation=None,
            final_confidence=None,
            errors=[],
            output_events_written=[],
            next_agent_triggered=None,
        )

    async def _node_validate_inputs(self, state: OrchState) -> OrchState:
        t = time.time()
        loan = await self.store.load_stream(f"loan-{state['application_id']}")
        if not any(e.event_type == "DecisionRequested" for e in loan):
            raise ValueError("DecisionRequested required before orchestration")
        ms = int((time.time() - t) * 1000)
        await self._record_input_validated(["application_id"], ms)
        await self._record_node_execution("validate_inputs", ["loan_stream"], ["ok"], ms)
        return state

    async def _node_load_all_analyses(self, state: OrchState) -> OrchState:
        t = time.time()
        app_id = state["application_id"]
        credit_evs = await self.store.load_stream(f"credit-{app_id}")
        fraud_evs = await self.store.load_stream(f"fraud-{app_id}")
        comp_evs = await self.store.load_stream(f"compliance-{app_id}")

        credit_payload = None
        credit_sid = None
        for e in credit_evs:
            if e.event_type == "CreditAnalysisCompleted":
                credit_payload = e.payload
                credit_sid = (e.payload or {}).get("session_id")

        fraud_payload = None
        for e in fraud_evs:
            if e.event_type == "FraudScreeningCompleted":
                fraud_payload = e.payload

        comp_payload = None
        for e in comp_evs:
            if e.event_type == "ComplianceCheckCompleted":
                comp_payload = e.payload

        ms = int((time.time() - t) * 1000)
        await self._record_tool_call(
            "load_streams",
            "credit,fraud,compliance",
            "latest completed",
            ms,
        )
        await self._record_node_execution(
            "load_all_analyses",
            ["streams"],
            ["credit", "fraud", "compliance"],
            ms,
        )
        return {
            **state,
            "credit_session_id": credit_sid,
            "credit_analysis": credit_payload,
            "fraud_screening": fraud_payload,
            "compliance": comp_payload,
        }

    async def _node_synthesize_decision(self, state: OrchState) -> OrchState:
        t = time.time()
        SYSTEM = """You are a loan orchestrator. Output ONLY JSON:
{"recommendation":"APPROVE"|"DECLINE"|"REFER","confidence":0.0-1.0,"executive_summary":"<short>"}"""
        USER = json.dumps(
            {
                "credit": state.get("credit_analysis"),
                "fraud": state.get("fraud_screening"),
                "compliance": state.get("compliance"),
            },
            default=str,
        )
        content, ti, to, cost = await self._call_llm(SYSTEM, USER, max_tokens=512)
        data = self._parse_json(content) or {}
        rec = str(data.get("recommendation", "DECLINE")).upper()
        conf = float(data.get("confidence", 0.72))
        summ = str(data.get("executive_summary", "Orchestrator synthesis."))
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution(
            "synthesize_decision",
            ["analyses"],
            ["recommendation"],
            ms,
            ti,
            to,
            cost,
        )
        return {
            **state,
            "final_recommendation": rec,
            "final_confidence": conf,
            "executive_summary": summ,
        }

    async def _node_apply_hard_constraints(self, state: OrchState) -> OrchState:
        t = time.time()
        comp = state.get("compliance") or {}
        verdict = str(comp.get("overall_verdict") or "").upper()
        rec = str(state.get("final_recommendation") or "DECLINE").upper()
        conf = float(state.get("final_confidence") or 0.5)
        fraud = state.get("fraud_screening") or {}
        fscore = float(fraud.get("fraud_score") or 0.0)

        if verdict == "BLOCKED":
            rec = "DECLINE"
        if conf < 0.60:
            rec = "REFER"
        if fscore > 0.60:
            rec = "REFER"
        if rec == "REFER":
            conf = max(conf, 0.60)

        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("apply_hard_constraints", ["draft"], ["final"], ms)
        return {**state, "final_recommendation": rec, "final_confidence": conf}

    async def _node_write_output(self, state: OrchState) -> OrchState:
        t = time.time()
        app_id = state["application_id"]
        credit_sid = state.get("credit_session_id")
        if not credit_sid:
            raise ValueError("Credit session id missing (CreditAnalysisCompleted required)")

        rec = str(state.get("final_recommendation") or "DECLINE").upper()
        conf = float(state.get("final_confidence") or 0.7)
        summ = str(state.get("executive_summary") or "")
        await handle_decision_generated(
            self.store,
            application_id=app_id,
            orchestrator_session_id=self.session_id,
            recommendation=rec,
            confidence=max(conf, 0.60),
            contributing_sessions=[credit_sid],
            executive_summary=summ,
        )

        loan_evs = await self.store.load_stream(f"loan-{app_id}")
        last_dec = None
        for e in reversed(loan_evs):
            if e.event_type == "DecisionGenerated":
                last_dec = e
                break
        if not last_dec:
            raise RuntimeError("DecisionGenerated not found after handler")
        eid = str(last_dec.event_id)

        if rec == "DECLINE":
            await handle_human_review_requested(
                self.store,
                application_id=app_id,
                reason="Mandatory human review after orchestrator DECLINE",
                decision_event_id=eid,
            )

        await self._record_output_written(
            ["DecisionGenerated"] + (["HumanReviewRequested"] if rec == "DECLINE" else []),
            "Orchestrator output",
        )
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("write_output", ["loan"], ["decision"], ms)
        return {**state, "next_agent_triggered": "human_review" if rec == "DECLINE" else None}
