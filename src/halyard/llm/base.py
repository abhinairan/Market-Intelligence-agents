"""Provider-neutral LLM interface. Pipeline and agent code depend on this, never on an SDK."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from halyard.settings import PROJECT_ROOT, HalyardError

USAGE_LOG = PROJECT_ROOT / "outputs" / "llm_usage.jsonl"


class LLMError(HalyardError):
    """The provider call failed or returned something that does not fit the schema."""


@dataclass(frozen=True)
class JsonResult:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ToolSpec:
    """A tool as the model is told about it. `parameters` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str  # the provider's call ID; the tool's result must carry it back
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    """One entry in a tool-calling conversation, in no provider's format.

    `user` carries text; `assistant` carries text, tool calls or both; `tool` carries one
    tool's result as text, with the ID of the call it answers.
    """

    role: str  # "user", "assistant" or "tool"
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolTurn:
    """One model turn: tool calls to run, or text when the model has finished."""

    text: str
    tool_calls: tuple[ToolCall, ...]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0  # the part of input_tokens read from the provider's cache

    @property
    def message(self) -> Message:
        """This turn as the assistant message to append before the tool results."""
        return Message("assistant", self.text, self.tool_calls)


class LLMClient(ABC):
    provider: str

    def __init__(self, model: str, purpose: str, usage_log: Path | None = USAGE_LOG):
        self.model = model
        self.purpose = purpose  # "label" or "agent", recorded in the usage log
        self.usage_log = usage_log

    @abstractmethod
    def _complete_json(
        self, system: str, user: str, schema: dict[str, Any], name: str, max_tokens: int
    ) -> JsonResult: ...

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        name: str,
        max_tokens: int = 2000,
    ) -> JsonResult:
        """One call whose output is a JSON object matching `schema`.

        `schema` must be strict-compatible: every property listed in `required` and
        `additionalProperties: false` at every level, so all providers accept it unchanged.
        """
        result = self._complete_json(system, user, schema, name, max_tokens)
        missing = [k for k in schema.get("required", []) if k not in result.data]
        if missing:
            raise LLMError(f"{self.provider}/{self.model} output is missing {missing}")
        self._log(result)
        return result

    def run_with_tools(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4000,
        require_tool: bool = False,
        run_id: str | None = None,
    ) -> ToolTurn:
        """One model turn over `messages`, with `tools` on offer.

        The caller runs the returned tool calls, appends `turn.message` and one `tool`
        message per call, and calls again. `require_tool` makes the model call a tool
        rather than answer in text. `run_id` goes to the usage log, so spend can be summed
        per question.
        """
        turn = self._run_with_tools(system, messages, tools, max_tokens, require_tool)
        known = {t.name for t in tools}
        unknown = [c.name for c in turn.tool_calls if c.name not in known]
        if unknown:
            raise LLMError(f"{self.provider}/{self.model} called unknown tools {unknown}")
        if require_tool and not turn.tool_calls:
            raise LLMError(f"{self.provider}/{self.model} answered without calling a tool")
        self._log(turn, run_id)
        return turn

    def _run_with_tools(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
        require_tool: bool,
    ) -> ToolTurn:
        raise LLMError(f"Tool calling is not implemented for the {self.provider} adapter.")

    def _log(self, result: JsonResult | ToolTurn, run_id: str | None = None) -> None:
        if self.usage_log is None:
            return
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "provider": result.provider,
            "model": result.model,
            "purpose": self.purpose,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
        if isinstance(result, ToolTurn):
            row["cached_input_tokens"] = result.cached_input_tokens
        if run_id is not None:
            row["run_id"] = run_id
        with self.usage_log.open("a") as f:
            f.write(json.dumps(row) + "\n")
