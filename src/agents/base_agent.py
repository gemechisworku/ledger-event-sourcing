"""
src/agents/base_agent.py
===========================
BASE LANGGRAPH AGENT for Apex agents (implemented in sibling modules).
See `src/agents/credit_analysis_agent.py` for the reference CreditAnalysisAgent.
"""
from __future__ import annotations
import asyncio, hashlib, json, re, time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import uuid4
from anthropic import AsyncAnthropic
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

    async def process_application(self, application_id: str, prior_session_id: str | None = None) -> None:
        if not self._graph: self._graph = self.build_graph()
        self.application_id = application_id
        self.session_id = f"sess-{self.agent_type[:3]}-{uuid4().hex[:8]}"
        self._prior_session_id = prior_session_id
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
        prior = getattr(self, "_prior_session_id", None)
        ctx = f"prior_session_replay:{prior}" if prior else "fresh"
        tok = 2500 if prior else 1000
        await self._append_session({"event_type":"AgentSessionStarted","event_version":1,"payload":{
            "session_id":self.session_id,"agent_type":self.agent_type,"agent_id":self.agent_id,
            "application_id":app_id,"model_version":self.model,"langgraph_graph_version":LANGGRAPH_VERSION,
            "context_source":ctx,"context_token_count":tok,"started_at":datetime.now().isoformat()}})

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


__all__ = [
    "BaseApexAgent",
    "LANGGRAPH_VERSION",
    "MAX_OCC_RETRIES",
]
