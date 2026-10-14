"""Loaders: read every file in the data pack into typed records with file and row provenance.

They parse and annotate only. Hygiene (reposts, spam), entity resolution and labelling are
later steps and never happen here. Rule IDs refer to docs/definitions.md.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from halyard.ingest.records import (
    AdRecord,
    DataPack,
    LoadReport,
    MentionRecord,
    PackSize,
    PageRecord,
    PriceRecord,
    ProductRecord,
    SourceRef,
    TaxonomyRecord,
)
from halyard.settings import ClientConfig, HalyardError

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

MENTION_COLUMNS = (
    "mention_id", "platform", "posted_at", "author_handle", "text", "likes", "is_repost_of", "url",
)  # fmt: skip
PRODUCT_COLUMNS = ("sku", "product_name", "sub_brand", "pack", "price_inr", "aliases", "launched")
TAXONOMY_COLUMNS = ("code", "name", "owner_team", "includes", "client_rule")
PRICE_COLUMNS = (
    "competitor", "product", "pack", "price", "currency", "region", "captured_at", "source_url",
)  # fmt: skip
AD_COLUMNS = (
    "advertiser", "ad_id", "first_seen", "last_seen", "platform", "headline", "offer",
    "landing_url",
)  # fmt: skip

_OFFSET = re.compile(r"([+-])(\d{2}):(\d{2})")
_BRACKET = re.compile(r"\(([^()]+)\)")
_PACK = re.compile(r"(?:(\d+)\s*x\s*)?(\d+(?:\.\d+)?)\s*(kg|g|ml|l|bags?)(?:\s+\w+)?", re.IGNORECASE)
_CAPTURED = re.compile(r"Captured (\d{4}-\d{2}-\d{2}) from (\S+)")


class LoadError(HalyardError):
    """A file in the data pack does not have the shape the loaders expect."""


def parse_offset(offset: str) -> timezone:
    """`+05:30` as a fixed-offset timezone."""
    m = _OFFSET.fullmatch(offset)
    if not m:
        raise LoadError(f"timezone must look like +05:30, not {offset!r}")
    delta = timedelta(hours=int(m[2]), minutes=int(m[3]))
    return timezone(delta if m[1] == "+" else -delta)


def week_start(day: date, week_starts_on: str) -> date:
    """D-02: the day that names the reporting week containing `day`."""
    return day - timedelta(days=(day.weekday() - WEEKDAYS.index(week_starts_on.lower())) % 7)


def parse_pack(raw: str, where: SourceRef) -> PackSize:
    """`6 x 200ml`, `250g`, `10 bags` or `100g jar` as unit count, unit size and unit."""
    m = _PACK.fullmatch(raw.strip())
    if not m:
        raise LoadError(f"{where}: cannot read pack size {raw!r}")
    unit = m[3].lower()
    if unit.startswith("bag"):
        if m[1]:
            raise LoadError(f"{where}: cannot read pack size {raw!r}")
        return PackSize(raw, int(m[2]), 1, "bag")
    return PackSize(raw, int(m[1] or 1), _number(m[2], where), unit)


def extract_city(text: str, cities: dict[str, str]) -> tuple[str | None, list[str]]:
    """D-26: the first bracketed tag that is a configured city, plus any other bracketed tags."""
    city, others = None, []
    for tag in _BRACKET.findall(text):
        known = cities.get(tag.strip().casefold())
        if known and city is None:
            city = known
        elif not known:
            others.append(tag.strip())
    return city, others


def _number(value: str, where: SourceRef) -> int | float:
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            raise LoadError(f"{where}: {value!r} is not a number") from None


def _date(value: str, where: SourceRef) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise LoadError(f"{where}: {value!r} is not a YYYY-MM-DD date") from None


def _rows(pack_dir: Path, name: str, columns: tuple[str, ...]) -> Iterator[tuple[SourceRef, dict]]:
    """CSV rows with their line number. `newline=""` keeps values byte-exact (CRLF pack)."""
    path = pack_dir / name
    if not path.exists():
        raise LoadError(f"{name} is missing from the data pack at {pack_dir}")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = tuple(next(reader, ()))
        if header != columns:
            raise LoadError(f"{name}: expected columns {list(columns)}, found {list(header)}")
        for row in reader:
            where = SourceRef(name, reader.line_num)
            if len(row) != len(columns):
                raise LoadError(f"{where}: expected {len(columns)} values, found {len(row)}")
            yield where, dict(zip(columns, row, strict=True))


def load_mentions(client: ClientConfig, name: str) -> tuple[tuple[MentionRecord, ...], LoadReport]:
    tz = parse_offset(client.timezone)
    cities = {c.casefold(): c for c in client.raw.get("city_tags", [])}
    report = LoadReport()
    by_id: dict[str, list[tuple[dict, MentionRecord]]] = {}
    for where, row in _rows(client.data_pack, name, MENTION_COLUMNS):
        report.mention_rows += 1
        seen = by_id.setdefault(row["mention_id"], [])
        # D-10: a byte-identical copy collapses into the first row and only adds its row number.
        copy_of = next((i for i, (first, _) in enumerate(seen) if first == row), None)
        if copy_of is not None:
            first, record = seen[copy_of]
            seen[copy_of] = (
                first,
                replace(record, duplicate_rows=(*record.duplicate_rows, where.row)),
            )
            report.duplicate_rows += 1
            continue

        try:
            posted = datetime.fromisoformat(row["posted_at"])
        except ValueError:
            raise LoadError(f"{where}: posted_at {row['posted_at']!r} is not ISO 8601") from None
        if posted.tzinfo is None:
            raise LoadError(f"{where}: posted_at {row['posted_at']!r} has no UTC offset")
        if posted.utcoffset() != tz.utcoffset(None):
            report.other_offsets += 1
        # D-01: bucket on the client's local clock time, never on UTC. For a timestamp already
        # in the client offset, astimezone leaves the clock time untouched.
        local_date = posted.astimezone(tz).date()
        if not client.window_start <= local_date <= client.window_end:
            report.out_of_window += 1
        if not row["likes"].isdecimal():
            raise LoadError(f"{where}: likes {row['likes']!r} is not a whole number")
        city, other_tags = extract_city(row["text"], cities)
        report.unrecognised_tags.update(other_tags)

        seen.append(
            (
                row,
                MentionRecord(
                    mention_id=row["mention_id"],
                    platform=row["platform"],
                    posted_at=row["posted_at"],
                    date_ist=local_date,
                    week_ist=week_start(local_date, client.week_starts_on),
                    author_handle=row["author_handle"],
                    text=row["text"],
                    likes=int(row["likes"]),
                    is_repost_of=row["is_repost_of"] or None,
                    url=row["url"],
                    city=city,
                    source=where,
                ),
            )
        )

    mentions: list[MentionRecord] = []
    for versions in by_id.values():
        # D-10: rows that share an ID but differ are all kept and flagged for review.
        if len(versions) > 1:
            report.id_conflicts += 1
        mentions += [replace(m, id_conflict=len(versions) > 1) for _, m in versions]
    mentions.sort(key=lambda m: m.source.row)
    return tuple(mentions), report


def load_products(pack_dir: Path, name: str) -> tuple[ProductRecord, ...]:
    return tuple(
        ProductRecord(
            sku=row["sku"],
            product_name=row["product_name"],
            sub_brand=row["sub_brand"],
            pack=parse_pack(row["pack"], where),
            price_inr=_number(row["price_inr"], where),
            aliases=tuple(a.strip() for a in row["aliases"].split("|") if a.strip()),
            launched=_date(row["launched"], where),
            source=where,
        )
        for where, row in _rows(pack_dir, name, PRODUCT_COLUMNS)
    )


def load_taxonomy(pack_dir: Path, name: str) -> tuple[TaxonomyRecord, ...]:
    return tuple(
        TaxonomyRecord(
            code=row["code"],
            name=row["name"],
            owner_team=row["owner_team"],
            includes=row["includes"],
            client_rule=row["client_rule"] or None,
            source=where,
        )
        for where, row in _rows(pack_dir, name, TAXONOMY_COLUMNS)
    )


def load_prices(pack_dir: Path, name: str) -> tuple[PriceRecord, ...]:
    return tuple(
        PriceRecord(
            competitor=row["competitor"],
            product=row["product"],
            pack=parse_pack(row["pack"], where),
            price=_number(row["price"], where),
            currency=row["currency"],
            region=row["region"],
            captured_at=_date(row["captured_at"], where),
            source_url=row["source_url"],
            source=where,
        )
        for where, row in _rows(pack_dir, name, PRICE_COLUMNS)
    )


def load_ads(pack_dir: Path, name: str) -> tuple[AdRecord, ...]:
    return tuple(
        AdRecord(
            advertiser=row["advertiser"],
            ad_id=row["ad_id"],
            first_seen=_date(row["first_seen"], where),
            last_seen=_date(row["last_seen"], where),
            platform=row["platform"],
            headline=row["headline"],
            offer=row["offer"] or None,
            landing_url=row["landing_url"],
            source=where,
        )
        for where, row in _rows(pack_dir, name, AD_COLUMNS)
    )


def load_pages(pack_dir: Path, folder: str) -> tuple[PageRecord, ...]:
    """Saved pages: a `# title` line, a `Captured <date> from <url>` line, then the body."""
    if not (pack_dir / folder).is_dir():
        raise LoadError(f"{folder}/ is missing from the data pack at {pack_dir}")
    pages = []
    for path in sorted((pack_dir / folder).glob("*.md")):
        name = f"{folder}/{path.name}"
        lines = path.read_text(encoding="utf-8").splitlines()
        title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), None)
        captured = next(
            ((i, m) for i, ln in enumerate(lines, 1) if (m := _CAPTURED.match(ln))), None
        )
        if title is None or captured is None:
            # D-50: a page without a capture date cannot become a dated observation.
            raise LoadError(f"{name}: needs a '# title' line and a 'Captured <date> from <url>' line")
        row, m = captured
        where = SourceRef(name, row)
        body_row = next((i for i in range(row + 1, len(lines) + 1) if lines[i - 1].strip()), row)
        pages.append(
            PageRecord(
                kind=folder,
                title=title,
                captured_at=_date(m[1], where),
                url=m[2],
                body="\n".join(lines[body_row - 1 :]).rstrip() if body_row > row else "",
                body_row=body_row,
                source=where,
            )
        )
    return tuple(pages)


def load_pack(client: ClientConfig) -> DataPack:
    """Every file named under `files` and `page_folders` in the client config."""
    files = client.raw["files"]
    mentions, report = load_mentions(client, files["mentions"])
    return DataPack(
        mentions=mentions,
        products=load_products(client.data_pack, files["products"]),
        taxonomy=load_taxonomy(client.data_pack, files["taxonomy"]),
        prices=load_prices(client.data_pack, files["pricing"]),
        ads=load_ads(client.data_pack, files["ads"]),
        pages=tuple(
            page
            for folder in client.raw["page_folders"]
            for page in load_pages(client.data_pack, folder)
        ),
        report=report,
    )
