"""Mention hygiene: normalised text, reposts, spam bursts and double posts.

Works on loaded mentions and returns annotations; it never drops or edits a mention (D-16).
Parameters come from config/<client>/hygiene.yaml. Rule IDs refer to docs/definitions.md.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import yaml

from halyard.ingest.records import MentionRecord
from halyard.settings import ClientConfig, HalyardError

_EMOJI_JOINERS = "️‍"  # variation selector and zero-width joiner inside emoji


@dataclass(frozen=True)
class Repost:
    basis: str  # tool_flag, or the basis of a configured text marker (D-11)
    method: str  # extracted (tool flag) or inferred (text marker)
    quoted_handle: str | None
    original_id: str | None  # None when no original could be linked


@dataclass(frozen=True)
class SpamBurst:
    normalised_text: str
    first_posted_at: str
    last_posted_at: str
    handles: tuple[str, ...]
    mention_ids: tuple[str, ...]


@dataclass(frozen=True)
class Hygiene:
    normalised: dict[str, str]  # mention_id -> normalised text (D-12)
    reposts: dict[str, Repost]  # D-11
    bursts: tuple[SpamBurst, ...]  # D-13
    spam: dict[str, int]  # mention_id -> index into bursts
    double_posts: dict[str, str]  # mention_id -> the earlier post that counts (D-17)
    account_classes: dict[str, str]  # handle -> class, only for spam authors (D-13)
    repost_counts: dict[str, int]  # original mention_id -> reposts linked to it (D-44)

    def status(self, mention_id: str) -> str | None:
        """The hygiene reason a mention is not a conversation, or None (D-15)."""
        if mention_id in self.spam:
            return "spam"
        if mention_id in self.reposts:
            return "repost"
        if mention_id in self.double_posts:
            return "double_post"
        return None


def load_hygiene_config(client: ClientConfig) -> dict[str, Any]:
    path = client.config_dir / "hygiene.yaml"
    if not path.exists():
        raise HalyardError(f"No hygiene config at {path}.")
    return yaml.safe_load(path.read_text())


class Normaliser:
    """D-12: a matching key for a text. The stored text is never changed."""

    def __init__(self, config: dict[str, Any], cities: Iterable[str]):
        norm = config["normalise"]
        self._markers = [
            re.compile(m["pattern"], re.IGNORECASE) for m in config["reposts"]["markers"]
        ]
        fillers = "|".join(re.escape(f.lower()) for f in norm["leading_fillers"])
        self._lead = re.compile(rf"^(?:{fillers})[,:]?\s+") if fillers else None
        # A word-like decoration ("lol", "#coffee") must stand alone; "!!" may touch a word.
        trailing = [
            (r"(?:^|\s)" if d[0].isalnum() or d[0] == "#" else "") + re.escape(d.lower())
            for d in norm["trailing_decorations"]
        ]
        trailing += [rf"(?:^|\s)\({re.escape(c.lower())}\)" for c in cities]
        self._trail = re.compile(rf"(?:{'|'.join(trailing)})$") if trailing else None

    def __call__(self, text: str) -> str:
        out = text
        for marker in self._markers:
            out = marker.sub("", out)
        out = out.lower().strip()
        while True:
            before = out
            if self._lead:
                out = self._lead.sub("", out)
            if self._trail:
                out = self._trail.sub("", out)
            out = _strip_trailing_emoji(out).strip()
            if out == before:
                return out


def _strip_trailing_emoji(text: str) -> str:
    end = len(text)
    while end and (
        text[end - 1] in _EMOJI_JOINERS or unicodedata.category(text[end - 1]) in ("So", "Sk")
    ):
        end -= 1
    return text[:end]


def _posted(m: MentionRecord) -> datetime:
    # Offset-aware, so ordering and gaps are exact; nothing is bucketed here (D-01).
    return datetime.fromisoformat(m.posted_at)


def find_reposts(
    mentions: tuple[MentionRecord, ...], normalised: dict[str, str], config: dict[str, Any]
) -> dict[str, Repost]:
    """D-11: (a) the tool flag, then (b) and (c) the configured text markers."""
    ids = {m.mention_id for m in mentions}
    markers = [(m["basis"], re.compile(m["pattern"])) for m in config["reposts"]["markers"]]
    by_handle_text: dict[tuple[str, str], list[MentionRecord]] = defaultdict(list)
    for m in mentions:
        by_handle_text[(m.author_handle, normalised[m.mention_id])].append(m)

    reposts: dict[str, Repost] = {}
    for m in mentions:
        if m.is_repost_of:
            original = m.is_repost_of if m.is_repost_of in ids else None
            reposts[m.mention_id] = Repost("tool_flag", "extracted", None, original)
            continue
        for basis, pattern in markers:
            hit = pattern.search(m.text)
            if not hit:
                continue
            handle = hit["handle"]
            # The original is the quoted handle's latest earlier post with the same text.
            earlier = [
                o
                for o in by_handle_text[(handle, normalised[m.mention_id])]
                if _posted(o) < _posted(m)
            ]
            original = max(earlier, key=_posted).mention_id if earlier else None
            reposts[m.mention_id] = Repost(basis, "inferred", handle, original)
            break
    return reposts


def find_spam(
    mentions: tuple[MentionRecord, ...], normalised: dict[str, str], config: dict[str, Any]
) -> tuple[tuple[SpamBurst, ...], dict[str, int]]:
    """D-13: identical promotional text from enough distinct handles inside the window."""
    spam = config["spam"]
    promo = [re.compile(p) for p in spam["promo_patterns"]]
    window = timedelta(hours=spam["window_hours"])
    by_text: dict[str, list[MentionRecord]] = defaultdict(list)
    for m in mentions:
        if any(p.search(m.text) for p in promo):
            by_text[normalised[m.mention_id]].append(m)

    bursts: list[SpamBurst] = []
    assigned: dict[str, int] = {}
    for text, group in sorted(by_text.items()):
        group.sort(key=lambda m: (_posted(m), m.mention_id))
        hit: set[str] = set()
        for i, first in enumerate(group):
            in_window = [m for m in group[i:] if _posted(m) - _posted(first) <= window]
            if len({m.author_handle for m in in_window}) >= spam["min_handles"]:
                hit.update(m.mention_id for m in in_window)
        members = [m for m in group if m.mention_id in hit]
        if not members:
            continue
        for m in members:
            assigned[m.mention_id] = len(bursts)
        bursts.append(
            SpamBurst(
                normalised_text=text,
                first_posted_at=members[0].posted_at,
                last_posted_at=members[-1].posted_at,
                handles=tuple(sorted({m.author_handle for m in members})),
                mention_ids=tuple(m.mention_id for m in members),
            )
        )
    return tuple(bursts), assigned


def find_double_posts(
    mentions: tuple[MentionRecord, ...],
    normalised: dict[str, str],
    skip: set[str],
    config: dict[str, Any],
) -> dict[str, str]:
    """D-17: same author, text and platform within the window; the earliest counts."""
    window = timedelta(hours=config["double_post"]["window_hours"])
    groups: dict[tuple[str, str, str], list[MentionRecord]] = defaultdict(list)
    for m in mentions:
        if m.mention_id not in skip:
            groups[(m.author_handle, m.platform, normalised[m.mention_id])].append(m)

    doubles: dict[str, str] = {}
    for group in groups.values():
        group.sort(key=lambda m: (_posted(m), m.mention_id))
        counted = group[0]
        for m in group[1:]:
            if _posted(m) - _posted(counted) <= window:
                doubles[m.mention_id] = counted.mention_id
            else:
                counted = m
    return doubles


def run_hygiene(mentions: tuple[MentionRecord, ...], client: ClientConfig) -> Hygiene:
    config = load_hygiene_config(client)
    normalise = Normaliser(config, client.raw.get("city_tags", []))
    normalised = {m.mention_id: normalise(m.text) for m in mentions}
    reposts = find_reposts(mentions, normalised, config)
    bursts, spam = find_spam(mentions, normalised, config)
    doubles = find_double_posts(mentions, normalised, set(reposts) | set(spam), config)
    return Hygiene(
        normalised=normalised,
        reposts=reposts,
        bursts=bursts,
        spam=spam,
        double_posts=doubles,
        account_classes={
            h: config["spam"]["account_class"] for burst in bursts for h in burst.handles
        },
        repost_counts=dict(Counter(r.original_id for r in reposts.values() if r.original_id)),
    )
