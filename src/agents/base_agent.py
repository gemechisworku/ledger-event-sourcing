"""
src/agents/base_agent.py
===========================
BASE LANGGRAPH AGENT + all 5 agent class stubs.
See `src/agents/credit_analysis_agent.py` for the reference CreditAnalysisAgent.
The other 4 agents are stubs with complete docstrings for implementation.
"""
from __future__ import annotations
import asyncio, hashlib, json, re, time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import uuid4
from anthropic import AsyncAnthropic
from langgraph.graph import StateGraph, END

from src.event_store import OptimisticConcurrencyError
from src.schema.events import AgentInputValidated, AgentInputValidationFailed, AgentType

LANGGRAPH_VERSION = "1.0.0"
MAX_OCC_RETRIES = 5

class BaseApexAgent(ABC):
    """
    Base for all 5 Apex agents. Provides Gas Town session management,
    per-node event recording, tool call recording, OCC retry scaffolding.

    AGENT NODE SEQUENCE (all agents follow this):
        start_session → validate_inputs → load_context → [domain nodes] → write_output → end_session

    Each node must call self._record_node_execution() at its end.
    Each tool/registry call must call self._record_tool_call().
    The write_output node must call self._record_output_written() then self._record_node_execution().
    """
    def __init__(self, agent_id: str, agent_type: str, store, registry, client: AsyncAnthropic, model="claude-sonnet-4-20250514"):
        self.agent_id = agent_id; self.agent_type = agent_type
        self.store = store; self.registry = registry; self.client = client; self.model = model
        self.session_id = None; self.application_id = None
        self._session_stream = None; self._t0 = None
        self._seq = 0; self._llm_calls = 0; self._tokens = 0; self._cost = 0.0
        self._graph = None

    @abstractmethod
    def build_graph(self): raise NotImplementedError

    async def process_application(self, application_id: str) -> None:
        if not self._graph: self._graph = self.build_graph()
        self.application_id = application_id
        self.session_id = f"sess-{self.agent_type[:3]}-{uuid4().hex[:8]}"
        self._session_stream = f"agent-{self.agent_type}-{self.session_id}"
        self._t0 = time.time(); self._seq = 0; self._llm_calls = 0; self._tokens = 0; self._cost = 0.0
        await self._start_session(application_id)
        try:
            result = await self._graph.ainvoke(self._initial_state(application_id))
            await self._complete_session(result)
        except Exception as e:
            await self._fail_session(type(e).__name__, str(e)); raise

    def _initial_state(self, app_id):
        return {"application_id": app_id, "session_id": self.session_id,
                "agent_id": self.agent_id, "errors": [], "output_events_written": [], "next_agent_triggered": None}

    async def _start_session(self, app_id):
        await self._append_session({"event_type":"AgentSessionStarted","event_version":1,"payload":{
            "session_id":self.session_id,"agent_type":self.agent_type,"agent_id":self.agent_id,
            "application_id":app_id,"model_version":self.model,"langgraph_graph_version":LANGGRAPH_VERSION,
            "context_source":"fresh","context_token_count":1000,"started_at":datetime.now().isoformat()}})

    async def _record_node_execution(self, name, in_keys, out_keys, ms, tok_in=None, tok_out=None, cost=None):
        self._seq += 1
        if tok_in: self._tokens += tok_in + (tok_out or 0); self._llm_calls += 1
        if cost: self._cost += cost
        await self._append_session({"event_type":"AgentNodeExecuted","event_version":1,"payload":{
            "session_id":self.session_id,"agent_type":self.agent_type,"node_name":name,
            "node_sequence":self._seq,"input_keys":in_keys,"output_keys":out_keys,
            "llm_called":tok_in is not None,"llm_tokens_input":tok_in,"llm_tokens_output":tok_out,
            "llm_cost_usd":cost,"duration_ms":ms,"executed_at":datetime.now().isoformat()}})

    async def _record_tool_call(self, tool, inp, out, ms):
        await self._append_session({"event_type":"AgentToolCalled","event_version":1,"payload":{
            "session_id":self.session_id,"agent_type":self.agent_type,"tool_name":tool,
            "tool_input_summary":inp,"tool_output_summary":out,"tool_duration_ms":ms,
            "called_at":datetime.now().isoformat()}})

    async def _record_output_written(self, events_written, summary):
        await self._append_session({"event_type":"AgentOutputWritten","event_version":1,"payload":{
            "session_id":self.session_id,"agent_type":self.agent_type,"application_id":self.application_id,
            "events_written":events_written,"output_summary":summary,"written_at":datetime.now().isoformat()}})

    async def _complete_session(self, result):
        ms = int((time.time()-self._t0)*1000)
        next_tr = result.get("next_agent_triggered")
        if next_tr is None:
            next_tr = result.get("next_agent")
        await self._append_session({"event_type":"AgentSessionCompleted","event_version":1,"payload":{
            "session_id":self.session_id,"agent_type":self.agent_type,"application_id":self.application_id,
            "total_nodes_executed":self._seq,"total_llm_calls":self._llm_calls,"total_tokens_used":self._tokens,
            "total_cost_usd":round(self._cost,6),"total_duration_ms":ms,
            "next_agent_triggered":next_tr,"completed_at":datetime.now().isoformat()}})

    async def _fail_session(self, etype, emsg):
        await self._append_session({"event_type":"AgentSessionFailed","event_version":1,"payload":{
            "session_id":self.session_id,"agent_type":self.agent_type,"application_id":self.application_id,
            "error_type":etype,"error_message":emsg[:500],"last_successful_node":f"node_{self._seq}",
            "recoverable":etype in ("llm_timeout","RateLimitError"),"failed_at":datetime.now().isoformat()}})

    def _agent_type_enum(self) -> AgentType:
        if isinstance(self.agent_type, AgentType):
            return self.agent_type
        return AgentType(self.agent_type)

    async def _append_session(self, event: dict) -> None:
        assert self._session_stream is not None
        await self._append_with_retry(self._session_stream, [event])

    async def _record_input_validated(self, inputs_validated: list[str], duration_ms: int) -> None:
        ev = AgentInputValidated(
            session_id=self.session_id,
            agent_type=self._agent_type_enum(),
            application_id=self.application_id,
            inputs_validated=inputs_validated,
            validation_duration_ms=duration_ms,
            validated_at=datetime.now(timezone.utc),
        )
        await self._append_session(ev.to_store_dict())

    async def _record_input_failed(self, missing_inputs: list[str], validation_errors: list[str]) -> None:
        ev = AgentInputValidationFailed(
            session_id=self.session_id,
            agent_type=self._agent_type_enum(),
            application_id=self.application_id,
            missing_inputs=missing_inputs,
            validation_errors=validation_errors,
            failed_at=datetime.now(timezone.utc),
        )
        await self._append_session(ev.to_store_dict())

    async def _append_with_retry(
        self,
        stream_id: str,
        events: list[dict],
        causation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> list[int]:
        """Append one or more events with OCC retry (reload version on conflict)."""
        if not events:
            return []
        for attempt in range(MAX_OCC_RETRIES):
            try:
                ver = await self.store.stream_version(stream_id)
                return await self.store.append(
                    stream_id,
                    events,
                    expected_version=ver,
                    causation_id=causation_id,
                    correlation_id=correlation_id,
                )
            except OptimisticConcurrencyError:
                if attempt >= MAX_OCC_RETRIES - 1:
                    raise
                await asyncio.sleep(0.05 * (2**attempt))

    async def _append_stream(self, stream_id: str, event_dict: dict, causation_id: str = None):
        """Append a single event with OCC retry."""
        await self._append_with_retry(stream_id, [event_dict], causation_id=causation_id)

    @staticmethod
    def _parse_json(text: str) -> dict:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {}
        return json.loads(m.group())

    async def _call_llm(self, system, user, max_tokens=1024):
        resp = await self.client.messages.create(model=self.model, max_tokens=max_tokens,
            system=system, messages=[{"role":"user","content":user}])
        t = resp.content[0].text; i = resp.usage.input_tokens; o = resp.usage.output_tokens
        return t, i, o, round(i/1e6*3.0 + o/1e6*15.0, 6)

    @staticmethod
    def _sha(d): return hashlib.sha256(json.dumps(str(d),sort_keys=True).encode()).hexdigest()[:16]


class DocumentProcessingAgent(BaseApexAgent):
    """
    Wraps the Week 3 Document Intelligence pipeline as a LangGraph agent.

    NODES TO IMPLEMENT:
        validate_inputs → validate_document_format → run_week3_extraction
        → assess_quality (LLM) → write_output

    WEEK 3 INTEGRATION — in _node_run_week3_extraction:
        from document_refinery.pipeline import extract_financial_facts
        for each doc in package:
            append ExtractionStarted to docpkg stream
            facts = await extract_financial_facts(file_path, document_type)
            append ExtractionCompleted(facts=facts) to docpkg stream

    LLM ROLE — in _node_assess_quality:
        System prompt: "You are a financial document quality analyst.
        Check extracted facts for internal consistency. Do NOT make credit decisions.
        Return DocumentQualityAssessment JSON."
        Specifically check: balance_sheet_balances, EBITDA plausibility,
        margin ranges for industry, critical missing fields.

    OUTPUT STREAMS:
        docpkg-{id}: DocumentFormatValidated, ExtractionStarted, ExtractionCompleted,
                     QualityAssessmentCompleted, PackageReadyForAnalysis
        loan-{id}: CreditAnalysisRequested
    """
    def build_graph(self):
        from typing import TypedDict
        class S(TypedDict):
            application_id: str; session_id: str; agent_id: str
            document_ids: list | None; extracted_facts_by_doc: dict | None
            quality_assessment: dict | None; has_critical_issues: bool | None
            errors: list; output_events_written: list; next_agent_triggered: str | None
        g = StateGraph(S)
        g.add_node("validate_inputs",         self._node_validate_inputs)
        g.add_node("validate_document_format",self._node_validate_format)
        g.add_node("run_week3_extraction",     self._node_extract)
        g.add_node("assess_quality",           self._node_assess_quality)
        g.add_node("write_output",             self._node_write_output)
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs","validate_document_format")
        g.add_edge("validate_document_format","run_week3_extraction")
        g.add_edge("run_week3_extraction","assess_quality")
        g.add_edge("assess_quality","write_output")
        g.add_edge("write_output", END)
        return g.compile()

    async def _node_validate_inputs(self, state):
        raise NotImplementedError("Implement _node_validate_inputs: verify DocumentUploaded events exist on loan stream")
    async def _node_validate_format(self, state):
        raise NotImplementedError("Implement _node_validate_format: check PDF/XLSX format, append DocumentFormatValidated or Rejected")
    async def _node_extract(self, state):
        raise NotImplementedError("Implement _node_extract: call Week 3 pipeline per document, append ExtractionStarted + ExtractionCompleted")
    async def _node_assess_quality(self, state):
        raise NotImplementedError("Implement _node_assess_quality: LLM coherence check, append QualityAssessmentCompleted")
    async def _node_write_output(self, state):
        raise NotImplementedError("Implement _node_write_output: append PackageReadyForAnalysis, trigger CreditAnalysisRequested")


class FraudDetectionAgent(BaseApexAgent):
    """
    Detects inconsistencies between submitted documents and registry history.

    NODES TO IMPLEMENT:
        validate_inputs → load_document_facts → cross_reference_registry
        → analyze_fraud_patterns (LLM) → write_output

    LLM ROLE — in _node_analyze_fraud_patterns:
        Compare extracted current-year facts against historical_financials from registry.
        Flag: revenue_discrepancy (> 50% unexplained gap year-on-year),
              balance_sheet_inconsistency, unusual_submission_pattern.
        Compute fraud_score as weighted sum of anomaly severities.
        Return FraudAssessment JSON with named anomalies.
        RULE: fraud_score > 0.3 → must include at least one named anomaly with evidence.

    OUTPUT STREAMS:
        fraud-{id}: FraudScreeningInitiated, FraudAnomalyDetected (0+), FraudScreeningCompleted
        loan-{id}: ComplianceCheckRequested
    """
    def build_graph(self):
        from typing import TypedDict
        class S(TypedDict):
            application_id: str; session_id: str; agent_id: str
            extracted_facts: dict | None; historical_financials: list | None
            company_profile: dict | None; fraud_assessment: dict | None
            errors: list; output_events_written: list; next_agent_triggered: str | None
        g = StateGraph(S)
        for name in ["validate_inputs","load_document_facts","cross_reference_registry","analyze_fraud_patterns","write_output"]:
            g.add_node(name, getattr(self, f"_node_{name}"))
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs","load_document_facts")
        g.add_edge("load_document_facts","cross_reference_registry")
        g.add_edge("cross_reference_registry","analyze_fraud_patterns")
        g.add_edge("analyze_fraud_patterns","write_output")
        g.add_edge("write_output",END)
        return g.compile()

    async def _node_validate_inputs(self, state): raise NotImplementedError("verify FraudScreeningRequested event exists on loan stream")
    async def _node_load_document_facts(self, state): raise NotImplementedError("load ExtractionCompleted events from docpkg stream")
    async def _node_cross_reference_registry(self, state): raise NotImplementedError("query registry: get_company + get_financial_history")
    async def _node_analyze_fraud_patterns(self, state): raise NotImplementedError("LLM: compare extracted facts vs registry history, compute fraud_score")
    async def _node_write_output(self, state): raise NotImplementedError("append FraudScreeningCompleted, trigger ComplianceCheckRequested")


class ComplianceAgent(BaseApexAgent):
    """
    Evaluates 6 deterministic regulatory rules. No LLM in decision path.

    NODES (6 rule nodes + bookend nodes):
        validate_inputs → check_reg001 → check_reg002 → check_reg003
        → check_reg004 → check_reg005 → check_reg006 → write_output

    Use conditional edges after each hard-block rule:
        graph.add_conditional_edges("check_reg002", self._should_continue,
                                     {"continue":"check_reg003","hard_block":"write_output"})

    RULE IMPLEMENTATIONS (deterministic — no LLM):
        REG-001: not any AML_WATCH flag is_active  → ComplianceRulePassed/Failed
        REG-002: not any SANCTIONS_REVIEW is_active → hard_block=True if failed
        REG-003: jurisdiction != "MT"               → hard_block=True if failed
        REG-004: not (Sole Proprietor AND >$250K)   → remediation_available=True if failed
        REG-005: founded_year <= 2022               → hard_block=True if failed
        REG-006: Always passes → ComplianceRuleNoted(CRA_CONSIDERATION)

    OUTPUT STREAMS:
        compliance-{id}: ComplianceCheckInitiated, ComplianceRulePassed/Failed/Noted (6x), ComplianceCheckCompleted
        loan-{id}: DecisionRequested (if CLEAR/CONDITIONAL) OR ApplicationDeclined (if BLOCKED)
    """
    def build_graph(self):
        from typing import TypedDict
        class S(TypedDict):
            application_id: str; session_id: str; agent_id: str
            company_profile: dict | None; rules_results: list | None
            hard_block: bool | None; overall_verdict: str | None
            errors: list; output_events_written: list; next_agent_triggered: str | None
        g = StateGraph(S)
        for name in ["validate_inputs","check_reg001","check_reg002","check_reg003","check_reg004","check_reg005","check_reg006","write_output"]:
            g.add_node(name, getattr(self, f"_node_{name}"))
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs","check_reg001")
        g.add_edge("check_reg001","check_reg002")
        # REG-002 and REG-003 are hard blocks: conditional edge to write_output if failed
        g.add_conditional_edges("check_reg002", lambda s: "write_output" if s.get("hard_block") else "check_reg003")
        g.add_conditional_edges("check_reg003", lambda s: "write_output" if s.get("hard_block") else "check_reg004")
        g.add_edge("check_reg004","check_reg005")
        g.add_conditional_edges("check_reg005", lambda s: "write_output" if s.get("hard_block") else "check_reg006")
        g.add_edge("check_reg006","write_output")
        g.add_edge("write_output",END)
        return g.compile()

    async def _node_validate_inputs(self, state): raise NotImplementedError("load company profile from registry, verify ComplianceCheckRequested event")
    async def _node_check_reg001(self, state): raise NotImplementedError("BSA: check AML_WATCH flags, append ComplianceRulePassed/Failed")
    async def _node_check_reg002(self, state): raise NotImplementedError("OFAC: check SANCTIONS_REVIEW flags, hard_block=True if failed")
    async def _node_check_reg003(self, state): raise NotImplementedError("Jurisdiction: jurisdiction != 'MT', hard_block=True if failed")
    async def _node_check_reg004(self, state): raise NotImplementedError("Legal type: Sole Proprietor + >250K → failed, remediation_available=True")
    async def _node_check_reg005(self, state): raise NotImplementedError("Operating history: founded_year <= 2022, hard_block=True if failed")
    async def _node_check_reg006(self, state): raise NotImplementedError("CRA: always passes, append ComplianceRuleNoted")
    async def _node_write_output(self, state): raise NotImplementedError("append ComplianceCheckCompleted, then DecisionRequested or ApplicationDeclined")


class DecisionOrchestratorAgent(BaseApexAgent):
    """
    Synthesises all prior agent outputs. Reads from ALL prior agent streams.

    NODES:
        validate_inputs → load_all_analyses → synthesize_decision (LLM)
        → apply_hard_constraints → write_output

    READS FROM:
        credit-{id}: CreditAnalysisCompleted (risk_tier, confidence, limit)
        fraud-{id}: FraudScreeningCompleted (fraud_score, anomalies)
        compliance-{id}: ComplianceCheckCompleted (overall_verdict)

    HARD CONSTRAINTS (Python — not LLM, in apply_hard_constraints):
        1. compliance BLOCKED → must DECLINE regardless of LLM
        2. confidence < 0.60 → must REFER
        3. fraud_score > 0.60 → must REFER
        4. risk_tier HIGH AND confidence >= 0.70 → DECLINE eligible

    LLM ROLE (synthesize_decision):
        Given all 3 analyses, produce executive_summary and key_risks.
        Initial recommendation (may be overridden by hard constraints).
        Return OrchestratorDecision JSON.

    OUTPUT STREAMS:
        loan-{id}: DecisionGenerated
        loan-{id}: ApplicationApproved (if APPROVE) OR ApplicationDeclined (if DECLINE)
                   OR HumanReviewRequested (if REFER)
    """
    def build_graph(self):
        from typing import TypedDict
        class S(TypedDict):
            application_id: str; session_id: str; agent_id: str
            credit_analysis: dict | None; fraud_screening: dict | None
            compliance_record: dict | None; orchestrator_decision: dict | None
            errors: list; output_events_written: list; next_agent_triggered: str | None
        g = StateGraph(S)
        for name in ["validate_inputs","load_all_analyses","synthesize_decision","apply_hard_constraints","write_output"]:
            g.add_node(name, getattr(self, f"_node_{name}"))
        g.set_entry_point("validate_inputs")
        g.add_edge("validate_inputs","load_all_analyses")
        g.add_edge("load_all_analyses","synthesize_decision")
        g.add_edge("synthesize_decision","apply_hard_constraints")
        g.add_edge("apply_hard_constraints","write_output")
        g.add_edge("write_output",END)
        return g.compile()

    async def _node_validate_inputs(self, state): raise NotImplementedError("verify DecisionRequested event, all 3 analysis streams complete")
    async def _node_load_all_analyses(self, state): raise NotImplementedError("load credit, fraud, compliance streams; extract latest completed events")
    async def _node_synthesize_decision(self, state): raise NotImplementedError("LLM: synthesize all 3 inputs into recommendation + executive_summary")
    async def _node_apply_hard_constraints(self, state): raise NotImplementedError("Python rules: compliance BLOCKED→DECLINE, confidence<0.6→REFER, fraud>0.6→REFER")
    async def _node_write_output(self, state): raise NotImplementedError("append DecisionGenerated + ApplicationApproved/Declined/HumanReviewRequested")
