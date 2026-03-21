"""
Postgres URL resolution for integration tests.
Loads .env when imported (same as individual test modules).
"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

DEFAULT_PG_URL = "postgresql://postgres:apex@127.0.0.1:5432/apex_ledger"


def candidate_postgres_urls() -> list[str]:
    """
    URLs to try in order. Deduplicate so one bad DATABASE_URL does not block Docker on :5432.
    """
    seen: set[str] = set()
    out: list[str] = []
    for key in ("TEST_DB_URL", "DATABASE_URL", "APPLICANT_REGISTRY_URL"):
        v = os.environ.get(key)
        if v and v.strip() and v not in seen:
            seen.add(v)
            out.append(v.strip())
    if DEFAULT_PG_URL not in seen:
        out.append(DEFAULT_PG_URL)
    return out
