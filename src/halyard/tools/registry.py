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
from halyard.tools import competitors, mentions, sentiment
from halyard.tools.base import ToolError, ToolResult
from halyard.tools.context import ToolContext
from halyard.tools.filters import BRAND_LEVEL, MentionFilter
from halyard.tools.share_of_voice import share_of_voice
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
    genuine_only: bool = False  # the metric is defined on genuine conversations only
    required: tuple[str, ...] = ()

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema of the arguments, the form both LLM adapters start from."""
        filters = {
            k: v
            for k, v in FILTER_PARAMETERS.items()
            if not (self.genuine_only and k == "include_excluded")
        }
        properties = (
            (filters if self.takes_filter else {})
            | (WINDOW_PARAMETERS if self.takes_window else {})
            | self.own_parameters
        )
        return {
            "type": "object",
            "properties": properties,
            "required": list(self.required),
            "additionalProperties": False,
        }


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
        Tool(
            "sentiment_trend",
            "Sentiment week by week for a brand or a product line: net score, % negative and "
            "the counts behind them. For a line it also returns the brand overall and the "
            "brand without that line. Set `split_by_line` with a brand to see every line side "
            "by side, which shows what a brand-level figure hides.",
            sentiment.sentiment_trend,
            {
                "split_by_line": {
                    "type": "boolean",
                    "description": "With a brand and no line: one series per line.",
                }
            },
            genuine_only=True,
        ),
        Tool(
            "complaint_breakdown",
            "Complaints by the client's own complaint codes, ranked, each with its owner team, "
            "counts by product line and by week, and example mentions. Use for 'what are "
            "people complaining about' and for routing a complaint to a team.",
            sentiment.complaint_breakdown,
            {
                "top_n": {"type": "integer", "description": "Only the top N codes. Default all."},
                "examples": {
                    "type": "integer",
                    "description": "Example mentions per code. Default 2.",
                },
            },
            genuine_only=True,
        ),
        Tool(
            "share_of_voice",
            "Share of voice between brands over a window: each brand's genuine conversations, "
            "its share, what was left out and why, and reach (reposts, likes) alongside. Use "
            "for any share-of-voice question and to explain how the figure was counted. Set "
            "`compare_naive` only when asked why the figure differs from another tool's or "
            "vendor's: it adds what plain name matching would report.",
            share_of_voice,
            {
                "brands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Brands to compare. Default: the client and every competitor.",
                },
                "compare_naive": {
                    "type": "boolean",
                    "description": "Also return the naive name-matching figure. Default false.",
                },
            },
            takes_filter=False,
        ),
        Tool(
            "competitor_observations",
            "Dated facts about a brand from its own pages and the pricing export: prices, "
            "free-shipping thresholds, launches and offers, each with its capture date and "
            "age. Also returns changes between observations as date ranges. Use for what a "
            "competitor launched, charges or changed, and when.",
            competitors.competitor_observations,
            {
                "brand": FILTER_PARAMETERS["brand"],
                "line": {"type": "string", "description": "Product line, e.g. `Saltmarsh Nitro`."},
                "kind": {
                    "type": "string",
                    "enum": ["price", "free_shipping_threshold", "launch", "offer"],
                },
            },
            takes_filter=False,
            takes_window=False,
        ),
        Tool(
            "price_compare",
            "Compare the price of `a` with `b` like with like: same market and currency, per "
            "unit. Returns the ratio of a's price to b's, each price's date, and any price "
            "that could not be compared and why. Use for 'what does X cost compared with "
            "ours' and to check a price claim in an ad.",
            competitors.price_compare,
            {
                "a": {"type": "string", "description": "Product line or product, e.g. "
                                                       "`Saltmarsh Nitro`."},
                "b": {"type": "string", "description": "What to compare it with, e.g. "
                                                       "`Brewbird Nitro`."},
                "region": {"type": "string", "description": "Market code, e.g. `IN`. Default: "
                                                            "every market both are priced in."},
                "claimed_ratio": {
                    "type": "number",
                    "description": "A claim to check, as a's price over b's: 0.5 for 'half the "
                    "price'.",
                },
                "include_offers": {
                    "type": "boolean",
                    "description": "Also apply a's stated offers, kept apart from list price.",
                },
            },
            takes_filter=False,
            takes_window=False,
            required=("a", "b"),
        ),
        Tool(
            "competitor_ads",
            "Competitor ads from the ad-library export, grouped by headline: how many, on "
            "which platforms, when first and last seen, whether still running, and any offer. "
            "Use for what a competitor is advertising and claiming.",
            competitors.competitor_ads,
            {
                "brand": {"type": "string", "description": "The advertiser."},
                "line": {"type": "string", "description": "Product line the ad promotes."},
                "text": {"type": "string", "description": "Words to find in the headline or "
                                                          "offer."},
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
    missing = [k for k in tool.required if k not in given]
    if missing:
        raise ToolError(f"{name} needs {', '.join(missing)}.")

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
