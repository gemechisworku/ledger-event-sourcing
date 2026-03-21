# Business rules (six)

1. State machine transitions only.
2. **Gas Town:** `AgentContextLoaded` before any decision on AgentSession.
3. **Model churn:** no second `CreditAnalysisCompleted` unless superseded by human override.
4. **Confidence floor:** `DecisionGenerated` with confidence &lt; 0.6 → `REFER`.
5. **Compliance:** `ApplicationApproved` only if required compliance checks passed.
6. **Causal chain:** `contributing_agent_sessions` must reference sessions that actually processed this application.

Enforce in **aggregates** / domain layer, not only HTTP/MCP.
