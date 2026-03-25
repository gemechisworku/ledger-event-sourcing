# Ledger Workbench (frontend)

React + Vite + Tailwind SPA for the **Agentic Workbench**: pipeline graph, SSE logs, loan stream viewer, dark/light theme.

## Prerequisites

- Node 20+ recommended
- FastAPI BFF running ([`spec/10-frontend/implementation-plan.md`](../spec/10-frontend/implementation-plan.md) assumes `src/api` Phase 6)

## Setup

```bash
cd frontend
cp .env.example .env   # optional; defaults to http://127.0.0.1:8000
npm install
```

## Dev server

```bash
npm run dev
```

Open `http://localhost:5173`. Ensure the API allows this origin (`CORS_ORIGINS` in the Python `.env` includes `http://localhost:5173` — default in `src/api/main.py`).

## Docker (production-style static build)

From the **repository root** (not only `frontend/`):

```bash
docker compose up --build
```

Workbench is served at **http://localhost:8080**; the API is on **http://localhost:8000** on the host. The Vite build is baked with `VITE_API_BASE_URL=http://127.0.0.1:8000` so the browser calls the API on your machine. See root [`README.md`](../README.md) **Docker Compose** section.

## Build / lint

```bash
npm run build
npm run lint
```

## API base URL

- Build-time: `VITE_API_BASE_URL` in `.env`
- Runtime override: **Settings** page (stored in `localStorage`), then reload

## Spec

- Product: [`../spec/10-frontend/agentic-workbench-ui-spec.md`](../spec/10-frontend/agentic-workbench-ui-spec.md)
- Implementation phases: [`../spec/10-frontend/implementation-plan.md`](../spec/10-frontend/implementation-plan.md)
