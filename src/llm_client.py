"""
OpenRouter LLM client — single module for all model calls.

Reads OPENROUTER_API_KEY and OPENROUTER_MODEL from environment.
Uses the OpenAI Python SDK pointed at OpenRouter's API.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


def build_llm_client() -> AsyncOpenAI:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required. Set it in .env or environment."
        )
    return AsyncOpenAI(
        api_key=key,
        base_url=OPENROUTER_BASE,
        default_headers={"HTTP-Referer": "https://apex-ledger.local", "X-Title": "Apex Ledger"},
    )


def get_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL).strip()


async def chat_completion(
    client: AsyncOpenAI,
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 1024,
) -> LLMResponse:
    """Simple chat completion (no tool use)."""
    mdl = model or get_model()
    resp = await client.chat.completions.create(
        model=mdl,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = resp.choices[0]
    text = choice.message.content or ""
    usage = resp.usage
    return LLMResponse(
        text=text,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        model=mdl,
    )


async def chat_completion_with_tools(
    client: AsyncOpenAI,
    *,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str | None = None,
    max_tokens: int = 2048,
) -> Any:
    """Chat completion with function calling; returns the raw OpenAI response for tool-call loop."""
    mdl = model or get_model()
    return await client.chat.completions.create(
        model=mdl,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, *messages],
        tools=tools,
        tool_choice="auto",
    )


def build_mock_llm_client() -> AsyncOpenAI:
    """For tests only — returns a real-shaped AsyncOpenAI that won't make network calls."""
    from unittest.mock import AsyncMock, MagicMock

    client = MagicMock(spec=AsyncOpenAI)

    async def _fake_create(**kwargs: Any) -> Any:
        system = ""
        for m in kwargs.get("messages", []):
            if m.get("role") == "system":
                system = m.get("content", "").lower()
        if "fraud" in system:
            text = '{"fraud_score":0.12,"recommendation":"CLEAR","anomalies":[]}'
        elif "orchestrator" in system:
            text = '{"recommendation":"REFER","confidence":0.65,"executive_summary":"Mock orchestrator."}'
        else:
            text = '{"risk_tier":"MEDIUM","recommended_limit_usd":400000,"confidence":0.82,"rationale":"Mock credit.","key_concerns":[],"data_quality_caveats":[],"policy_overrides_applied":[]}'

        msg = MagicMock()
        msg.content = text
        msg.tool_calls = None
        choice = MagicMock()
        choice.message = msg
        choice.finish_reason = "stop"
        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 200
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    completions = MagicMock()
    completions.create = AsyncMock(side_effect=_fake_create)
    chat_obj = MagicMock()
    chat_obj.completions = completions
    client.chat = chat_obj
    return client
