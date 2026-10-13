"""Write a built graph to Neo4j. `halyard build` wipes first, so a rebuild is repeatable."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from neo4j import Driver, GraphDatabase

from halyard.ingest.graph import Graph
from halyard.settings import Settings
from halyard.store.schema import NODES

BATCH = 1000


def connect(settings: Settings) -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        # An edge type the ontology declares can have no instance in a given pack (no double
        # posts here, D-17). Asking for it is not a mistake, so that warning is switched off.
        notifications_disabled_categories=["UNRECOGNIZED"],
    )


def _batches(rows: list[dict[str, Any]]):
    for i in range(0, len(rows), BATCH):
        yield rows[i : i + BATCH]


def write_graph(graph: Graph, driver: Driver, wipe: bool = True) -> None:
    if wipe:
        driver.execute_query("MATCH (n) DETACH DELETE n")
    for label, node_type in NODES.items():
        # One node per key, which is also what lets MERGE find it quickly.
        driver.execute_query(
            f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS "
            f"FOR (n:`{label}`) REQUIRE n.`{node_type.key}` IS UNIQUE"
        )

    nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (label, key), props in graph.nodes.items():
        nodes[label].append({"key": key, "props": props})
    for label, rows in nodes.items():
        for batch in _batches(rows):
            driver.execute_query(
                f"UNWIND $rows AS r MERGE (n:`{label}` {{`{NODES[label].key}`: r.key}}) "
                "SET n = r.props",
                rows=batch,
            )

    edges: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for (kind, source, target), props in graph.edges.items():
        edges[(kind, source[0], target[0])].append(
            {"source": source[1], "target": target[1], "props": props}
        )
    for (kind, source, target), rows in edges.items():
        for batch in _batches(rows):
            driver.execute_query(
                f"UNWIND $rows AS r "
                f"MATCH (a:`{source}` {{`{NODES[source].key}`: r.source}}) "
                f"MATCH (b:`{target}` {{`{NODES[target].key}`: r.target}}) "
                f"MERGE (a)-[e:`{kind}`]->(b) SET e = r.props",
                rows=batch,
            )


def stored_counts(driver: Driver) -> dict[str, dict[str, int]]:
    """Node and edge counts as the database reports them."""
    nodes, _, _ = driver.execute_query("MATCH (n) RETURN labels(n)[0] AS k, count(*) AS n")
    edges, _, _ = driver.execute_query("MATCH ()-[e]->() RETURN type(e) AS k, count(*) AS n")
    return {
        "nodes": {r["k"]: r["n"] for r in nodes},
        "edges": {r["k"]: r["n"] for r in edges},
    }
