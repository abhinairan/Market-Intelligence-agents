"""What every tool returns, and how a tool says it cannot answer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from halyard.settings import HalyardError


class ToolError(HalyardError):
    """A tool could not answer as asked. The message says why and what would work, since the
    reader is the agent that made the call."""


@dataclass(frozen=True)
class ToolResult:
    """No tool returns a number without its evidence (docs/PLAN.md §4)."""

    data: Any
    method_note: str  # how the figures were counted, with rule IDs
    as_of: date  # D-03: the date relative phrases were read against
    mention_ids: list[str] = field(default_factory=list)  # the mentions behind the figures
    source_refs: list[str] = field(default_factory=list)  # `file:row` for everything else
    # The mentions behind each part of a breakdown (a code on a line, a status on a day), so a
    # figure can be traced to its own mentions and not only to the whole result's. Kept in
    # the log and the run; not sent to the model.
    mention_id_groups: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "data": _plain(self.data),
            "mention_ids": self.mention_ids,
            "source_refs": self.source_refs,
            "method_note": self.method_note,
            "as_of": self.as_of.isoformat(),
        }
        if self.mention_id_groups:
            out["mention_id_groups"] = self.mention_id_groups
        return out


def _plain(value: Any) -> Any:
    """Dates as ISO strings, so a result can be sent to a model or written to a log."""
    if isinstance(value, dict):
        return {_plain(k) if isinstance(k, date) else str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value.isoformat() if isinstance(value, date) else value
