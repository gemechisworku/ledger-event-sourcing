# Agentic Workbench UI — Product & Technical Specification

**Status:** Draft for review  
**Stack target:** React + Tailwind CSS  
**Backend alignment:** [`08-api-layer/fastapi-bff-plan.md`](../08-api-layer/fastapi-bff-plan.md) (FastAPI BFF, SSE pipeline progress)

This document defines a **comprehensive, interactive agentic workflow visualization** for real-world operations: clear visibility of **which agent or stage is active**, **inputs and outputs**, **workflow topology**, and **unified logs**, with **dark/light themes** and a **persistent left sidebar** navigation pattern.

---

## 1. Goals & non-goals

### 1.1 Goals

| ID | Goal |
|----|------|
| G1 | **Operational clarity** — At a glance: pipeline stage, status (pending / running / success / failed / skipped), and time bounds. |
| G2 | **Agent transparency** — For each agent or step: show **inputs** (structured) and **outputs** (structured), sourced from events or API payloads. |
| G3 | **Workflow diagram** — Interactive graph of the loan pipeline (and optionally sub-flows), aligned with domain stages (`document` → `credit` → `fraud` → `compliance` → `decision`). |
| G4 | **Live logs** — Append-only **unified log** on the frontend (SSE and/or polled resources), filterable by level/source/stage. |
| G5 | **Consistent UX** — Single design system (spacing, typography, color roles), **light + dark** modes, **left sidebar** primary navigation. |
| G6 | **Interactive** — Select nodes/steps to inspect details; pan/zoom graph; expand/collapse panels without losing context. |

### 1.2 Non-goals (initial release)

- Replacing **MCP** or **admin CLIs** for power users.
- **Authoring** new LangGraph definitions in the browser (future).
- **Multi-tenant** auth beyond a simple configurable API base URL (unless added in a later phase).

---

## 2. Research summary — recommended libraries

Findings from current ecosystem practice (2024–2026): combine a **node-based graph** for workflows, **virtualized lists** for logs, **headless UI + Tailwind** for consistent shell, and **SSE** for server-push already provided by the BFF.

### 2.1 Workflow & graph visualization

| Option | Role | Rationale |
|--------|------|-----------|
| **[@xyflow/react](https://reactflow.dev/)** (React Flow v12+) | Primary workflow canvas | De facto standard for **interactive node graphs** in React: custom nodes as React components (works well with Tailwind), pan/zoom, minimap, selection, plugins. Used in production for pipelines and builders. |
| **[elkjs](https://www.npmjs.com/package/elkjs)** (optional) | Auto-layout | **ELK** gives deterministic **DAG layout** (layers, spacing, edge routing). **Dagre** is simpler/faster but less flexible; React Flow docs showcase ELK for advanced layouts. |
| **[@dagrejs/dagre](https://www.npmjs.com/package/@dagrejs/dagre)** (optional) | Lighter auto-layout | Acceptable for **fixed left-to-right pipelines** with fewer layout knobs. |

**Recommendation:** **@xyflow/react** as mandatory; **elkjs** when the graph grows beyond a fixed list of stages or needs automatic reflow on resize.

### 2.2 Application shell, theming, forms

| Option | Role | Rationale |
|--------|------|-----------|
| **[Tailwind CSS](https://tailwindcss.com/)** | Styling | Required by product; use **CSS variables** for theme tokens. |
| **[shadcn/ui](https://ui.shadcn.com/)** (Radix primitives) | Sidebar, dialogs, tabs, scroll-area | **Copy-in** components, accessible, **dark mode** via CSS variables; **Sidebar** component fits “menus on the left” with collapse + mobile sheet. |
| **[next-themes](https://github.com/pacocoursey/next-themes)** | Theme switching | Works with **Vite + React** (not only Next.js): system preference, class `dark` on `document`, no flash if configured. |

### 2.3 Data fetching & client state

| Option | Role | Rationale |
|--------|------|-----------|
| **[TanStack Query](https://tanstack.com/query)** (`@tanstack/react-query`) | Server state | Caching, retries, deduping for REST (`/health`, `/v1/applications/...`). |
| **[Zustand](https://github.com/pmndrs/zustand)** or **TanStack Store** | UI state | Selected node, panel layout, log filters, “pinned” application id — minimal boilerplate. |

### 2.4 Logs (high volume, streaming)

| Option | Role | Rationale |
|--------|------|-----------|
| **Native `EventSource`** or **fetch streaming** | Consume BFF SSE | Matches existing **`GET /v1/jobs/{job_id}/stream`** (`text/event-stream`). |
| **[@tanstack/react-virtual](https://tanstack.com/virtual)** or **react-window** | Virtualized log list | Keeps **60fps** with thousands of lines; only visible rows mount. |
| **[react-logviewer](https://github.com/melloware/react-logviewer)** (optional) | ANSI + stream | If backend emits ANSI codes; otherwise plain text + JSON lines is enough. |

**Recommendation:** Start with **virtualized** custom log lines + JSON syntax highlight (e.g. **shiki** or lightweight **prism** on demand) to avoid heavy deps until needed.

### 2.5 Motion (optional)

| Library | Use |
|---------|-----|
| **[Framer Motion](https://www.framer.com/motion/)** | Subtle panel transitions, node highlight pulses — optional for MVP. |

### 2.6 Build tooling

| Choice | Notes |
|--------|------|
| **[Vite](https://vitejs.dev/)** + **React** + **TypeScript** | Fast DX, SPA behind FastAPI CORS; aligns with “React + Tailwind” without mandating Next.js. **Next.js** is valid if SSR/SSG is desired later. |

---

## 3. Information architecture

### 3.1 Global layout

```
┌─────────────────────────────────────────────────────────────┐
│ Top bar: app title, env badge, theme toggle, connection OK  │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                   │
│ Sidebar  │  Main content (route-based)                       │
│ (fixed)  │                                                   │
│          │                                                   │
│ • Dashboard                                                 │
│ • Applications                                              │
│ • Run pipeline (contextual)                                 │
│ • Logs / observability                                      │
│ • Settings                                                  │
│          │                                                   │
└──────────┴──────────────────────────────────────────────────┘
```

- **Sidebar:** Primary navigation; **collapsible** on desktop; **drawer** on small breakpoints (shadcn Sidebar pattern).
- **Top bar:** Breadcrumb or current application id; **API health** indicator (from `GET /health`); **dark/light** toggle.

### 3.2 Primary routes (SPA)

| Route | Purpose |
|-------|---------|
| `/` | Dashboard — summary cards (store status, recent applications). |
| `/applications` | List/search applications (from projections or `GET /v1/applications/{id}` loop — see §6). |
| `/applications/:id` | **Command center** — workflow graph + stage timeline + agent I/O + logs for one application. |
| `/applications/:id/run` | Start pipeline, pick stages, attach to SSE job. |
| `/settings` | API base URL, theme default, log retention (client-side), feature flags. |

Exact path names are implementation details; semantics above are normative.

---

## 4. Functional requirements

### 4.1 Workflow diagram (interactive)

- **Nodes:** One node per **pipeline stage** (and optionally per **agent session** when session ids are known from events).
- **Edges:** Directed edges showing **default order**; edge style reflects **data dependency** (solid) vs **sequential only** (dashed) if distinguishable in data model.
- **States:** Visual encoding (color + icon + label): `idle` | `running` | `completed` | `failed` | `skipped`.
- **Interactions:** Click node → open **Inspector** (§4.2). Pan/zoom; optional **minimap**; **fit view** button.
- **Layout:** Initial layout from **static stage list** + **ELK** (or manual coordinates) for MVP; re-run layout when window resizes if using ELK.

### 4.2 Agent / step inspector (inputs & outputs)

**Purpose:** “Full visibility” for each step.

| Field | Source (priority) |
|-------|---------------------|
| Stage name | SSE `progress.stage` + domain enum |
| Agent id / session | Event stream `agent-*` or future enriched SSE |
| **Inputs** | Last known command payload, `AgentInputValidated`, or tool args (projection/MCP in Phase 2) |
| **Outputs** | Domain events emitted (e.g. `CreditAnalysisCompleted` summary fields), truncated with “expand JSON” |
| Duration | Client timestamps between progress events; server `recorded_at` when available |

If the backend only exposes **coarse** SSE (`Starting X` / `Completed X`), the UI must still show that clearly and label **“detail: load from event stream”** with a button to **fetch** `GET /v1/applications/:id` or a future **`GET /v1/applications/:id/streams`** (out of scope for this spec’s backend section — see §6.2).

### 4.3 Unified log panel

- **Ingest:** Subscribe to **active job SSE** (`/v1/jobs/{job_id}/stream`) and append **JSON lines** to the log model.
- **Display:** Virtualized list; **timestamp**, **level** (derived from `type`: progress | complete | error), **message**, **raw JSON** expand.
- **Filters:** By `type`, by `stage`, text search (client-side index optional in Phase 2).
- **Actions:** Copy selection, clear view, pause autoscroll, export visible lines as `.jsonl`.

### 4.4 Run pipeline UX

- Form: `application_id`, optional **stage subset** (checkboxes defaulting to full pipeline).
- On submit: `POST .../pipeline/run` → receive `job_id` → auto-open **Logs** and **Workflow** with live updates until `complete` or `error`.

### 4.5 Dashboard

- Health widget: `database`, `store_pool` from `/health`.
- Shortcuts: **New application**, **Open last application**.

### 4.6 Dark & light mode

- **Tokens:** Semantic colors only (`background`, `foreground`, `muted`, `primary`, `destructive`, `border`, `sidebar-*`).
- **Persistence:** `localStorage` + `prefers-color-scheme` default.
- **Charts/graphs:** Node colors must meet **contrast** in both themes (WCAG AA target).

---

## 5. Non-functional requirements

| Area | Requirement |
|------|--------------|
| **Performance** | Log panel must stay smooth with **≥10k lines** in memory (virtualization); graph with **≤50 nodes** at 60fps interaction. |
| **Resilience** | SSE disconnect → **visible banner** + exponential backoff reconnect for the same `job_id` where possible. |
| **Security** | No secrets in localStorage except **non-production** API URL if explicitly allowed; use env at build time for production. |
| **A11y** | Keyboard navigation for sidebar, focus traps in modals, sufficient color contrast. |
| **i18n** | English-first; copy centralized for later localization. |

---

## 6. Backend integration (current & future)

### 6.1 Implemented today (FastAPI BFF)

| Capability | Endpoint | UI use |
|------------|----------|--------|
| Health | `GET /health` | Status dot, dashboard |
| Create application | `POST /v1/applications` | Form submit |
| Loan stream (JSON) | `GET /v1/applications/{id}` | Timeline / partial I/O |
| Start pipeline | `POST /v1/applications/{id}/pipeline/run` | Returns `job_id` |
| Pipeline SSE | `GET /v1/jobs/{job_id}/stream` | Logs + stage transitions |

CORS: already configured for dev origins; production must whitelist the SPA origin.

### 6.2 Likely backend extensions (post-MVP, not blocking UI skeleton)

To reach **full** agent I/O without scraping:

- **`GET /v1/applications/{id}/timeline`** — merged view of loan + docpkg + credit + fraud + compliance + key agent streams (server-side join).
- **Enriched SSE** — include `input_summary` / `output_summary` per stage when available.
- **WebSocket** (optional) — bidirectional if interactive cancellation is required.

These are **tracked as follow-ups** when drafting the implementation plan.

---

## 7. Design system (concise)

- **Typography:** One sans font (e.g. **Geist**, **Inter**, or **system-ui** stack); monospace for JSON/logs.
- **Density:** “Comfortable” default; compact mode optional for logs.
- **Icons:** **Lucide** (pairs well with shadcn).
- **Motion:** ≤200ms for panel transitions; avoid motion on log append path.

---

## 8. MVP vs later phases

| MVP | Phase 2+ |
|-----|----------|
| Sidebar shell, theme, dashboard, application create, run pipeline, SSE logs, React Flow graph with stage states | ELK auto-layout, ANSI log colors, timeline API, session-level nodes, user auth, role-based views |

---

## 9. Open questions (resolve before implementation plan)

1. **Monorepo placement:** `frontend/` at repo root vs separate repo — affects CI and env injection.
2. **Reverse proxy:** Single origin (nginx/Caddy) for `/api` → FastAPI and `/` → static SPA in production?
3. **Minimum application list:** Is a new **`GET /v1/applications` list** endpoint required, or is seeding ids from ops acceptable for v1?

---

## 10. Traceability

| Spec section | Backend doc | Tests / validation |
|--------------|-------------|-------------------|
| SSE logs | `08-api-layer/fastapi-bff-plan.md` | Manual + E2E against running BFF |
| Stage order | `src/api/services/pipeline.py` `DEFAULT_STAGES` | Snapshot tests on graph config |

---

## 11. Document history

| Version | Date | Notes |
|---------|------|--------|
| 0.1 | 2026-03-25 | Initial draft from research + product goals |
