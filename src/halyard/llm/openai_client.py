"""OpenAI adapter (Responses API, strict JSON-schema output)."""

from __future__ import annotations

import json
from typing import Any

import openai

from halyard.llm.base import JsonResult, LLMClient, LLMError


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self, api_key: str, model: str, purpose: str, **kwargs: Any):
        super().__init__(model, purpose, **kwargs)
        self._client = openai.OpenAI(api_key=api_key)

    def _complete_json(
        self, system: str, user: str, schema: dict[str, Any], name: str, max_tokens: int
    ) -> JsonResult:
        try:
            resp = self._client.responses.create(
                model=self.model,
                instructions=system,
                input=user,
                max_output_tokens=max_tokens,
                store=False,
                text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"openai/{self.model}: {exc}") from exc
        if resp.status != "completed":
            raise LLMError(f"openai/{self.model} did not complete (status {resp.status})")
        try:
            data = json.loads(resp.output_text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"openai/{self.model} returned non-JSON output") from exc
        return JsonResult(
            data=data,
            provider=self.provider,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
