# The Ledger

Event-sourced audit infrastructure for multi-agent commercial loan processing at Apex Financial Services.

## Quick Start
```bash
# 1. Install uv (if needed): https://docs.astral.sh/uv/getting-started/installation/

# 2. Create env and install dependencies
uv sync

# 3. Start PostgreSQL (see "PostgreSQL (Docker)" below if you use another port)
docker run -d -e POSTGRES_PASSWORD=apex -e POSTGRES_DB=apex_ledger -p 5432:5432 postgres:16

# 4. Set environment
cp .env.example .env
# Edit .env — ANTHROPIC_API_KEY, and DATABASE_URL matching your Docker port/password

# 5. Generate all data (companies + documents + seed events → DB)
uv run python datagen/generate_all.py --db-url postgresql://postgres:apex@localhost/apex_ledger

# 6. Validate schema (no DB needed)
uv run python datagen/generate_all.py --skip-db --skip-docs --validate-only

# 7. Schema & generator tests (run before EventStore work)
uv run pytest tests/test_schema_and_generator.py -v

# 8. Event store — implement in src/event_store.py
# uv run pytest tests/test_event_store.py -v
```

## PostgreSQL (Docker)

The app and tests connect over **TCP to the port you publish on the host**, not the in-container `5432` unless you map `5432:5432`.

**Run Postgres (example):**
```bash
docker run -d --name ledger-pg \
  -e POSTGRES_PASSWORD=apex \
  -e POSTGRES_DB=apex_ledger \
  -p 5432:5432 \
  postgres:16
```

**`.env` — use the same user, password, DB name, host port:**
```env
DATABASE_URL=postgresql://postgres:apex@127.0.0.1:5432/apex_ledger
APPLICANT_REGISTRY_URL=postgresql://postgres:apex@127.0.0.1:5432/apex_ledger
```

If you map another host port (e.g. `-p 5433:5432` because `5432` is busy), only change the URL:

`postgresql://postgres:apex@127.0.0.1:5433/apex_ledger`

**Phase 1 PostgreSQL tests** try each of `TEST_DB_URL`, `DATABASE_URL`, `APPLICANT_REGISTRY_URL`, then a Docker-friendly default (`tests/pg_helpers.py`), so one stale URL in `.env` does not block the others. `tests/test_event_store.py` also deletes prior `test-%` streams so appends with `expected_version=-1` stay valid across runs. With any working URL, `uv run pytest tests/test_event_store.py tests/test_applicant_registry_client.py -v` hits the real DB; otherwise integration tests skip.

`EventStore.connect()` applies `src/schema.sql` on first connect (idempotent `CREATE IF NOT EXISTS`).

## Included in the starter
- Full event schema (45 event types) — `src/schema/events.py`
- Data generator (GAAP PDFs, Excel, CSV, 1,200+ seed events)
- Event simulator (five agent pipelines, deterministic)
- Schema validator (events against `EVENT_REGISTRY`)
- Schema/generator tests

## Implementation roadmap
| Component | File | Phase |
|-----------|------|-------|
| EventStore | `src/event_store.py` | 1 |
| ApplicantRegistryClient | `src/registry/client.py` | 1 |
| Domain aggregates | `src/domain/aggregates/` | 2 |
| DocumentProcessingAgent | `src/agents/base_agent.py` | 2 |
| CreditAnalysisAgent | `src/agents/base_agent.py` | 2 (reference) |
| FraudDetectionAgent | `src/agents/base_agent.py` | 3 |
| ComplianceAgent | `src/agents/base_agent.py` | 3 |
| DecisionOrchestratorAgent | `src/agents/base_agent.py` | 3 |
| Projections + daemon | `src/projections/` | 4 |
| Upcasters | `src/upcasters.py` | 4 |
| MCP server | `src/mcp_server.py` | 5 |
| HTTP API (BFF) | `src/api/main.py` | 6 |
| Frontend (Workbench) | `frontend/` | 8 |

Design and module specs live under [`spec/`](spec/).

### HTTP API (Phase 6)

Requires `DATABASE_URL` (or `TEST_DB_URL`) in the environment unless you inject a store in code. From the repo root:

```bash
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

`GET /health` reports store connectivity. Pipeline progress: `POST /v1/applications/{id}/pipeline/run` then `GET /v1/jobs/{job_id}/stream` (SSE).

### Frontend (Phase 8 — Agentic Workbench)

From repo root:

```bash
cd frontend
npm install
npm run dev
```

Uses `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`). See [`frontend/README.md`](frontend/README.md) and [`spec/10-frontend/`](spec/10-frontend/).

### Docker Compose (Postgres + API + Workbench UI)

If you run **everything in Docker**, use the repo [`docker-compose.yml`](docker-compose.yml):

```bash
docker compose up --build
```

| Service | Port (host) | Notes |
|---------|-------------|--------|
| **web** | [http://localhost:8080](http://localhost:8080) | Static SPA; API calls go to `http://127.0.0.1:8000` **on the host** (CORS is preconfigured for `:8080`). |
| **api** | [http://localhost:8000](http://localhost:8000) | FastAPI; `/docs`, `/health`. |
| **postgres** | `5432` | `postgres` / `apex` / `apex_ledger` |

The API container uses `DATABASE_URL=...@postgres:5432` (Docker network DNS). **Seed data** (companies, registry, etc.) is not automatic: run [`datagen/generate_all.py`](datagen/generate_all.py) from the host with  
`postgresql://postgres:apex@127.0.0.1:5432/apex_ledger` after Postgres is up.

Optional: add `ANTHROPIC_API_KEY` by mounting env — see the comment in `docker-compose.yml` (`env_file: [.env]`).

## Tests by phase
```bash
uv run pytest tests/test_schema_and_generator.py -v  # Phase 0
uv run pytest tests/test_event_store.py tests/test_applicant_registry_client.py -v  # Phase 1
uv run pytest tests/test_domain.py -v               # Phase 2 (domain; InMemory, no Postgres)
uv run pytest tests/test_narratives.py -v           # Phase 3
uv run pytest tests/test_projections.py -v          # Phase 4
uv run pytest tests/test_mcp.py -v                  # Phase 5
uv run pytest tests/test_api_health.py tests/test_api_applications.py tests/test_api_pipeline.py -v  # Phase 6
```
