"""
tests/conftest.py — shared fixtures
"""
import os
import random
import sys
from pathlib import Path

import pytest
from faker import Faker

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from tests.pg_helpers import DEFAULT_PG_URL, candidate_postgres_urls

random.seed(42)
Faker.seed(42)

@pytest.fixture
def db_url():
    """First configured URL (see candidate_postgres_urls for full list)."""
    urls = candidate_postgres_urls()
    return urls[0] if urls else DEFAULT_PG_URL

@pytest.fixture
def sample_companies():
    from datagen.company_generator import generate_companies
    return generate_companies(10)

@pytest.fixture
def event_store_class():
    """Returns the EventStore class. Swap for real once implemented."""
    from src.event_store import EventStore
    return EventStore


@pytest.fixture(autouse=True)
def _clear_anthropic_key_for_api_http_tests(monkeypatch, request):
    """FastAPI tests use in-memory store + mock Anthropic; ignore real key from .env."""
    if request.node.path.name.startswith("test_api_"):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
