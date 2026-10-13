"""Typed records for every file in a data pack. Loaders build them; nothing here reads files.

Every record carries a `SourceRef`, so any value can be traced to its file and row.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SourceRef:
    file: str  # path relative to the data pack
    row: int  # line number in the file, header = 1 (D-10 cites these)

    def __str__(self) -> str:
        return f"{self.file}:{self.row}"


@dataclass(frozen=True)
class PackSize:
    """A pack string split into units, e.g. "6 x 200ml" = 6 units of 200 ml (D-53)."""

    raw: str
    unit_count: int
    unit_size: float
    unit: str  # g, kg, ml, l or bag


@dataclass(frozen=True)
class MentionRecord:
    mention_id: str
    platform: str
    posted_at: str  # exactly as exported, offset included (D-01)
    date_ist: date  # local date in the client timezone (D-01)
    week_ist: date  # Monday of the reporting week (D-02)
    author_handle: str
    text: str  # as captured, never altered (D-12)
    likes: int
    is_repost_of: str | None
    url: str
    city: str | None  # bracketed city tag, title case (D-26)
    source: SourceRef  # first row the mention appears on
    duplicate_rows: tuple[int, ...] = ()  # rows of byte-identical copies after the first (D-10)
    id_conflict: bool = False  # another row has this ID with different content (D-10)

    @property
    def source_rows(self) -> tuple[int, ...]:
        return (self.source.row, *self.duplicate_rows)


@dataclass(frozen=True)
class ProductRecord:
    sku: str
    product_name: str
    sub_brand: str
    pack: PackSize
    price_inr: int | float  # client catalogue price, undated (D-52)
    aliases: tuple[str, ...]
    launched: date
    source: SourceRef


@dataclass(frozen=True)
class TaxonomyRecord:
    code: str
    name: str
    owner_team: str
    includes: str
    client_rule: str | None
    source: SourceRef


@dataclass(frozen=True)
class PriceRecord:
    competitor: str
    product: str
    pack: PackSize
    price: int | float
    currency: str
    region: str
    captured_at: date  # D-50
    source_url: str
    source: SourceRef


@dataclass(frozen=True)
class AdRecord:
    advertiser: str
    ad_id: str
    first_seen: date
    last_seen: date
    platform: str
    headline: str
    offer: str | None
    landing_url: str
    source: SourceRef


@dataclass(frozen=True)
class PageRecord:
    """A saved web page (brand site or competitor snapshot)."""

    kind: str  # the folder it came from
    title: str
    captured_at: date  # D-50
    url: str
    body: str
    source: SourceRef  # row of the "Captured ... from ..." line


@dataclass
class LoadReport:
    """What the loaders saw, so nothing is collapsed or skipped silently."""

    mention_rows: int = 0
    duplicate_rows: int = 0  # D-10
    id_conflicts: int = 0  # D-10
    other_offsets: int = 0  # timestamps not in the client offset (D-01)
    out_of_window: int = 0  # D-03
    unrecognised_tags: Counter[str] = field(default_factory=Counter)  # D-26


@dataclass(frozen=True)
class DataPack:
    mentions: tuple[MentionRecord, ...]
    products: tuple[ProductRecord, ...]
    taxonomy: tuple[TaxonomyRecord, ...]
    prices: tuple[PriceRecord, ...]
    ads: tuple[AdRecord, ...]
    pages: tuple[PageRecord, ...]
    report: LoadReport
