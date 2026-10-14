"""OpenAI adapter (Responses API): strict JSON-schema output and tool calling."""

from __future__ import annotations

import json
from typing import Any

import openai

from halyard.llm.base import (
    JsonResult,
    LLMClient,
    LLMError,
    Message,
    ToolCall,
    ToolSpec,
    ToolTurn,
)


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

    def _run_with_tools(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
        require_tool: bool,
    ) -> ToolTurn:
        try:
            resp = self._client.responses.create(
                model=self.model,
                instructions=system,
                input=to_input(messages),
                tools=[to_tool(t) for t in tools],
                tool_choice="required" if require_tool else "auto",
                max_output_tokens=max_tokens,
                store=False,
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"openai/{self.model}: {exc}") from exc
        if resp.status != "completed":
            raise LLMError(f"openai/{self.model} did not complete (status {resp.status})")
        details = getattr(resp.usage, "input_tokens_details", None)
        return ToolTurn(
            text=resp.output_text,
            tool_calls=tuple(
                to_call(item, self.model) for item in resp.output if item.type == "function_call"
            ),
            provider=self.provider,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cached_input_tokens=getattr(details, "cached_tokens", 0) or 0,
        )


def to_tool(tool: ToolSpec) -> dict[str, Any]:
    """Not strict: strict mode needs every parameter required, and ours are mostly optional.
    The tool registry checks the arguments itself."""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "strict": False,
    }


def to_input(messages: list[Message]) -> list[dict[str, Any]]:
    """Our messages as Responses API input items. Calls and their outputs are separate items
    joined by `call_id`."""
    items: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            items.append(
                {"type": "function_call_output", "call_id": m.tool_call_id, "output": m.text}
            )
            continue
        if m.text:
            items.append({"role": m.role, "content": m.text})
        for call in m.tool_calls:
            items.append(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                }
            )
    return items


def to_call(item: Any, model: str) -> ToolCall:
    try:
        arguments = json.loads(item.arguments or "{}")
    except json.JSONDecodeError as exc:
        raise LLMError(f"openai/{model} sent arguments for {item.name} that are not JSON") from exc
    if not isinstance(arguments, dict):
        raise LLMError(f"openai/{model} sent arguments for {item.name} that are not an object")
    return ToolCall(id=item.call_id, name=item.name, arguments=arguments)
