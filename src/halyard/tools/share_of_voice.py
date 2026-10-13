"""Share of voice with its method spelled out, and reach next to it (D-41, D-44)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from halyard.store.graph_store import MentionRow
from halyard.tools.base import ToolError, ToolResult
from halyard.tools.context import ToolContext
from halyard.tools.filters import GENUINE, line_brand
from halyard.tools.mentions import exclusions
from halyard.tools.windows import Window, resolve_window

MOST_REPOSTED = 3  # D-44


def _reach(mentions: list[MentionRow]) -> dict[str, Any]:
    """D-44: reposts and likes of a brand's genuine conversations, never added to the count."""
    reposts = sum(m.props.get("repost_count", 0) for m in mentions)
    top = sorted(
        (m for m in mentions if m.props.get("repost_count")),
        key=lambda m: (-m.props["repost_count"], m.mention_id),
    )[:MOST_REPOSTED]
    return {
        "reposts": reposts,
        "reposts_per_100_conversations": round(100 * reposts / len(mentions), 1) if mentions else 0,
        "likes_at_capture_time": sum(m.props["likes"] for m in mentions),
        "most_reposted": [
            {"mention_id": m.mention_id, "reposts": m.props["repost_count"], "text": m.props["text"]}
            for m in top
        ],
    }


def _naive(ctx: ToolContext, brands: list[str], in_window: list[MentionRow]) -> dict[str, Any]:
    """What plain name matching over every exported row would report, and why it differs."""
    names = {b["key"]: b["name"] for b in ctx.names.brands}
    terms = {b: names[b].split()[0].lower() for b in brands}
    rows: Counter[str] = Counter()
    not_counted: dict[str, Counter[str]] = {b: Counter() for b in brands}
    missed: Counter[str] = Counter()
    for m in in_window:
        copies = len(m.props["source_rows"])
        for brand, term in terms.items():
            matched = term in m.props["text"].lower()
            counted = m.status == GENUINE and brand in m.brands
            if matched:
                rows[brand] += copies
                if not counted:
                    not_counted[brand][m.status] += 1
                if copies > 1:
                    not_counted[brand]["duplicate_row"] += copies - 1  # D-10
            elif counted:
                missed[brand] += 1
    total = sum(rows.values())
    return {
        "method": "Rows of the export whose text contains the first word of the brand's name, "
        "any case. No duplicate rows, reposts, spam or unrelated entities removed, and no "
        "sub-brand or alias credited.",
        "total_rows_matched": total,
        "brands": [
            {
                "brand": b,
                "search_term": terms[b],
                "rows": rows[b],
                "share_pct": round(100 * rows[b] / total, 1) if total else None,
                "matched_but_not_counted": dict(not_counted[b].most_common()),
                "counted_but_not_matched": missed[b],
            }
            for b in brands
        ],
    }


def share_of_voice(
    ctx: ToolContext,
    window: Window | None = None,
    brands: list[str] | None = None,
    compare_naive: bool = False,
) -> ToolResult:
    window = window or resolve_window(ctx.client)
    known = {b["key"]: b["name"] for b in ctx.names.brands}
    chosen = list(dict.fromkeys(ctx.names.brand(b) for b in brands)) if brands else list(known)
    if len(chosen) < 2:
        raise ToolError("Share of voice needs at least two brands to compare.")
    in_window = [m for m in ctx.mentions if m.date in window]
    genuine = [m for m in in_window if m.status == GENUINE]
    per_brand = {b: [m for m in genuine if b in m.brands] for b in chosen}
    # D-41: the denominator is the sum of the brands' counts, so the shares add up to 100.
    total = sum(len(ms) for ms in per_brand.values())
    counted = {m.mention_id: m for ms in per_brand.values() for m in ms}

    rows = []
    for brand, ms in sorted(per_brand.items(), key=lambda b: (-len(b[1]), b[0])):
        lines = Counter(ln for m in ms for ln in m.lines if line_brand(ln) == brand)
        rows.append(
            {
                "brand": brand,
                "name": known[brand],
                "conversations": len(ms),
                "share_pct": round(100 * len(ms) / total, 1) if total else None,
                "of_which_by_line": dict(lines.most_common()),  # e.g. a sub-brand's share
                "reach": _reach(ms),
            }
        )
    data: dict[str, Any] = {
        "window": {"start": window.start, "end": window.end},
        "brands": rows,
        "sum_of_brand_counts": total,
        "distinct_conversations": len(counted),
        "naming_more_than_one_brand": sum(
            1 for m in counted.values() if len(set(m.brands) & set(chosen)) > 1
        ),
        "left_out": exclusions(ctx, window).data,
    }
    if compare_naive:
        data["naive"] = _naive(ctx, chosen, in_window)
    note = (
        "Share of voice = a brand's genuine original conversations / the sum of the compared "
        "brands' genuine original conversations in the window (D-41). Left out: reposts "
        "(D-11), spam (D-13), mentions of an unrelated or ambiguous entity (D-22, D-23) and "
        "duplicate rows (D-10); `left_out` gives their sizes. A sub-brand counts for its brand "
        "(D-21). A mention naming two brands counts for each, so the sum of brand counts can "
        "exceed the distinct conversations (D-25). Reach is reported next to the counts and "
        "never added to them; likes are as at capture time (D-44). "
        f"Window: {window.describe()}, dates in the client's local time (D-01)."
    )
    if compare_naive:
        note += (
            " `naive` is what plain name matching over all rows gives. It is shown for "
            "comparison only and is not our figure (D-41)."
        )
    return ToolResult(data, note, ctx.client.as_of, mention_ids=sorted(counted))
