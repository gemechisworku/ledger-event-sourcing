"""API application submit + read."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from starlette.testclient import TestClient

from src.api.main import create_app
from src.event_store import InMemoryEventStore


def test_create_and_get_application():
    app = create_app(store=InMemoryEventStore())
    with TestClient(app) as client:
        body = {
            "application_id": "API-APP-001",
            "applicant_id": "COMP-API-1",
            "requested_amount_usd": "350000",
            "loan_purpose": "working_capital",
            "loan_term_months": 48,
            "submission_channel": "api",
            "contact_email": "cfo@example.com",
            "contact_name": "Alex Kim",
            "application_reference": "WC line 2026",
        }
        r = client.post("/v1/applications", json=body)
        assert r.status_code == 200
        assert r.json()["application_id"] == "API-APP-001"

        g = client.get("/v1/applications/API-APP-001")
        assert g.status_code == 200
        data = g.json()
        assert data["event_count"] >= 1
        assert data["events"][0]["event_type"] == "ApplicationSubmitted"


def test_list_applications_in_memory_returns_empty_with_note():
    app = create_app(store=InMemoryEventStore())
    with TestClient(app) as client:
        r = client.get("/v1/applications")
        assert r.status_code == 200
        data = r.json()
        assert data["applications"] == []
        assert "in-memory" in (data.get("note") or "").lower()


def test_create_duplicate_conflict():
    app = create_app(store=InMemoryEventStore())
    body = {
        "application_id": "API-DUP",
        "applicant_id": "X",
        "requested_amount_usd": "10000",
        "loan_purpose": "bridge",
        "loan_term_months": 12,
        "submission_channel": "api",
        "contact_email": "a@b.c",
        "contact_name": "T",
        "application_reference": "r",
    }
    with TestClient(app) as client:
        assert client.post("/v1/applications", json=body).status_code == 200
        r2 = client.post("/v1/applications", json=body)
        assert r2.status_code == 409
