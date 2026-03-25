"""
ComplianceAgent — deterministic REG-001 … REG-006 evaluation (no LLM in rule path).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.base_agent import BaseApexAgent
from src.schema.events import (
    ApplicationDeclined,
    ComplianceCheckCompleted,
    ComplianceCheckInitiated,
    ComplianceRuleFailed,
    ComplianceRuleNoted,
    ComplianceRulePassed,
    ComplianceVerdict,
    DecisionRequested,
)

REGULATIONS: dict = {
    "REG-001": {
        "name": "Bank Secrecy Act (BSA) Check",
        "version": "2026-Q1-v1",
        "is_hard_block": False,
        "check": lambda co: not any(
            f.get("flag_type") == "AML_WATCH" and f.get("is_active")
            for f in co.get("compliance_flags", [])
        ),
        "failure_reason": "Active AML Watch flag present. Remediation required.",
        "remediation": "Provide enhanced due diligence documentation within 10 business days.",
    },
    "REG-002": {
        "name": "OFAC Sanctions Screening",
        "version": "2026-Q1-v1",
        "is_hard_block": True,
        "check": lambda co: not any(
            f.get("flag_type") == "SANCTIONS_REVIEW" and f.get("is_active")
            for f in co.get("compliance_flags", [])
        ),
        "failure_reason": "Active OFAC Sanctions Review. Application blocked.",
        "remediation": None,
    },
    "REG-003": {
        "name": "Jurisdiction Lending Eligibility",
        "version": "2026-Q1-v1",
        "is_hard_block": True,
        "check": lambda co: co.get("jurisdiction") != "MT",
        "failure_reason": "Jurisdiction MT not approved for commercial lending at this time.",
        "remediation": None,
    },
    "REG-004": {
        "name": "Legal Entity Type Eligibility",
        "version": "2026-Q1-v1",
        "is_hard_block": False,
        "check": lambda co: not (
            co.get("legal_type") == "Sole Proprietor"
            and (co.get("requested_amount_usd", 0) or 0) > 250_000
        ),
        "failure_reason": "Sole Proprietor loans >$250K require additional documentation.",
        "remediation": "Submit SBA Form 912 and personal financial statement.",
    },
    "REG-005": {
        "name": "Minimum Operating History",
        "version": "2026-Q1-v1",
        "is_hard_block": True,
        "check": lambda co: (datetime.now(timezone.utc).year - int(co.get("founded_year") or datetime.now(timezone.utc).year))
        >= 2,
        "failure_reason": "Business must have at least 2 years of operating history.",
        "remediation": None,
    },
    "REG-006": {
        "name": "CRA Community Reinvestment",
        "version": "2026-Q1-v1",
        "is_hard_block": False,
        "check": lambda co: True,
        "note_type": "CRA_CONSIDERATION",
        "note_text": "Jurisdiction qualifies for Community Reinvestment Act consideration.",
    },
}


class ComplianceState(TypedDict):
    application_id: str
    session_id: str
    agent_id: str
    company_profile: dict | None
    hard_block: bool
    block_rule_id: str | None
    rules_evaluated: int
    rules_passed: int
    rules_failed: int
    rules_noted: int
    errors: list[str]
    output_events_written: list
    next_agent_triggered: str | None


class ComplianceAgent(BaseApexAgent):
    def build_graph(self) -> Any:
        g = StateGraph(ComplianceState)
        for name in (
            "validate_inputs",
            "check_reg001",
            "check_reg002",
            "check_reg003",
            "check_reg004",
            "check_reg005",
            "check_reg006",
            "write_output",
        ):
            g.add_node(name, getattr(self, f"_node_{name}"))
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs", "check_reg001")
        g.add_edge("check_reg001", "check_reg002")
        g.add_conditional_edges("check_reg002", lambda s: "write_output" if s.get("hard_block") else "check_reg003")
        g.add_conditional_edges("check_reg003", lambda s: "write_output" if s.get("hard_block") else "check_reg004")
        g.add_edge("check_reg004", "check_reg005")
        g.add_conditional_edges("check_reg005", lambda s: "write_output" if s.get("hard_block") else "check_reg006")
        g.add_edge("check_reg006", "write_output")
        g.add_edge("write_output", END)
        return g.compile()

    def _initial_state(self, application_id: str) -> ComplianceState:
        return ComplianceState(
            application_id=application_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            company_profile=None,
            hard_block=False,
            block_rule_id=None,
            rules_evaluated=0,
            rules_passed=0,
            rules_failed=0,
            rules_noted=0,
            errors=[],
            output_events_written=[],
            next_agent_triggered=None,
        )

    async def _load_company_profile(self, application_id: str) -> dict:
        loan = await self.store.load_stream(f"loan-{application_id}")
        sub = next((e for e in loan if e.event_type == "ApplicationSubmitted"), None)
        if not sub:
            raise ValueError("ApplicationSubmitted missing")
        applicant_id = (sub.payload or {}).get("applicant_id")
        amt = (sub.payload or {}).get("requested_amount_usd")
        profile = await self.registry.get_company(applicant_id)
        if profile is None:
            raise ValueError(f"Unknown applicant {applicant_id!r}")
        flags = await self.registry.get_compliance_flags(applicant_id)
        return {
            "company_id": profile.company_id,
            "jurisdiction": profile.jurisdiction,
            "legal_type": profile.legal_type,
            "founded_year": profile.founded_year,
            "requested_amount_usd": float(amt) if amt is not None else 0.0,
            "compliance_flags": [
                {"flag_type": f.flag_type, "severity": f.severity, "is_active": f.is_active}
                for f in flags
            ],
        }

    async def _ensure_initiated(self, application_id: str) -> None:
        cstream = f"compliance-{application_id}"
        evs = await self.store.load_stream(cstream)
        if any(e.event_type == "ComplianceCheckInitiated" for e in evs):
            return
        rules = [f"REG-00{i}" for i in range(1, 7)]
        init_ev = ComplianceCheckInitiated(
            application_id=application_id,
            session_id=self.session_id,
            regulation_set_version="2026-Q1",
            rules_to_evaluate=rules,
            initiated_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(cstream, [init_ev])

    async def _emit_rule_pass(self, application_id: str, rule_id: str) -> None:
        meta = REGULATIONS[rule_id]
        ev = ComplianceRulePassed(
            application_id=application_id,
            session_id=self.session_id,
            rule_id=rule_id,
            rule_name=meta["name"],
            rule_version=meta["version"],
            evidence_hash=self._sha({"rule": rule_id, "co": self.session_id}),
            evaluation_notes="ok",
            evaluated_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(f"compliance-{application_id}", [ev])

    async def _emit_rule_failed(self, application_id: str, rule_id: str) -> None:
        meta = REGULATIONS[rule_id]
        ev = ComplianceRuleFailed(
            application_id=application_id,
            session_id=self.session_id,
            rule_id=rule_id,
            rule_name=meta["name"],
            rule_version=meta["version"],
            failure_reason=meta["failure_reason"],
            is_hard_block=bool(meta.get("is_hard_block")),
            remediation_available=meta.get("remediation") is not None,
            remediation_description=meta.get("remediation"),
            evidence_hash=self._sha({"fail": rule_id}),
            evaluated_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(f"compliance-{application_id}", [ev])

    async def _emit_rule_noted(self, application_id: str, rule_id: str) -> None:
        meta = REGULATIONS[rule_id]
        ev = ComplianceRuleNoted(
            application_id=application_id,
            session_id=self.session_id,
            rule_id=rule_id,
            rule_name=meta["name"],
            note_type=meta["note_type"],
            note_text=meta["note_text"],
            evaluated_at=datetime.now(timezone.utc),
        ).to_store_dict()
        await self._append_with_retry(f"compliance-{application_id}", [ev])

    async def _node_validate_inputs(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        loan = await self.store.load_stream(f"loan-{state['application_id']}")
        if not any(e.event_type == "ComplianceCheckRequested" for e in loan):
            raise ValueError("ComplianceCheckRequested required")
        co = await self._load_company_profile(state["application_id"])
        ms = int((time.time() - t) * 1000)
        await self._record_input_validated(["company_profile"], ms)
        await self._record_node_execution("validate_inputs", ["loan_stream"], ["company_profile"], ms)
        return {**state, "company_profile": co}

    async def _eval_rule(self, state: ComplianceState, rule_id: str) -> ComplianceState:
        app_id = state["application_id"]
        co = state["company_profile"] or {}
        meta = REGULATIONS[rule_id]
        await self._ensure_initiated(app_id)
        st = {**state, "rules_evaluated": state["rules_evaluated"] + 1}
        if rule_id == "REG-006":
            await self._emit_rule_noted(app_id, rule_id)
            return {**st, "rules_noted": state["rules_noted"] + 1}
        ok = bool(meta["check"](co))
        if ok:
            await self._emit_rule_pass(app_id, rule_id)
            return {**st, "rules_passed": state["rules_passed"] + 1}
        await self._emit_rule_failed(app_id, rule_id)
        st2 = {**st, "rules_failed": state["rules_failed"] + 1}
        if meta.get("is_hard_block"):
            return {**st2, "hard_block": True, "block_rule_id": rule_id}
        return st2

    async def _node_check_reg001(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        out = await self._eval_rule(state, "REG-001")
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("check_reg001", ["company"], ["reg001"], ms)
        return out

    async def _node_check_reg002(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        out = await self._eval_rule(state, "REG-002")
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("check_reg002", ["company"], ["reg002"], ms)
        return out

    async def _node_check_reg003(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        out = await self._eval_rule(state, "REG-003")
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("check_reg003", ["company"], ["reg003"], ms)
        return out

    async def _node_check_reg004(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        out = await self._eval_rule(state, "REG-004")
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("check_reg004", ["company"], ["reg004"], ms)
        return out

    async def _node_check_reg005(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        out = await self._eval_rule(state, "REG-005")
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("check_reg005", ["company"], ["reg005"], ms)
        return out

    async def _node_check_reg006(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        out = await self._eval_rule(state, "REG-006")
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("check_reg006", ["company"], ["reg006"], ms)
        return out

    async def _node_write_output(self, state: ComplianceState) -> ComplianceState:
        t = time.time()
        app_id = state["application_id"]
        loan_sid = f"loan-{app_id}"
        comp_sid = f"compliance-{app_id}"

        if state.get("hard_block"):
            done = ComplianceCheckCompleted(
                application_id=app_id,
                session_id=self.session_id,
                rules_evaluated=state["rules_evaluated"],
                rules_passed=state["rules_passed"],
                rules_failed=state["rules_failed"],
                rules_noted=state["rules_noted"],
                has_hard_block=True,
                overall_verdict=ComplianceVerdict.BLOCKED,
                completed_at=datetime.now(timezone.utc),
            ).to_store_dict()
            decl = ApplicationDeclined(
                application_id=app_id,
                decline_reasons=[
                    state.get("block_rule_id") or "COMPLIANCE_BLOCK",
                    REGULATIONS.get(state.get("block_rule_id") or "", {}).get("failure_reason", ""),
                ],
                declined_by=f"compliance:{self.agent_id}",
                adverse_action_notice_required=True,
                adverse_action_codes=[state.get("block_rule_id") or "COMPLIANCE"],
                declined_at=datetime.now(timezone.utc),
            ).to_store_dict()
            await self._append_with_retry(comp_sid, [done])
            await self._append_with_retry(loan_sid, [decl])
            await self._record_output_written(
                ["ComplianceCheckCompleted", "ApplicationDeclined"],
                "Hard block — application declined",
            )
        else:
            done = ComplianceCheckCompleted(
                application_id=app_id,
                session_id=self.session_id,
                rules_evaluated=state["rules_evaluated"],
                rules_passed=state["rules_passed"],
                rules_failed=state["rules_failed"],
                rules_noted=state["rules_noted"],
                has_hard_block=False,
                overall_verdict=ComplianceVerdict.CLEAR,
                completed_at=datetime.now(timezone.utc),
            ).to_store_dict()
            dr = DecisionRequested(
                application_id=app_id,
                requested_at=datetime.now(timezone.utc),
                all_analyses_complete=True,
                triggered_by_event_id=self.session_id,
            ).to_store_dict()
            await self._append_with_retry(comp_sid, [done])
            await self._append_with_retry(loan_sid, [dr])
            await self._record_output_written(
                ["ComplianceCheckCompleted", "DecisionRequested"],
                "Clear — decision stage",
            )
        ms = int((time.time() - t) * 1000)
        await self._record_node_execution("write_output", ["compliance", "loan"], ["terminal"], ms)
        return {**state, "next_agent_triggered": "orchestrator" if not state.get("hard_block") else None}
