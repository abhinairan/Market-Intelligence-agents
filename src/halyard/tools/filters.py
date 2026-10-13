"""Mention filters shared by every tool, and the names a caller may use in them.

Callers are agents, so a name is matched loosely (key or name, any case) and a value that
matches nothing fails with the values that would have worked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from halyard.store.graph_store import GraphStore, MentionRow
from halyard.tools.base import ToolError
from halyard.tools.windows import Window

GENUINE = "genuine"  # D-15
BRAND_LEVEL = "brand-level"  # as a line filter: names the brand and none of its lines (D-24)


def _fold(value: str) -> str:
    return " ".join(value.lower().split())


class Names:
    """Brand, line and complaint-code names, read from the graph."""

    def __init__(self, store: GraphStore):
        self.brands = store.nodes("Brand")
        self.lines = store.nodes("ProductLine")
        self.codes = store.nodes("ComplaintCode")

    @property
    def client_brand(self) -> str:
        return next(b["key"] for b in self.brands if b.get("is_client"))

    def brand(self, value: str) -> str:
        v = _fold(value)
        hits = [b["key"] for b in self.brands if v in (_fold(b["key"]), _fold(b["name"]))]
        # "Saltmarsh" for "Saltmarsh Coffee": the first word of the name is enough.
        hits = hits or [b["key"] for b in self.brands if _fold(b["name"]).split()[0] == v]
        return _one(hits, value, "brand", [b["key"] for b in self.brands])

    def line(self, value: str, brand: str | None = None) -> str:
        """A ProductLine key (`<brand key>:<line name>`) from a key, a name, or brand + name."""
        v = _fold(value)
        pool = [ln for ln in self.lines if brand is None or line_brand(ln["key"]) == brand]
        hits = [
            ln["key"] for ln in pool
            if v in (_fold(ln["key"]), _fold(ln["name"]),
                     _fold(f"{line_brand(ln['key'])} {ln['name']}"))
        ]  # fmt: skip
        # "nitro" for "Saltmarsh Nitro", once the brand has narrowed the choice.
        hits = hits or [ln["key"] for ln in pool if _fold(ln["name"]).endswith(f" {v}")]
        return _one(hits, value, "product line", [ln["key"] for ln in pool])

    def code(self, value: str) -> str:
        v = _fold(value)
        hits = [c["code"] for c in self.codes if v in (_fold(c["code"]), _fold(c["name"]))]
        return _one(hits, value, "complaint code", [c["code"] for c in self.codes])


def line_brand(line_key: str) -> str:
    return line_key.split(":", 1)[0]


def _one(hits: list[str], value: str, what: str, options: list[str]) -> str:
    if len(hits) == 1:
        return hits[0]
    problem = "matches more than one" if hits else "is not a known"
    raise ToolError(f"{value!r} {problem} {what}. Use one of: {', '.join(hits or options)}.")


@dataclass(frozen=True)
class MentionFilter:
    brand: str | None = None
    line: str | None = None  # a line, or BRAND_LEVEL
    platform: str | None = None
    city: str | None = None
    sentiment: str | None = None
    code: str | None = None
    include_excluded: bool = False  # D-16: only genuine conversations unless asked


def resolve_filter(mentions: list[MentionRow], names: Names, flt: MentionFilter) -> MentionFilter:
    """The same filter in stored spellings: keys for brand, line and code. Unknown values
    raise; they never quietly match nothing."""
    brand = names.brand(flt.brand) if flt.brand else None
    line = None
    if flt.line and _fold(flt.line) == BRAND_LEVEL:
        brand, line = brand or names.client_brand, BRAND_LEVEL
    elif flt.line:
        line = names.line(flt.line, brand)
    return MentionFilter(
        brand=brand,
        line=line,
        platform=_choice(flt.platform, mentions, "platform"),
        city=_choice(flt.city, mentions, "city"),
        sentiment=_choice(flt.sentiment, mentions, "sentiment"),
        code=names.code(flt.code) if flt.code else None,
        include_excluded=flt.include_excluded,
    )


def select_mentions(
    mentions: list[MentionRow], names: Names, flt: MentionFilter, window: Window | None = None
) -> list[MentionRow]:
    """The mentions a filter keeps, in the order given."""
    f = resolve_filter(mentions, names, flt)

    def keep(m: MentionRow) -> bool:
        if not f.include_excluded and m.status != GENUINE:
            return False
        if window is not None and m.date not in window:
            return False
        if f.brand and f.brand not in m.brands:
            return False
        if f.line == BRAND_LEVEL:  # none of this brand's lines
            if any(line_brand(ln) == f.brand for ln in m.lines):
                return False
        elif f.line and f.line not in m.lines:
            return False
        if f.code and f.code not in m.codes:
            return False
        return all(
            want is None or m.props.get(prop) == want
            for prop, want in (
                ("platform", f.platform), ("city", f.city), ("sentiment", f.sentiment),
            )
        )  # fmt: skip

    return [m for m in mentions if keep(m)]


def _choice(value: str | None, mentions: list[MentionRow], prop: str) -> Any:
    """The stored spelling of a value, matched in any case against the values in the data."""
    if value is None:
        return None
    present = {_fold(str(m.props[prop])): m.props[prop] for m in mentions if prop in m.props}
    if _fold(value) not in present:
        options = ", ".join(sorted(str(v) for v in present.values()))
        raise ToolError(f"{value!r} is not a {prop} in the data. Use one of: {options}.")
    return present[_fold(value)]
