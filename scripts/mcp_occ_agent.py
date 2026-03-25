#!/usr/bin/env python3
"""
Single MCP call: record_credit_analysis (same tool Cursor uses).

Two terminals run this at the same time with different session ids (sess-a vs sess-b).
Both append the first CreditAnalysisCompleted on the same credit stream → one wins OCC, one gets OptimisticConcurrencyError.

Prereqs: run_mcp_http.py + mcp_occ_setup.py

  uv run python scripts/mcp_occ_agent.py sess-a
  uv run python scripts/mcp_occ_agent.py sess-b
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8765/mcp")
APP_ID = os.environ.get("OCC_APP_ID", "OCC-MCP-RACE-001")


def _parse_tool_result(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"message": text}


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/mcp_occ_agent.py <sess-a|sess-b>", file=sys.stderr)
        sys.exit(1)
    session_id = sys.argv[1]

    from fastmcp import Client

    async with Client(MCP_URL) as client:
        r = await client.call_tool_mcp(
            "record_credit_analysis",
            {
                "application_id": APP_ID,
                "session_id": session_id,
                "model_version": "mv-1",
                "risk_tier": "MEDIUM",
                "recommended_limit_usd": "90000",
                "confidence": 0.75,
                "rationale": f"Concurrent credit completion from {session_id}",
            },
        )

    if r.structuredContent:
        out = dict(r.structuredContent)
    else:
        text = ""
        for c in r.content:
            if getattr(c, "text", None):
                text += c.text
        out = _parse_tool_result(text) if text else {"empty": True}

    print(f"[{session_id}] MCP record_credit_analysis →")
    print(json.dumps(out, indent=2, default=str))

    if isinstance(out, dict):
        if out.get("error_type") == "OptimisticConcurrencyError":
            print(f"\n>>> Expected: loser saw OptimisticConcurrencyError (expected_version={out.get('expected_version')}, actual_version={out.get('actual_version')})")
        elif out.get("ok") is True:
            print("\n>>> Expected: winner appended first CreditAnalysisCompleted")
        elif out.get("error_type") == "DomainError":
            print(f"\n>>> DomainError (often the second runner after OCC already resolved): {out.get('message')}")


if __name__ == "__main__":
    asyncio.run(main())
