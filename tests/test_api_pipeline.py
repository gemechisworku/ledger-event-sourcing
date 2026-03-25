"""Pipeline SSE progress."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from starlette.testclient import TestClient

from src.api.main import create_app
from src.event_store import InMemoryEventStore


def test_pipeline_sse_document_and_credit():
    app = create_app(store=InMemoryEventStore())
    with TestClient(app) as client:
        sub = {
            "application_id": "API-PIPE-001",
            "applicant_id": "COMP-PIPE-1",
            "requested_amount_usd": "500000",
            "loan_purpose": "expansion",
            "loan_term_months": 60,
            "submission_channel": "api",
            "contact_email": "ops@example.com",
            "contact_name": "Riley",
            "application_reference": "Plant expansion",
        }
        assert client.post("/v1/applications", json=sub).status_code == 200

        pr = client.post(
            "/v1/applications/API-PIPE-001/pipeline/run",
            json={"stages": ["document", "credit"]},
        )
        assert pr.status_code == 200
        job_id = pr.json()["job_id"]
        assert job_id

        events: list[dict] = []
        with client.stream("GET", f"/v1/jobs/{job_id}/stream") as resp:
            assert resp.status_code == 200
            buf = b""
            for chunk in resp.iter_bytes():
                buf += chunk
                while b"\n\n" in buf:
                    block, buf = buf.split(b"\n\n", 1)
                    for line in block.split(b"\n"):
                        if line.startswith(b"data: "):
                            events.append(json.loads(line[6:].decode()))

        types = [e.get("type") for e in events]
        assert "progress" in types
        assert "complete" in types
        assert events[-1].get("type") == "complete"
        assert events[-1].get("application_id") == "API-PIPE-001"


def test_pipeline_unknown_job_404():
    app = create_app(store=InMemoryEventStore())
    with TestClient(app) as client:
        r = client.get("/v1/jobs/00000000-0000-0000-0000-000000000000/stream")
        assert r.status_code == 404
