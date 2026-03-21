# MCP architecture

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md)

- **Tools** = **commands** → `EventStore.append`
- **Resources** = **queries** → projection tables / indexed reads
- **CQRS** is structural: write path and read path separated at the MCP boundary.

## Integration test (lifecycle)

Drive **ApplicationSubmitted → FinalApproved** using **only MCP tools** (no direct Python domain calls in tests):

1. `start_agent_session`
2. `record_credit_analysis`
3. (fraud, compliance as required by your flow)
4. `generate_decision`
5. `record_human_review`
6. Query `ledger://applications/{id}/compliance` — full trace present

If a step needs a bypass, the MCP surface is incomplete.

## Stack

- **FastMcp** (`pyproject.toml`) — `src/mcp_server.py` entrypoint.
