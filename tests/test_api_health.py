"""API health endpoint."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from starlette.testclient import TestClient

from src.api.main import create_app
from src.event_store import InMemoryEventStore


def test_health_ok_in_memory():
    app = create_app(store=InMemoryEventStore())
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["database"] == "in-memory"
    assert data["store_pool"] is False
