# Agentic Workbench UI — Implementation Plan

**Authority:** [`agentic-workbench-ui-spec.md`](agentic-workbench-ui-spec.md)  
**Backend dependency:** Phase 6 FastAPI BFF (`src/api/`) — health, applications CRUD-style, pipeline run, job SSE.

**Decisions locked for this plan**

| Open question (spec §9) | Decision |
|-------------------------|----------|
| Monorepo placement | **`frontend/`** at repository root (Vite SPA); single repo for API + UI in training context. |
| Reverse proxy | **Dev:** Vite proxy to `http://127.0.0.1:8000` **or** `VITE_API_BASE_URL`. **Prod:** document Caddy/nginx pattern; not implemented in this phase. |
| Application list | **MVP:** `localStorage` **recent application IDs** + manual text field to jump to `/applications/:id`. **Stretch:** add `GET /v1/applications` (projection-backed) in a small backend slice. |

---

## How to use this file

Same convention as root [`implementation_plan.md`](../implementation_plan.md): `[ ]` / `[x]` for tasks; add rows to **Progress log** at bottom when milestones merge.

---

## Stack (frozen for MVP)

| Layer | Choice |
|-------|--------|
| Build | **Vite 6+**, **React 18+**, **TypeScript** |
| Styling | **Tailwind CSS**, **shadcn/ui** (Radix), **Lucide** icons |
| Theme | **next-themes** + `class` strategy on `<html>` |
| Routing | **React Router v7** (`createBrowserRouter`) |
| Server state | **TanStack Query v5** |
| Client UI state | **Zustand** (minimal: selected stage, job id, log filters) |
| Graph | **@xyflow/react** |
| Logs | **@tanstack/react-virtual** + manual row renderer |
| HTTP | **fetch** + thin wrapper; SSE via **`fetch` streaming** or **`EventSource`** (prefer one consistently — see Phase 3) |

Optional later: **elkjs** auto-layout (Phase 6 polish), **Playwright** E2E (Phase 7).

---

## Phase F0 — Bootstrap & quality bar

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F0.1 | Create `frontend/` | `npm create vite@latest frontend -- --template react-ts`; `cd frontend`; install deps | `npm run build` succeeds |
| F0.2 | Tailwind + shadcn | `npx shadcn@latest init`; add `components.json`; base color slate/zinc per taste | Dark class on `html` works |
| F0.3 | ESLint + Prettier | Align with Vite ESLint; format on save documented in README snippet | CI-ready `npm run lint` |
| F0.4 | Env contract | `VITE_API_BASE_URL` default `http://127.0.0.1:8000`; `.env.example` in `frontend/` | Document in `frontend/README.md` |
| F0.5 | Path aliases | `@/` → `src/` | Imports resolve |

**Gate:** `cd frontend && npm run build && npm run lint`

---

## Phase F1 — App shell: sidebar, router, theme

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F1.1 | **ThemeProvider** | `next-themes`; toggle in header; persist preference | Toggle + reload keeps theme |
| F1.2 | **Root layout** | Left **Sidebar** (shadcn): Dashboard, Applications, Settings; **top bar**: title, health indicator placeholder, theme toggle | Responsive: sheet on mobile |
| F1.3 | **Routes** | `/`, `/applications`, `/applications/:id`, `/applications/:id/run`, `/settings` | 404 route |
| F1.4 | **Design tokens** | Use shadcn semantic colors only; sidebar variables for dark | No raw hex in feature pages |

**Gate:** Navigate all routes without console errors; Lighthouse a11y basics (sidebar keyboard).

---

## Phase F2 — API layer & dashboard

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F2.1 | **QueryClientProvider** | Global TanStack Query; devtools optional in dev | — |
| F2.2 | **API module** | `src/lib/api.ts`: `getHealth()`, typed responses matching FastAPI `HealthResponse` | Unit test with MSW optional |
| F2.3 | **Health hook** | `useHealth` poll every 30s + on focus; show **green/amber/red** in header | Disconnect BFF → red |
| F2.4 | **Dashboard page** | Cards: DB status text, link to Applications, “New application” CTA | Manual |

**Gate:** With BFF running, dashboard shows `database` + `store_pool` from `/health`.

---

## Phase F3 — Applications: create, recent list, settings

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F3.1 | **Create application form** | Fields per `ApplicationCreate` (Pydantic); `POST /v1/applications`; toast on success/error | 422/409 surfaced |
| F3.2 | **Recent IDs** | Zustand or hook: push `application_id` to `localStorage` queue (max 20 deduped) | Survives refresh |
| F3.3 | **Applications index** | List recent IDs + input to **open by id** → navigate to `/applications/:id` | — |
| F3.4 | **Settings page** | Edit `VITE_API_BASE_URL` override stored in `localStorage` (dev only warning); reload instructions | — |

**Gate:** Create app via UI; appears in recent; open detail route.

---

## Phase F4 — Application command center (data)

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F4.1 | **Load loan stream** | `GET /v1/applications/:id`; handle 404 | — |
| F4.2 | **Timeline panel** | Table or list: `event_type`, `stream_position`, collapsible `payload` JSON (syntax highlight optional: `react-json-view-lite` or `<pre>` + format) | Readable |
| F4.3 | **Metadata** | If API later adds `metadata` per event, show it; until then hide section | Spec alignment |

**Gate:** User sees full loan stream for a seeded application.

---

## Phase F5 — Pipeline run + SSE log stream

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F5.1 | **Run form** | `POST .../pipeline/run` with optional `stages` checkboxes (default all `DEFAULT_STAGES` mirrored in `src/lib/pipeline-stages.ts`) | Returns `job_id` |
| F5.2 | **SSE client** | `GET /v1/jobs/{job_id}/stream`; parse `data: {...}\n\n`; append to ring buffer or full array with cap (e.g. 50k lines) + “clear” | Complete event closes stream reader |
| F5.3 | **Log viewer** | Virtualized list; columns: time (client receive), type, stage, message; filter chips: type, stage; search | Smooth scroll |
| F5.4 | **SSE resilience** | On error: banner “stream ended”; optional **Reconnect** button (new `POST` run if business allows) | Document limitation: job is one-shot |

**Gate:** Run pipeline from UI; see progress + complete in log; under 10k lines no jank.

---

## Phase F6 — Workflow graph (React Flow)

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F6.1 | **Static graph** | Nodes = `document`, `credit`, `fraud`, `compliance`, `decision`; edges sequential | Matches `DEFAULT_STAGES` order |
| F6.2 | **Derive state from SSE** | Map last `progress`/`complete`/`error` events to node status colors | Running stage pulses or border |
| F6.3 | **Controls** | MiniMap, zoom in/out, fit view | — |
| F6.4 | **Click node** | Set selected stage in Zustand; sync inspector (Phase F7) | — |

**Gate:** Visual parity with a live run: stages light up in order.

---

## Phase F7 — Stage inspector (best-effort transparency)

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F7.1 | **Inspector panel** | Right drawer or bottom split: shows selected stage name + **last SSE lines** for that `stage` | — |
| F7.2 | **Loan stream assist** | Button “Reload loan stream” → refetch `GET /v1/applications/:id`; show **relevant event types** for stage (client-side filter map: e.g. credit → `CreditAnalysisRequested`, `CreditAnalysisCompleted` strings) | User sees partial I/O |
| F7.3 | **Honest empty states** | If no matching events: copy from spec — “Full agent I/O requires timeline API (planned)” | No fake data |

**Gate:** For a completed run, inspector shows something meaningful for ≥2 stages.

---

## Phase F8 — Polish & documentation

| # | Task | Detail | Verification |
|---|------|--------|--------------|
| F8.1 | **CORS dev** | Document `CORS_ORIGINS` in root `.env` including `http://localhost:5173` | Dev checklist |
| F8.2 | **Root README** | Section “Frontend”: install, `npm run dev`, proxy env | New contributor can run |
| F8.3 | **Playwright (optional)** | Smoke: health visible, create app happy path | CI job optional |
| F8.4 | **Accessibility pass** | Sidebar roving tabindex; focus visible; log panel aria-live for `error` type | Manual checklist |

**Gate:** README steps verified on clean clone.

---

## Backend slices (optional; parallel tracks)

Not blocking F0–F8 MVP; implement when inspector/timeline needs real data.

| # | Backend task | Endpoint / change | Enables |
|---|--------------|-------------------|--------|
| B1 | List applications | `GET /v1/applications?limit=&cursor=` from `projection_application_summary` or distinct `loan-%` streams | Rich Applications index |
| B2 | Timeline | `GET /v1/applications/{id}/timeline` merged streams | Full agent I/O without client merge |
| B3 | Enriched SSE | Optional `detail` in progress events | Fewer REST round-trips |

Track in root `implementation_plan.md` or separate PRs.

---

## Verification matrix (MVP)

| Capability | How to verify |
|--------------|----------------|
| Dark/light | Toggle; persist |
| Sidebar nav | All links work |
| Health | Matches BFF |
| Create + open app | End-to-end manual |
| Pipeline + logs | SSE visible; complete received |
| Workflow graph | Stage colors follow SSE |
| Inspector | Shows SSE + filtered loan events |

---

## Progress log

| Date | What changed |
|------|----------------|
| 2026-03-25 | F0–F8 delivered in one pass: `frontend/` Vite SPA, Tailwind tokens, Radix-based UI primitives, shell, dashboard, applications + recent ids, settings API override, application detail with loan timeline, pipeline run + EventSource SSE + virtualized logs, React Flow graph + stage inspector, README + `.env.example`. |

---

## Estimated sequencing (indicative)

| Phase block | Calendars (solo dev, indicative) |
|-------------|-----------------------------------|
| F0–F1 | 2–4 days |
| F2–F3 | 2–3 days |
| F4–F5 | 3–5 days |
| F6–F7 | 3–5 days |
| F8 | 1–2 days |

Parallel: backend B1 can start after F3 if list view is prioritized.
