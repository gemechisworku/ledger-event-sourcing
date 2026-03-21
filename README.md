# The Ledger

Event-sourced audit infrastructure for multi-agent commercial loan processing at Apex Financial Services.

## Quick Start
```bash
# 1. Install uv (if needed): https://docs.astral.sh/uv/getting-started/installation/

# 2. Create env and install dependencies
uv sync

# 3. Start PostgreSQL
docker run -d -e POSTGRES_PASSWORD=apex -e POSTGRES_DB=apex_ledger -p 5432:5432 postgres:16

# 4. Set environment
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY

# 5. Generate all data (companies + documents + seed events → DB)
uv run python datagen/generate_all.py --db-url postgresql://postgres:apex@localhost/apex_ledger

# 6. Validate schema (no DB needed)
uv run python datagen/generate_all.py --skip-db --skip-docs --validate-only

# 7. Schema & generator tests (run before EventStore work)
uv run pytest tests/test_schema_and_generator.py -v

# 8. Event store — implement in ledger/event_store.py
# uv run pytest tests/test_event_store.py -v
```

## Included in the starter
- Full event schema (45 event types) — `ledger/schema/events.py`
- Data generator (GAAP PDFs, Excel, CSV, 1,200+ seed events)
- Event simulator (five agent pipelines, deterministic)
- Schema validator (events against `EVENT_REGISTRY`)
- Schema/generator tests

## Implementation roadmap
| Component | File | Phase |
|-----------|------|-------|
| EventStore | `ledger/event_store.py` | 1 |
| ApplicantRegistryClient | `ledger/registry/client.py` | 1 |
| Domain aggregates | `ledger/domain/aggregates/` | 2 |
| DocumentProcessingAgent | `ledger/agents/base_agent.py` | 2 |
| CreditAnalysisAgent | `ledger/agents/base_agent.py` | 2 (reference) |
| FraudDetectionAgent | `ledger/agents/base_agent.py` | 3 |
| ComplianceAgent | `ledger/agents/base_agent.py` | 3 |
| DecisionOrchestratorAgent | `ledger/agents/base_agent.py` | 3 |
| Projections + daemon | `ledger/projections/` | 4 |
| Upcasters | `ledger/upcasters.py` | 4 |
| MCP server | `ledger/mcp_server.py` | 5 |

Design and module specs live under [`spec/`](spec/).

## Tests by phase
```bash
uv run pytest tests/test_schema_and_generator.py -v  # Phase 0
uv run pytest tests/test_event_store.py -v           # Phase 1
uv run pytest tests/test_domain.py -v               # Phase 2
uv run pytest tests/test_narratives.py -v           # Phase 3
uv run pytest tests/test_projections.py -v          # Phase 4
uv run pytest tests/test_mcp.py -v                  # Phase 5
```
