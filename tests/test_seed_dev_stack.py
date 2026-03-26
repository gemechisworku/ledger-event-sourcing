"""
Integration checks for scripts/seed_dev_stack.py (requires PostgreSQL).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import asyncpg
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.pg_helpers import candidate_postgres_urls


def _load_seed_module():
    p = _ROOT / "scripts" / "seed_dev_stack.py"
    spec = importlib.util.spec_from_file_location("seed_dev_stack", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _pg_url() -> str:
    urls = candidate_postgres_urls()
    if not urls:
        pytest.skip("No PostgreSQL URL configured")
    return urls[0]


@pytest.mark.asyncio
async def test_seed_registry_upserts_company_and_financials():
    url = _pg_url()
    try:
        conn = await asyncpg.connect(url, timeout=10)
    except Exception as exc:
        pytest.skip(f"Could not connect: {exc!r}")
    mod = _load_seed_module()
    profiles = [
        {
            "company_id": "COMP-001",
            "name": "Test Rodriguez",
            "industry": "technology",
            "jurisdiction": "VA",
            "legal_type": "LLC",
            "trajectory": "STABLE",
            "risk_segment": "MEDIUM",
            "compliance_flags": [],
        }
    ]
    try:
        await mod.seed_registry(conn, profiles)
        row = await conn.fetchrow(
            "SELECT company_id, name, risk_segment FROM applicant_registry.companies WHERE company_id = $1",
            "COMP-001",
        )
        assert row is not None
        assert row["name"] == "Test Rodriguez"
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM applicant_registry.financial_history WHERE company_id = $1",
            "COMP-001",
        )
        assert n == 3
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_seed_demo_and_projection():
    url = _pg_url()
    try:
        conn = await asyncpg.connect(url, timeout=10)
    except Exception as exc:
        pytest.skip(f"Could not connect: {exc!r}")

    mod = _load_seed_module()
    profiles = [
        {
            "company_id": "COMP-001",
            "name": "Test Rodriguez",
            "industry": "technology",
            "jurisdiction": "VA",
            "legal_type": "LLC",
            "trajectory": "STABLE",
            "risk_segment": "MEDIUM",
            "compliance_flags": [],
        }
    ]
    await mod.seed_registry(conn, profiles)
    await conn.close()

    from src.domain.streams import loan_stream_id
    from src.event_store import EventStore
    from src.upcasters import default_upcaster_registry

    store = EventStore(url, upcaster_registry=default_upcaster_registry())
    await store.connect()
    try:
        await mod.seed_demo_application(store, _ROOT)
        await mod.catch_up_application_summary(store)
        assert store.pool is not None
        async with store.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT application_id, state, applicant_id FROM projection_application_summary WHERE application_id = $1",
                mod.DEMO_APPLICATION_ID,
            )
        assert row is not None
        assert row["applicant_id"] == mod.DEMO_APPLICANT_ID
        # Projection state reflects full ledger history; shared DBs may be past SUBMITTED.
        assert row["state"]
        sid = loan_stream_id(mod.DEMO_APPLICATION_ID)
        stream = await store.load_stream(sid)
        assert any(e.event_type == "ApplicationSubmitted" for e in stream)
        # Idempotent: no duplicate DocumentUploaded burst
        n_docs_1 = sum(1 for e in stream if e.event_type == "DocumentUploaded")
        await mod.seed_demo_application(store, _ROOT)
        stream2 = await store.load_stream(sid)
        n_docs_2 = sum(1 for e in stream2 if e.event_type == "DocumentUploaded")
        assert n_docs_1 == n_docs_2
    finally:
        await store.close()
