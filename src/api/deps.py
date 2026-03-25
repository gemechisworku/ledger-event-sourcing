"""FastAPI dependencies."""
from __future__ import annotations

from typing import Any

from fastapi import Request


def get_store(request: Request) -> Any:
    return request.app.state.store


def get_job_registry(request: Request):
    return request.app.state.jobs


def get_anthropic(request: Request) -> Any:
    return request.app.state.anthropic
