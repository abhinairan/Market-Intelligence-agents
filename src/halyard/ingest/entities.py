"""Entity resolution: which brands, product lines and other entities a mention is about.

Deterministic rules from config/<client>/entities.yaml plus the client's product catalogue.
Every result names the rule and the exact string that matched, so it can be checked by hand.
Rule IDs refer to docs/definitions.md; the decisions are logged in docs/er-log.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

from halyard.ingest.records import MentionRecord, ProductRecord
from halyard.settings import ClientConfig, HalyardError


@dataclass(frozen=True)
class BrandRef:
    brand: str  # key in entities.yaml
    matched: str  # the text that matched
    rule: str


@dataclass(frozen=True)
class LineRef:
    brand: str
    line: str
    matched: str
    rule: str


@dataclass(frozen=True)
class SetAside:
    """A brand name in the text that was judged not to be about that brand."""

    kind: str  # unrelated (D-22) or ambiguous (D-23)
    key: str
    brand: str  # the brand it would otherwise have counted for
    matched: str
    rule: str


@dataclass(frozen=True)
class Resolution:
    brands: tuple[BrandRef, ...] = ()
    lines: tuple[LineRef, ...] = ()
    set_aside: SetAside | None = None
    implied: tuple[str, ...] = ()  # implied_competitor_reference, never counted (D-20)

    @property
    def status(self) -> str | None:
        """Why the mention counts for no brand, or None when it names at least one."""
        if self.brands:
            return None
        return self.set_aside.kind if self.set_aside else "unresolved"

    def names(self, brand: str) -> bool:
        return any(b.brand == brand for b in self.brands)

    def lines_of(self, brand: str) -> tuple[str, ...]:
        return tuple(ln.line for ln in self.lines if ln.brand == brand)


def _term(term: str) -> re.Pattern[str]:
    """A whole-word, case-insensitive match, so "BB Nitro" never matches inside "BB50"."""
    body = r"\s+".join(re.escape(part) for part in term.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _first(patterns: list[re.Pattern[str]], text: str) -> str | None:
    hits = [m for p in patterns if (m := p.search(text))]
    return min(hits, key=lambda m: m.start())[0] if hits else None


@dataclass(frozen=True)
class _Line:
    name: str
    terms: list[re.Pattern[str]]
    standalone: list[re.Pattern[str]]


@dataclass(frozen=True)
class _Brand:
    key: str
    rule: str
    references: list[re.Pattern[str]]
    lines: list[_Line]


class EntityResolver:
    def __init__(self, config: dict[str, Any], products: tuple[ProductRecord, ...]):
        self.config = config
        self._brands = [self._brand(b, products) for b in config["brands"]]
        known = {b.key for b in self._brands}
        self._collisions = [
            (kind, c, [_term(t) for t in c[field]])
            for kind, section, field in (
                ("unrelated", "unrelated_entities", "context_terms"),  # D-22 first
                ("ambiguous", "ambiguous", "phrases"),  # D-23
            )
            for c in config.get(section, [])
        ]
        for _, c, _ in self._collisions:
            if c["collides_with"] not in known:
                raise HalyardError(f"entities.yaml: {c['key']} collides with an unknown brand.")
        self._implied = [_term(t) for t in config.get("implied_references", [])]

    @staticmethod
    def _brand(b: dict[str, Any], products: tuple[ProductRecord, ...]) -> _Brand:
        lines = []
        for ln in b.get("lines", []):
            terms = list(ln.get("terms", []))
            if "sub_brand" in ln:
                # D-24: the client's own product names and aliases, straight from its catalogue.
                for p in products:
                    if p.sub_brand == ln["sub_brand"]:
                        terms += [p.product_name, *p.aliases]
            lines.append(
                _Line(
                    ln["name"],
                    [_term(t) for t in dict.fromkeys(terms)],
                    [_term(t) for t in ln.get("standalone_terms", [])],
                )
            )
        if b.get("is_client"):
            mapped = {ln.get("sub_brand") for ln in b.get("lines", [])}
            missing = sorted({p.sub_brand for p in products} - mapped)
            if missing:
                raise HalyardError(f"entities.yaml: no line for catalogue sub-brand(s) {missing}.")
        return _Brand(b["key"], b["rule"], [_term(r) for r in b["references"]], lines)

    def resolve(self, text: str) -> Resolution:
        brands: list[BrandRef] = []
        lines: list[LineRef] = []
        set_aside: SetAside | None = None
        for brand in self._brands:
            # D-20, D-21: the brand's name, or a line term that names the brand by itself.
            named = _first(brand.references, text)
            standalone = {
                ln.name: hit for ln in brand.lines if (hit := _first(ln.standalone, text))
            }
            if not named and not standalone:
                continue  # D-24: a line word without the brand is not a mention of it
            matched = named or next(iter(standalone.values()))
            aside = self._collision(brand.key, text)
            if aside:
                set_aside = set_aside or aside
                continue
            brands.append(BrandRef(brand.key, matched, brand.rule))
            for ln in brand.lines:
                hit = standalone.get(ln.name) or _first(ln.terms, text)
                if hit:
                    lines.append(LineRef(brand.key, ln.name, hit, "D-24"))
        implied = tuple(m[0] for p in self._implied if (m := p.search(text)))
        return Resolution(tuple(brands), tuple(lines), set_aside, implied)

    def brand_named(self, name: str) -> str | None:
        """The brand whose company name is exactly `name` (advertiser and competitor columns)."""
        return next((b["key"] for b in self.config["brands"] if b["name"] == name), None)

    def lines_for(self, brand: str, text: str) -> list[tuple[str, str]]:
        """(line, matched) for a text already known to be this brand's, e.g. its own ad."""
        hits = []
        for b in self._brands:
            if b.key == brand:
                for ln in b.lines:
                    hit = _first(ln.standalone + ln.terms, text)
                    if hit:
                        hits.append((ln.name, hit))
        return hits

    def _collision(self, brand: str, text: str) -> SetAside | None:
        for kind, c, patterns in self._collisions:
            if c["collides_with"] == brand and (hit := _first(patterns, text)):
                return SetAside(kind, c["key"], brand, hit, c["rule"])
        return None


def load_entities_config(client: ClientConfig) -> dict[str, Any]:
    path = client.config_dir / "entities.yaml"
    if not path.exists():
        raise HalyardError(f"No entities config at {path}.")
    return yaml.safe_load(path.read_text())


def resolve_entities(
    mentions: tuple[MentionRecord, ...], products: tuple[ProductRecord, ...], client: ClientConfig
) -> dict[str, Resolution]:
    """mention_id -> Resolution, read from the stored text (never the normalised key, D-12)."""
    resolver = EntityResolver(load_entities_config(client), products)
    return {m.mention_id: resolver.resolve(m.text) for m in mentions}


def mention_status(hygiene_status: str | None, resolution: Resolution) -> str:
    """D-15, D-16: `genuine`, or the one reason the mention is not counted as a conversation."""
    return hygiene_status or resolution.status or "genuine"
