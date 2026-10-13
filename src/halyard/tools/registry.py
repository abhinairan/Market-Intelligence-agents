"""Every tool's name, description and parameters, written once.

Agents see tools only through this registry: P4 translates each entry into a provider's
tool format, and `run_tool` is the single way a tool is called. It turns flat JSON arguments
into a filter and a window, runs the tool, and logs the call with a result ID so any answer
can be traced to the calls behind it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from halyard.settings import PROJECT_ROOT
from halyard.tools import mentions
from halyard.tools.base import ToolError, ToolResult
from halyard.tools.context import ToolContext
from halyard.tools.filters import BRAND_LEVEL, MentionFilter
from halyard.tools.windows import resolve_window

TOOL_LOG = PROJECT_ROOT / "outputs" / "tool_calls.jsonl"

FILTER_PARAMETERS: dict[str, dict[str, Any]] = {
    "brand": {
        "type": "string",
        "description": "Brand key or name, e.g. `brewbird` or `Saltmarsh`. Omit for all brands.",
    },
    "line": {
        "type": "string",
        "description": "Product line, e.g. `Nitro` or `Saltmarsh Nitro`, or "
        f"`{BRAND_LEVEL}` for mentions that name the brand and none of its lines.",
    },
    "platform": {"type": "string", "description": "Platform as the export names it."},
    "city": {"type": "string", "description": "City tag on the mention; most have none."},
    "sentiment": {
        "type": "string",
        "enum": ["positive", "neutral", "negative", "unlabelled"],
    },
    "code": {"type": "string", "description": "One of the client's complaint codes, e.g. `TST`."},
    "include_excluded": {
        "type": "boolean",
        "description": "Also count reposts, spam and unrelated mentions. Default false: only "
        "genuine conversations are counted.",
    },
}

WINDOW_PARAMETERS: dict[str, dict[str, Any]] = {
    "start": {"type": "string", "description": "First day, YYYY-MM-DD. Default: start of data."},
    "end": {"type": "string", "description": "Last day, YYYY-MM-DD. Default: end of data."},
    "last_weeks": {
        "type": "integer",
        "description": "The N most recent full reporting weeks. Use instead of start and end.",
    },
    "week": {
        "type": "string",
        "description": "Any day of one reporting week, YYYY-MM-DD. Use instead of start and end.",
    },
}

FILTER_FIELDS = tuple(f.name for f in fields(MentionFilter))
assert set(FILTER_FIELDS) == set(FILTER_PARAMETERS)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[..., ToolResult]
    own_parameters: dict[str, dict[str, Any]]  # beyond the shared filter and window ones
    takes_filter: bool = True
    takes_window: bool = True

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema of the arguments, the form both LLM adapters start from."""
        properties = (
            (FILTER_PARAMETERS if self.takes_filter else {})
            | (WINDOW_PARAMETERS if self.takes_window else {})
            | self.own_parameters
        )
        return {"type": "object", "properties": properties, "additionalProperties": False}


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "count_mentions",
            "Count consumer mentions, optionally grouped. Use for any 'how many' question about "
            "conversations. Returns the total, the distinct authors and the mention IDs counted.",
            mentions.count_mentions,
            {"group_by": {"type": "string", "enum": list(mentions.GROUP_BY)}},
        ),
        Tool(
            "get_mentions",
            "Read mentions: their text, author, date, sentiment, complaint codes and status. Use "
            "for examples and quotes, or pass `ids` to look up specific mentions.",
            mentions.get_mentions,
            {
                "ids": {"type": "array", "items": {"type": "string"},
                        "description": "Mention IDs to look up. Filters are ignored."},
                "limit": {"type": "integer", "description": "How many to return. Default 10."},
                "sort": {"type": "string", "enum": list(mentions.SORTS),
                         "description": "Default `likes`: most liked first."},
            },
        ),
        Tool(
            "exclusions",
            "What was left out of the counts and why: reposts, spam, mentions of an unrelated "
            "or ambiguous entity, duplicate rows. Use to explain how a number was counted.",
            mentions.exclusions,
            {},
            takes_filter=False,
        ),
        Tool(
            "daily_activity",
            "Mentions per day against the median day, with unusual days broken down into "
            "genuine conversations, spam, reposts and the most repeated texts. Use for 'what "
            "happened on <date>' and for spikes. Pass `day` to break down one day.",
            mentions.daily_activity,
            {
                "day": {"type": "string", "description": "One day to break down, YYYY-MM-DD."},
                "top": {"type": "integer", "description": "Repeated texts to list. Default 5."},
            },
            takes_filter=False,
        ),
    )
}


def run_tool(
    ctx: ToolContext, name: str, args: dict[str, Any], log: Path | None = TOOL_LOG
) -> dict[str, Any]:
    """Call a tool with JSON arguments. Returns the result as JSON-ready data with its ID."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"There is no tool named {name!r}. Tools: {', '.join(TOOLS)}.")
    allowed = tool.parameters["properties"]
    unknown = sorted(set(args) - set(allowed))
    if unknown:
        raise ToolError(f"{name} takes no argument {unknown}. It takes: {', '.join(allowed)}.")
    given = {k: v for k, v in args.items() if v is not None}

    kwargs = {k: v for k, v in given.items() if k in tool.own_parameters}
    if tool.takes_filter:
        kwargs["flt"] = MentionFilter(**{k: given[k] for k in FILTER_FIELDS if k in given})
    if tool.takes_window:
        kwargs["window"] = resolve_window(
            ctx.client, **{k: given[k] for k in WINDOW_PARAMETERS if k in given}
        )
    result = tool.run(ctx, **kwargs).to_dict()

    # The same call over the same graph gets the same ID.
    body = json.dumps({"tool": name, "args": given, "result": result}, sort_keys=True)
    result_id = "R-" + hashlib.sha256(body.encode()).hexdigest()[:8]
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        entry = {"result_id": result_id, "at": datetime.now().astimezone().isoformat(),
                 "tool": name, "args": given, "result": result}  # fmt: skip
        with log.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"result_id": result_id} | result
