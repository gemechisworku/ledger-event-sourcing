# Phase 6 — FastAPI BFF & pipeline streaming (plan)

**Status:** Plan only — implementation follows this document.

**Goal:** Expose the existing event-sourced domain (`EventStore`, `handlers`, LangGraph agents) to a **web frontend** via an **async HTTP API**, with **server-driven progress** suitable for **progress bars** (no polling-only UX required).

**Authority:** Aligns with [`../implementation_plan.md`](../implementation_plan.md), [`../04-domain-model/command-handlers.md`](../04-domain-model/command-handlers.md), existing MCP semantics in [`../../src/mcp_server.py`](../../src/mcp_server.py).

---

## 1. Why this layer exists

| Current surface | Limitation for SPAs |
|-----------------|---------------------|
| MCP (`stdio`) | Built for AI tools, not browsers |
| `scripts/run_pipeline.py` | Stub |
| Direct Python / pytest | Not a network contract |

**FastAPI** provides: OpenAPI schema, async I/O, streaming responses, standard deployment (uvicorn/gunicorn).

---

## 2. Architecture (high level)

```
Browser / SPA
    │  HTTPS (JSON + SSE)
    ▼
FastAPI app (`src/api/`)
    │  async route handlers
    │  dependency-injected EventStore + ApplicantRegistryClient + Anthropic client
    ▼
Pipeline orchestrator (`src/api/services/pipeline.py`)
    │  ordered: submit → … → agents / handlers (same order as narratives + MCP)
    │  yields progress events (stage name, weight, optional detail)
    ▼
Existing code only: `src/domain/handlers.py`, `src/agents/*`, `src/event_store.py`, `src/registry/client.py`
```

**Rule:** No duplicate business rules — orchestrator **calls** handlers and agents; validation stays in domain.

---

## 3. Async model

- **FastAPI** runs on **ASGI** (`uvicorn`).
- All I/O-bound work uses **async** paths already present: `EventStore.append`, `load_stream`, `ApplicantRegistryClient` (asyncpg pool).
- **LangGraph agents** use `async def process_application`; keep **one event loop** — run agents with `await` from async route handlers or async generator for SSE (no blocking `time.sleep` in request path).
- **CPU-bound** work (if any) — defer to `asyncio.to_thread` only if measured necessary; default is pure async.

**EventStore lifecycle:** Single **asyncpg pool** per app (FastAPI `lifespan` context manager: connect on startup, close on shutdown), same pattern as MCP’s `EventStore.connect()`.

---

## 4. Progress bars — **Server-Sent Events (SSE)**

**Choice:** **SSE** over **WebSockets** for progress (one-way server → client, simpler, HTTP/2 friendly, works with standard `EventSource` in browsers).

| Approach | Use |
|----------|-----|
| **SSE** `text/event-stream` | Stage progress: `{ "stage": "credit", "pct": 35, "message": "…", "done": false }` |
| **JSON REST** | Final result, job status snapshot, errors |

**Optional later:** WebSocket if you need cancel-from-UI or bidirectional chat in the same connection.

**Event shape (illustrative):**

```json
{"type":"progress","stage":"document","index":1,"total":6,"pct":17,"message":"Running document processing"}
{"type":"progress","stage":"credit","index":2,"total":6,"pct":33,"message":"Credit analysis"}
{"type":"complete","application_id":"…","summary":{...}}
{"type":"error","message":"…","code":"DOMAIN_ERROR"}
```

**Implementation detail:** `StreamingResponse` with an **async generator** that `yield`s `f"data: {json}\n\n"`; orchestrator **async-iterates** stages and `await`s each step, yielding after each.

---

## 5. Pipeline orchestrator (new code)

**Responsibility:** One module that encodes the **happy-path order** for a full application (configurable flags to skip stages for partial runs).

**Suggested stages** (align with `tests/test_narratives.py` + MCP lifecycle):

1. `submit` — `handle_submit_application` (or validate existing stream)
2. `document` — `DocumentProcessingAgent.process_application` (if documents path enabled)
3. `credit` — `CreditAnalysisAgent.process_application`
4. `fraud` — `FraudDetectionAgent.process_application`
5. `compliance` — `ComplianceAgent.process_application`
6. `decision` — `DecisionOrchestratorAgent.process_application` **or** `handle_decision_generated` + `handle_human_review_requested` depending on product flow

**Progress emission:** Before/after each stage; `pct` can be `(index / total) * 100` or weighted by expected duration.

**Failure:** On exception, yield `type:error`, log, optionally append `AgentSessionFailed` / domain-safe handling; return structured error to client.

**Idempotency:** Reuse existing agent idempotency (e.g. skip if `CreditAnalysisCompleted` already present) where applicable — document in orchestrator.

---

## 6. API surface (MVP → full)

### 6.1 Health & metadata

- `GET /health` — liveness + DB ping + optional projection lag (`ledger://ledger/health` parity)
- `GET /openapi.json` — automatic (FastAPI)

### 6.2 Applications

- `POST /v1/applications` — body mirrors `submit_application` MCP fields; returns `{ application_id, stream_version }`
- `GET /v1/applications/{application_id}` — read model from **ApplicationSummaryProjection** or `load_stream` summary (match MCP resource shape where useful)

### 6.3 Pipeline run (progress)

- `POST /v1/applications/{application_id}/pipeline` — optional body `{ "stages": ["credit","fraud",…], "async_job": true }`
  - **Option A:** Returns `202` + `job_id` + `Location: /v1/jobs/{job_id}/events` (SSE URL)
  - **Option B (simpler MVP):** Single request that **opens SSE** from client: `GET /v1/applications/{id}/pipeline/stream` with query `?stages=all` — **POST** first to create/validate, then **GET** stream (or use POST with `Accept: text/event-stream` — less common)

**Recommended MVP:**  
`POST /v1/applications/{id}/pipeline/run` returns `{ job_id }`  
`GET /v1/jobs/{job_id}/stream` — **SSE** progress until `complete` or `error`

In-process **job registry** (`dict[job_id, asyncio.Task]`) for MVP; **Redis** optional later for multi-worker.

### 6.4 Stage-only endpoints (optional, for step-by-step UI)

- `POST /v1/applications/{id}/stages/credit` — run credit agent only  
  Same pattern for fraud, compliance, etc.

---

## 7. Cross-cutting

| Concern | MVP plan |
|---------|----------|
| **CORS** | `CORSMiddleware` — allow dev origin (`localhost:5173`, etc.) |
| **Auth** | Stub: optional `X-API-Key` header or disable auth in dev; document production gap |
| **Errors** | `HTTPException` + JSON `{"detail":{...}}`; map `DomainError` to 409/422 |
| **Anthropic** | Inject `AsyncAnthropic` from settings; tests use `MagicMock` |
| **Config** | `pydantic-settings` or reuse `.env` (`DATABASE_URL`, `ANTHROPIC_API_KEY`) |

---

## 8. Dependencies (`pyproject.toml`)

Add (with version pins consistent with repo style):

- `fastapi` — API framework  
- `uvicorn[standard]` — ASGI server  
- `httpx` — optional, for async tests / internal calls  

(`sse-starlette` optional — raw `StreamingResponse` is enough for SSE.)

---

## 9. File layout (proposed)

```
src/api/
  __init__.py
  main.py              # FastAPI app, lifespan, CORS, router include
  deps.py              # get_store(), get_registry_pool(), get_anthropic()
  schemas.py           # Pydantic request/response models
  routes/
    health.py
    applications.py
    pipeline.py        # POST run + GET SSE stream
  services/
    pipeline.py        # PipelineOrchestrator, async generator of progress events
    jobs.py            # in-memory job id registry (MVP)
```

**Entrypoint:** `uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000`  
(or `python -m uvicorn ...`)

---

## 10. Testing strategy

| Test | Purpose |
|------|---------|
| `tests/test_api_health.py` | `GET /health` with `TestClient` / `httpx.AsyncClient` |
| `tests/test_api_pipeline_sse.py` | Mock agents or fast path; assert SSE chunks contain `progress` then `complete` |
| `tests/test_api_submit.py` | `POST /v1/applications` vs InMemory or test DB |

Use **`httpx.AsyncClient(app=app, lifespan="on")`** or **`pytest-asyncio`** with **`AsyncClient`** from `httpx` for async routes.

---

## 11. Milestones

| Milestone | Deliverable |
|-----------|-------------|
| **M1** | FastAPI app + `/health` + lifespan + `POST /v1/applications` |
| **M2** | Pipeline orchestrator (one stage, e.g. credit only) + SSE with fake progress |
| **M3** | Full stage chain + real agents behind feature flag + integration test vs Postgres |
| **M4** | CORS, error mapping, README “Run API” section |

---

## 12. Out of scope (this phase)

- Kubernetes / Helm  
- OAuth2 full implementation  
- Redis job queue (optional follow-up)  
- Replacing MCP — **both** can coexist  

---

## 13. Implementation plan checklist (for `implementation_plan.md`)

When implemented, add a **Phase 6 — FastAPI BFF** row and gate:  
`uv run pytest tests/test_api_*.py -v` + manual SSE smoke from browser or `curl -N`.

---

## 14. Frontend integration notes

- Progress bar: subscribe to SSE URL, update bar on each `progress` event, close on `complete` / `error`.
- Final state: `GET /v1/applications/{id}` or existing projection JSON.
- Use **same `application_id`** across tabs; optional WebSocket later for live collaboration.

This plan is ready for implementation in a follow-up task.
