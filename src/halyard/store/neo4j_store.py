"""GraphStore over Neo4j. The only place the query layer holds Cypher."""

from __future__ import annotations

from typing import Any

from neo4j import Driver

from halyard.store.graph_store import (
    AdRow,
    EdgeView,
    MentionRow,
    NodeView,
    ObservationRow,
    check_label,
    sort_edges,
)
from halyard.store.schema import NODES

MENTIONS = """
MATCH (m:Mention)
RETURN properties(m) AS props,
       head([(m)-[:POSTED_BY]->(a:Author) | a.handle]) AS author,
       [(m)-[:MENTIONS]->(b:Brand) | b.key] AS brands,
       [(m)-[:MENTIONS]->(l:ProductLine) | l.key] AS lines,
       [(m)-[:MENTIONS]->(u:UnrelatedEntity) | u.key] AS unrelated,
       [(m)-[:HAS_COMPLAINT]->(c:ComplaintCode) | c.code] AS codes,
       head([(m)-[:REPOST_OF]->(o:Mention) | o.mention_id]) AS repost_of,
       head([(m)-[:DOUBLE_POST_OF]->(o:Mention) | o.mention_id]) AS double_post_of
ORDER BY m.mention_id
"""

OBSERVATIONS = """
MATCH (o:Observation)
RETURN properties(o) AS props,
       [(o)-[:ABOUT]->(t) | [labels(t)[0], t.key]] AS about,
       head([(o)-[:FROM]->(s:Source) | s.file]) AS source
ORDER BY o.key
"""

ADS = """
MATCH (a:Ad)
RETURN properties(a) AS props,
       head([(a)-[:RUN_BY]->(b:Brand) | b.key]) AS brand,
       [(a)-[:PROMOTES]->(l:ProductLine) | l.key] AS lines
ORDER BY a.ad_id
"""


def _native(value: Any) -> Any:
    """Driver date types become Python dates, so both stores return the same values."""
    if isinstance(value, list):
        return [_native(v) for v in value]
    return value.to_native() if hasattr(value, "to_native") else value


def _props(props: dict[str, Any]) -> dict[str, Any]:
    return {k: _native(v) for k, v in props.items()}


class Neo4jStore:
    def __init__(self, driver: Driver):
        self.driver = driver

    def _rows(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return [r.data() for r in self.driver.execute_query(query, **params)[0]]

    def mentions(self) -> list[MentionRow]:
        return [
            MentionRow(
                props=_props(r["props"]),
                author=r["author"],
                brands=tuple(sorted(r["brands"])),
                lines=tuple(sorted(r["lines"])),
                unrelated=tuple(sorted(r["unrelated"])),
                codes=tuple(sorted(r["codes"])),
                repost_of=r["repost_of"],
                double_post_of=r["double_post_of"],
            )
            for r in self._rows(MENTIONS)
        ]

    def observations(self) -> list[ObservationRow]:
        return [
            ObservationRow(
                props=_props(r["props"]),
                about=tuple(sorted((label, key) for label, key in r["about"])),
                source=r["source"],
            )
            for r in self._rows(OBSERVATIONS)
        ]

    def ads(self) -> list[AdRow]:
        return [
            AdRow(props=_props(r["props"]), brand=r["brand"], lines=tuple(sorted(r["lines"])))
            for r in self._rows(ADS)
        ]

    def nodes(self, label: str) -> list[dict[str, Any]]:
        key = NODES[check_label(label)].key
        rows = self._rows(f"MATCH (n:`{label}`) RETURN properties(n) AS props ORDER BY n.`{key}`")
        return [_props(r["props"]) for r in rows]

    def node(self, label: str, key: str) -> NodeView | None:
        key_property = NODES[check_label(label)].key
        rows = self._rows(
            f"MATCH (n:`{label}` {{`{key_property}`: $key}}) "
            "OPTIONAL MATCH (n)-[e]-(o) "
            "RETURN properties(n) AS props, type(e) AS kind, startNode(e) = n AS outgoing, "
            "labels(o)[0] AS other_label, properties(o) AS other, properties(e) AS edge",
            key=key,
        )
        if not rows:
            return None
        edges = [
            EdgeView(
                r["kind"],
                "out" if r["outgoing"] else "in",
                (r["other_label"], r["other"][NODES[r["other_label"]].key]),
                _props(r["edge"]),
            )
            for r in rows
            if r["kind"]
        ]
        return NodeView(label, key, _props(rows[0]["props"]), sort_edges(edges))
