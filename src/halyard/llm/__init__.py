"""LLMClient and provider adapters. Use `get_client`; never import an adapter directly."""

from __future__ import annotations

from halyard.llm.base import JsonResult, LLMClient, LLMError
from halyard.settings import HalyardError, Settings

__all__ = ["JsonResult", "LLMClient", "LLMError", "get_client"]


def get_client(settings: Settings, purpose: str) -> LLMClient:
    """Client for `purpose` ("label" or "agent") using the provider and models in .env."""
    model = settings.label_model if purpose == "label" else settings.agent_model
    if not model:
        var = "LABEL_MODEL" if purpose == "label" else "AGENT_MODEL"
        raise HalyardError(f"{var} is empty in .env.")
    if not settings.llm_api_key:
        raise HalyardError(f"{settings.llm_provider.upper()}_API_KEY is empty in .env.")
    if settings.llm_provider == "openai":
        from halyard.llm.openai_client import OpenAIClient

        return OpenAIClient(settings.llm_api_key, model, purpose)
    from halyard.llm.anthropic_client import AnthropicClient

    return AnthropicClient(settings.llm_api_key, model, purpose)
