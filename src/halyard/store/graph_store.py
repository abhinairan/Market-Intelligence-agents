"""GraphStore: the few reads the query tools need, and nothing else.

Tools never see Cypher or a driver. A store hands back plain rows and the tools do the
counting, so every D-rule about counting is written once and a second store (the SQLite
stretch in docs/PLAN.md) only has to implement these five reads.

`MemoryStore` serves a graph built in memory. It is what lets every tool be tested from a
clean clone with no database, and what `Neo4jStore` is checked against.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from halyard.settings import HalyardError
from halyard.store.schema import NODES

NodeRef = tuple[str, str]  # (label, key value)


@dataclass(frozen=True)
class MentionRow:
    """A mention with what its edges say about it."""

    props: dict[str, Any]  # the node's properties, as in docs/ontology.md
    author: str
    brands: tuple[str, ...]  # Brand keys it is about (D-25: may be more than one)
    lines: tuple[str, ...]  # ProductLine keys
    unrelated: tuple[str, ...]  # UnrelatedEntity keys (D-22)
    codes: tuple[str, ...]  # complaint codes (D-31)
    repost_of: str | None = None
    double_post_of: str | None = None

    @property
    def mention_id(self) -> str:
        return self.props["mention_id"]

    @property
    def status(self) -> str:
        return self.props["status"]

    @property
    def date(self) -> date:
        return self.props["date_ist"]  # D-01: written at ingest, never derived in a query

    @property
    def week(self) -> date:
        return self.props["week_ist"]


@dataclass(frozen=True)
class ObservationRow:
    props: dict[str, Any]
    about: tuple[NodeRef, ...]  # the brands, lines and products it is a fact about
    source: str  # Source file it was read from

    @property
    def key(self) -> str:
        return self.props["key"]


@dataclass(frozen=True)
class AdRow:
    props: dict[str, Any]
    brand: str  # the advertiser's Brand key
    lines: tuple[str, ...]  # ProductLine keys its headline names

    @property
    def ad_id(self) -> str:
        return self.props["ad_id"]


@dataclass(frozen=True)
class EdgeView:
    kind: str
    direction: str  # "out" when the node is the edge's source, "in" when it is the target
    other: NodeRef
    props: dict[str, Any]  # provenance included


@dataclass(frozen=True)
class NodeView:
    """One node with every edge touching it: what a trace needs."""

    label: str
    key: str
    props: dict[str, Any]
    edges: tuple[EdgeView, ...]


class GraphStore(Protocol):
    def mentions(self) -> list[MentionRow]:
        """Every mention, counted or not (D-16), ordered by ID."""

    def observations(self) -> list[ObservationRow]:
        """Every dated fact (D-50), ordered by key."""

    def ads(self) -> list[AdRow]:
        """Every ad, ordered by ID."""

    def nodes(self, label: str) -> list[dict[str, Any]]:
        """The properties of every node of one type, ordered by key."""

    def node(self, label: str, key: str) -> NodeView | None:
        """One node with its edges, or None when there is no such node."""


def check_label(label: str) -> str:
    if label not in NODES:
        raise HalyardError(f"{label!r} is not a node type in the ontology.")
    return label


class MemoryStore:
    """A GraphStore over a graph held in memory (halyard.ingest.graph.Graph)."""

    def __init__(self, graph: Any):
        self._nodes: dict[NodeRef, dict[str, Any]] = graph.nodes
        self._out: dict[NodeRef, list[tuple[str, NodeRef, dict[str, Any]]]] = defaultdict(list)
        self._in: dict[NodeRef, list[tuple[str, NodeRef, dict[str, Any]]]] = defaultdict(list)
        for (kind, source, target), props in graph.edges.items():
            self._out[source].append((kind, target, props))
            self._in[target].append((kind, source, props))

    def _targets(self, ref: NodeRef, kind: str, label: str) -> tuple[str, ...]:
        return tuple(sorted(t[1] for k, t, _ in self._out[ref] if k == kind and t[0] == label))

    def _of(self, label: str) -> list[NodeRef]:
        return sorted(ref for ref in self._nodes if ref[0] == label)

    def mentions(self) -> list[MentionRow]:
        rows = []
        for ref in self._of("Mention"):
            rows.append(
                MentionRow(
                    props=dict(self._nodes[ref]),
                    author=self._targets(ref, "POSTED_BY", "Author")[0],
                    brands=self._targets(ref, "MENTIONS", "Brand"),
                    lines=self._targets(ref, "MENTIONS", "ProductLine"),
                    unrelated=self._targets(ref, "MENTIONS", "UnrelatedEntity"),
                    codes=self._targets(ref, "HAS_COMPLAINT", "ComplaintCode"),
                    repost_of=next(iter(self._targets(ref, "REPOST_OF", "Mention")), None),
                    double_post_of=next(
                        iter(self._targets(ref, "DOUBLE_POST_OF", "Mention")), None
                    ),
                )
            )
        return rows

    def observations(self) -> list[ObservationRow]:
        return [
            ObservationRow(
                props=dict(self._nodes[ref]),
                about=tuple(sorted(t for k, t, _ in self._out[ref] if k == "ABOUT")),
                source=self._targets(ref, "FROM", "Source")[0],
            )
            for ref in self._of("Observation")
        ]

    def ads(self) -> list[AdRow]:
        return [
            AdRow(
                props=dict(self._nodes[ref]),
                brand=self._targets(ref, "RUN_BY", "Brand")[0],
                lines=self._targets(ref, "PROMOTES", "ProductLine"),
            )
            for ref in self._of("Ad")
        ]

    def nodes(self, label: str) -> list[dict[str, Any]]:
        return [dict(self._nodes[ref]) for ref in self._of(check_label(label))]

    def node(self, label: str, key: str) -> NodeView | None:
        ref = (check_label(label), key)
        if ref not in self._nodes:
            return None
        edges = [EdgeView(k, "out", other, dict(p)) for k, other, p in self._out[ref]]
        edges += [EdgeView(k, "in", other, dict(p)) for k, other, p in self._in[ref]]
        return NodeView(label, key, dict(self._nodes[ref]), sort_edges(edges))


def sort_edges(edges: list[EdgeView]) -> tuple[EdgeView, ...]:
    return tuple(sorted(edges, key=lambda e: (e.kind, e.direction, e.other)))
