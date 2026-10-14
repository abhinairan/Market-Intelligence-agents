"""Anthropic adapter. Structured output via a single forced tool call.

Labelling only: tool calling for the agents is implemented in the OpenAI adapter alone, so
`run_with_tools` here raises the base class's "not implemented" error.
"""

from __future__ import annotations

from typing import Any

import anthropic

from halyard.llm.base import JsonResult, LLMClient, LLMError


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, api_key: str, model: str, purpose: str, **kwargs: Any):
        super().__init__(model, purpose, **kwargs)
        self._client = anthropic.Anthropic(api_key=api_key)

    def _complete_json(
        self, system: str, user: str, schema: dict[str, Any], name: str, max_tokens: int
    ) -> JsonResult:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[{"name": name, "description": f"Return the {name} result.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": name},
            )
        except anthropic.AnthropicError as exc:
            raise LLMError(f"anthropic/{self.model}: {exc}") from exc
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            raise LLMError(f"anthropic/{self.model} returned no structured output")
        return JsonResult(
            data=dict(block.input),
            provider=self.provider,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
