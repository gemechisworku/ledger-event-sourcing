"""Pydantic models for REST API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    application_id: str = Field(..., min_length=1)
    applicant_id: str
    requested_amount_usd: Decimal
    loan_purpose: str
    loan_term_months: int = Field(ge=1, le=600)
    submission_channel: str = "web"
    contact_email: str
    contact_name: str
    application_reference: str = ""


class ApplicationResponse(BaseModel):
    application_id: str
    stream_id: str
    stream_version: int


class ApplicationListItem(BaseModel):
    """Read model row from projection + stream metadata (when Postgres)."""

    application_id: str
    state: str
    applicant_id: str | None = None
    requested_amount_usd: str | None = None
    decision: str | None = None
    risk_tier: str | None = None
    compliance_status: str | None = None
    fraud_score: float | None = None
    last_event_type: str | None = None
    last_event_at: str | None = None
    updated_at: str | None = None
    stream_version: int = -1


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationListItem]
    note: str | None = None


class PipelineRunRequest(BaseModel):
    """Optional subset of stages; default runs full pipeline."""

    stages: list[str] | None = None


class PipelineRunResponse(BaseModel):
    job_id: str
    stream_url: str


class HealthResponse(BaseModel):
    status: str
    database: str
    store_pool: bool


class ProgressEvent(BaseModel):
    type: str
    stage: str | None = None
    index: int | None = None
    total: int | None = None
    pct: int | None = None
    message: str | None = None
    application_id: str | None = None
    detail: dict[str, Any] | None = None


class DecisionHistoryEvent(BaseModel):
    stream_id: str
    event_type: str
    stream_position: int
    global_position: int | None = None
    recorded_at: str | None = None
    payload: dict[str, Any] | None = None


class DecisionHistoryResponse(BaseModel):
    application_id: str
    total_events: int
    streams_queried: list[str]
    events: list[DecisionHistoryEvent]
    integrity: dict[str, Any] | None = None


class ConversationMessage(BaseModel):
    role: str
    content: str


class NLQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    history: list[ConversationMessage] = []


class NLQueryResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]] = []
    model: str | None = None
    tokens_used: int | None = None


# ── Persisted NL chats ──

class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)


class ConversationSummary(BaseModel):
    id: str
    client_session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationMessageRow(BaseModel):
    id: str
    role: str
    content: str
    model: str | None = None
    tokens_used: int | None = None
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    conversation: ConversationSummary
    messages: list[ConversationMessageRow]


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class ConversationQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
