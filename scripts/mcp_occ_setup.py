#!/usr/bin/env python3
"""
One-time setup (same MCP tools as Cursor): submit app + two credit agent sessions.

Run AFTER scripts/run_mcp_http.py is listening.

  uv run python scripts/mcp_occ_setup.py

Env:
  MCP_URL — default http://127.0.0.1:8765/mcp
  OCC_APP_ID — default OCC-MCP-RACE-001 (change if you already created this app)
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


async def _call(client, name: str, args: dict) -> dict:
    r = await client.call_tool_mcp(name, args)
    if r.structuredContent:
        out = dict(r.structuredContent)
        if out.get("error_type"):
            raise RuntimeError(f"{name}: {json.dumps(out, default=str)}")
        return out
    if r.isError:
        text = ""
        for c in r.content:
            if getattr(c, "text", None):
                text += c.text
        raise RuntimeError(f"{name} failed: {text!r}")
    for c in r.content:
        if getattr(c, "text", None):
            try:
                return json.loads(c.text)
            except json.JSONDecodeError:
                return {"message": c.text}
    return {"raw": str(r)}


async def main() -> None:
    from fastmcp import Client

    async with Client(MCP_URL) as client:
        print(f"MCP URL: {MCP_URL}  application_id: {APP_ID}\n")

        try:
            r0 = await _call(
                client,
                "submit_application",
                {
                    "application_id": APP_ID,
                    "applicant_id": "COMP-OCC",
                    "requested_amount_usd": "100000",
                    "loan_purpose": "working_capital",
                    "loan_term_months": 12,
                    "submission_channel": "mcp_occ",
                    "contact_email": "occ@example.com",
                    "contact_name": "OCC Demo",
                    "application_reference": "double-decision race",
                },
            )
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            print(
                f"If the application already exists, set a fresh id, e.g.  "
                f'`$env:OCC_APP_ID=\"OCC-MCP-RACE-{os.getpid()}\"` then re-run.',
                file=sys.stderr,
            )
            sys.exit(1)
        print("submit_application:", json.dumps(r0, indent=2, default=str))

        for sid in ("sess-a", "sess-b"):
            r = await _call(
                client,
                "start_agent_session",
                {
                    "agent_type": "credit_analysis",
                    "session_id": sid,
                    "agent_id": f"agent-{sid}",
                    "application_id": APP_ID,
                    "model_version": "mv-1",
                },
            )
            print(f"start_agent_session ({sid}):", json.dumps(r, indent=2, default=str))

        print("\nReady. In two terminals, run concurrently:")
        print(f'  uv run python scripts/mcp_occ_agent.py sess-a')
        print(f'  uv run python scripts/mcp_occ_agent.py sess-b')


if __name__ == "__main__":
    asyncio.run(main())
