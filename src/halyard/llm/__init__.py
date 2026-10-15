"""LLMClient and provider adapters. Use `get_client`; never import an adapter directly."""

from __future__ import annotations

from halyard.llm.base import (
    JsonResult,
    LLMClient,
    LLMError,
    Message,
    ToolCall,
    ToolSpec,
    ToolTurn,
)
from halyard.settings import HalyardError, Settings

__all__ = [
    "JsonResult",
    "LLMClient",
    "LLMError",
    "Message",
    "ToolCall",
    "ToolSpec",
    "ToolTurn",
    "get_client",
]


MODEL_VARS = {"label": "LABEL_MODEL", "agent": "AGENT_MODEL", "judge": "JUDGE_MODEL"}


def get_client(settings: Settings, purpose: str) -> LLMClient:
    """Client for `purpose` ("label", "agent" or "judge") using the provider and models in .env."""
    if purpose not in MODEL_VARS:
        raise HalyardError(f"Unknown model purpose {purpose!r}.")
    model = getattr(settings, f"{purpose}_model")
    if not model:
        raise HalyardError(f"{MODEL_VARS[purpose]} is empty in .env.")
    if not settings.llm_api_key:
        raise HalyardError(f"{settings.llm_provider.upper()}_API_KEY is empty in .env.")
    if settings.llm_provider == "openai":
        from halyard.llm.openai_client import OpenAIClient

        return OpenAIClient(settings.llm_api_key, model, purpose)
    from halyard.llm.anthropic_client import AnthropicClient

    return AnthropicClient(settings.llm_api_key, model, purpose)
