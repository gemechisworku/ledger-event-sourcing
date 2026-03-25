"""Shared natural-language query loop (tools + LLM) for /v1/query and persisted chats."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.api.schemas import NLQueryResponse
from src.integrity.audit_chain import run_integrity_check
from src.llm_client import chat_completion_with_tools, get_model
from src.projections import ComplianceAuditProjection

NL_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_decision_history",
            "description": "Retrieve the complete decision history for a loan application, including all events across loan, credit, fraud, compliance, and document streams, plus integrity verification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {"type": "string", "description": "The application ID (e.g. APEX-0001)"},
                },
                "required": ["application_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_compliance_at",
            "description": "Query the compliance state of an application at a specific point in time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {"type": "string"},
                    "as_of": {"type": "string", "description": "ISO-8601 timestamp to query compliance state at."},
                },
                "required": ["application_id", "as_of"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_application_summary",
            "description": "Get the current summary/state of a loan application from the projection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {"type": "string"},
                },
                "required": ["application_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_integrity_check",
            "description": "Verify the cryptographic integrity of the event chain for an application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {"type": "string"},
                },
                "required": ["application_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_applications",
            "description": "List all applications in the system with their current status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max rows to return", "default": 20},
                },
            },
        },
    },
]

NL_SYSTEM = """You are the Apex Ledger assistant. You answer questions about loan applications in the event-sourced ledger system.

You have tools to query application data. When the user asks about decision history, compliance, integrity, or application status, call the appropriate tool, then synthesize a clear, well-structured answer.

Rules:
- Always cite stream IDs and event types when describing history.
- When showing decision history, list events chronologically with stream, type, and key payload fields.
- For compliance queries, show individual rule results.
- For integrity checks, report chain validity and any tampering detected.
- Format monetary values with dollar signs and commas.
- Be concise but thorough. Use bullet points for event lists."""


async def execute_nl_tool(name: str, args: dict, store: Any) -> str:
    if name == "get_decision_history":
        app_id = args["application_id"]
        stream_prefixes = ["loan", "credit", "fraud", "compliance", "docpkg"]
        all_events = []
        for prefix in stream_prefixes:
            sid = f"{prefix}-{app_id}"
            evs = await store.load_stream(sid)
            for e in evs:
                payload = e.payload if isinstance(e.payload, dict) else dict(e.payload or {})
                all_events.append({
                    "stream_id": sid,
                    "event_type": e.event_type,
                    "stream_position": e.stream_position,
                    "global_position": getattr(e, "global_position", None),
                    "recorded_at": str(e.recorded_at) if e.recorded_at else None,
                    "payload": payload,
                })
        all_events.sort(key=lambda e: e.get("global_position") or 0)
        integrity = None
        try:
            r = await run_integrity_check(store, "loan", app_id)
            integrity = {
                "chain_valid": r.chain_valid,
                "tamper_detected": r.tamper_detected,
                "events_verified": r.events_verified,
            }
        except Exception:
            pass
        return json.dumps({"total_events": len(all_events), "events": all_events, "integrity": integrity}, default=str)

    if name == "get_compliance_at":
        app_id = args["application_id"]
        as_of = datetime.fromisoformat(args["as_of"].replace("Z", "+00:00"))
        proj = ComplianceAuditProjection(store)
        result = await proj.get_compliance_at(app_id, as_of)
        return json.dumps(result, default=str)

    if name == "get_application_summary":
        app_id = args["application_id"]
        pool = getattr(store, "_pool", None) or getattr(store, "pool", None)
        if pool is None:
            loan = await store.load_stream(f"loan-{app_id}")
            return json.dumps({"event_count": len(loan), "events": [e.event_type for e in loan]})
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM projection_application_summary WHERE application_id = $1", app_id
            )
        if not row:
            return json.dumps({"error": "Application not found in summary projection"})
        return json.dumps(dict(row), default=str)

    if name == "run_integrity_check":
        app_id = args["application_id"]
        r = await run_integrity_check(store, "loan", app_id)
        return json.dumps({
            "chain_valid": r.chain_valid,
            "tamper_detected": r.tamper_detected,
            "events_verified": r.events_verified,
        })

    if name == "list_applications":
        limit = args.get("limit", 20)
        pool = getattr(store, "_pool", None) or getattr(store, "pool", None)
        if pool is None:
            return json.dumps({"note": "In-memory store — no projection index available"})
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT application_id, state, applicant_id, decision, risk_tier, fraud_score "
                "FROM projection_application_summary ORDER BY updated_at DESC NULLS LAST LIMIT $1",
                limit,
            )
        return json.dumps([dict(r) for r in rows], default=str)

    return json.dumps({"error": f"Unknown tool: {name}"})


async def run_natural_language_query(
    store: Any,
    llm_client: Any,
    messages: list[dict[str, Any]],
    *,
    max_iterations: int = 5,
) -> NLQueryResponse:
    """
    Run one user turn. `messages` must include the latest user message as the last entry
    (role user). May include prior user/assistant pairs for context; tool messages appended in-loop.
    """
    total_tokens = 0
    working = list(messages)

    for _ in range(max_iterations):
        resp = await chat_completion_with_tools(
            llm_client,
            system=NL_SYSTEM,
            messages=working,
            tools=NL_TOOLS,
            max_tokens=2048,
        )
        choice = resp.choices[0]
        msg = choice.message
        if resp.usage:
            total_tokens += (resp.usage.prompt_tokens or 0) + (resp.usage.completion_tokens or 0)

        if msg.tool_calls:
            working.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]})
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
                result = await execute_nl_tool(fn_name, fn_args, store)
                working.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            return NLQueryResponse(
                answer=msg.content or "No answer generated.",
                sources=[],
                model=get_model(),
                tokens_used=total_tokens,
            )

    return NLQueryResponse(
        answer="Query processing reached the maximum iteration limit.",
        model=get_model(),
        tokens_used=total_tokens,
    )
