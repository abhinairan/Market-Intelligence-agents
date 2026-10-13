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

    def _log(self, result: JsonResult) -> None:
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
        with self.usage_log.open("a") as f:
            f.write(json.dumps(row) + "\n")
