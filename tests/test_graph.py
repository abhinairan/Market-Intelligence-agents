"""The graph as built in memory, then as stored in Neo4j (skipped when Neo4j is down)."""

from collections import Counter
from datetime import date

import pytest

from halyard import runtime
from halyard.ingest.graph import Graph, build_graph
from halyard.ingest.pipeline import prepare
from halyard.settings import PROJECT_ROOT, HalyardError, Settings, load_client
from halyard.store.schema import EDGES, NODES, render_ontology


@pytest.fixture(scope="module")
def graph():
    client = load_client("brewbird")
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client)
    return build_graph(prepare(settings), client)


def _edges(graph, kind):
    return {(s, t): props for (k, s, t), props in graph.edges.items() if k == kind}


def test_ontology_doc_matches_the_schema():
    path = PROJECT_ROOT / "docs" / "ontology.md"
    assert path.read_text(encoding="utf-8") == render_ontology(), "run `halyard ontology`"


def test_builder_refuses_anything_outside_the_ontology():
    g = Graph()
    with pytest.raises(HalyardError, match="no property"):
        g.node("Brand", "x", None, None, mood="happy")
    a, b = g.node("Brand", "a", None, None), g.node("Brand", "b", None, None)
    with pytest.raises(HalyardError, match="cannot join"):
        g.edge("POSTED_BY", a, b, method="extracted", source_file="f", source_ref="r")
    with pytest.raises(HalyardError, match="rule or model"):
        g.edge("COMPETES_WITH", a, b, method="inferred", source_file="f", source_ref="r")


def test_every_node_and_edge_is_declared_and_has_provenance(graph):
    assert {label for label, _ in graph.nodes} == set(NODES)
    assert {kind for kind, _, _ in graph.edges} <= set(EDGES)
    for (kind, _, _), props in graph.edges.items():
        assert props["method"] in ("extracted", "inferred"), kind
        assert props["source_file"] and props["source_ref"], kind
        if props["method"] == "inferred":
            assert props.get("rule") or props.get("model"), kind
    assert all(n["source_file"] for n in graph.nodes.values())


def test_counts(graph):
    counts = graph.counts()
    assert counts["nodes"] == {
        "Mention": 1904, "Author": 1899, "Observation": 20, "Ad": 19, "Source": 13,
        "Product": 12, "ProductLine": 6, "ComplaintCode": 6, "Team": 5, "Brand": 4,
        "UnrelatedEntity": 1,
    }  # fmt: skip
    assert counts["edges"]["POSTED_BY"] == 1904 and counts["edges"]["REPOST_OF"] == 70


def test_mention_keeps_extracted_and_inferred_apart(graph):
    m = graph.nodes[("Mention", "M10149")]
    assert m["posted_at"] == "2026-08-21T09:49:49+05:30"  # D-01: as exported
    assert (m["date_ist"], m["week_ist"]) == (date(2026, 8, 21), date(2026, 8, 17))
    assert (m["source_ref"], m["source_rows"]) == ("mentions.csv:158", [158, 159])  # D-10
    assert m["text"].endswith("lol") and not m["normalised_text"].endswith("lol")  # D-12
    inferred = {p.split(":")[0] for p in m["inferred_properties"]}
    assert {"date_ist", "week_ist", "status", "sentiment", "normalised_text"} <= inferred
    assert not inferred & {"mention_id", "text", "posted_at", "likes", "platform", "url"}
    assert "week_ist:D-02" in m["inferred_properties"]


def test_excluded_mentions_stay_with_their_reason(graph):  # D-16
    reasons = Counter(
        (n["status"], n.get("exclusion_rule"), n.get("exclusion_reason"))
        for (label, _), n in graph.nodes.items() if label == "Mention"
    )  # fmt: skip
    assert reasons == {
        ("genuine", None, None): 1686,
        ("spam", "D-13", "spam_burst"): 84,
        ("repost", "D-11", "repost:tool_flag"): 38,
        ("repost", "D-11", "repost:rt_text"): 15,
        ("repost", "D-11", "repost:repost_via_text"): 17,
        ("unrelated", "D-22", "unrelated_entity:brewbird_taproom"): 42,
        ("ambiguous", "D-23", "unresolved_entity"): 22,
    }
    bots = Counter(n.get("account_class") for (label, _), n in graph.nodes.items()
                   if label == "Author")  # fmt: skip
    assert bots == {"person": 1815, "coupon_bot": 84}  # D-13


def test_mention_edges_name_their_rule_and_evidence(graph):
    mentions = _edges(graph, "MENTIONS")
    brand = mentions[(("Mention", "M10149"), ("Brand", "brewbird"))]
    assert (brand["method"], brand["rule"], brand["matched"]) == ("inferred", "D-20", "Brewbird")
    assert brand["source_ref"] == "M10149"
    line = mentions[(("Mention", "M10149"), ("ProductLine", "brewbird:Nitro"))]
    assert (line["rule"], line["matched"]) == ("D-24", "Nitro")
    assert sum(1 for (_, t) in mentions if t == ("UnrelatedEntity", "brewbird_taproom")) == 45

    reposts = Counter((e["method"], e["basis"], e.get("rule")) for e in
                      _edges(graph, "REPOST_OF").values())  # fmt: skip
    assert reposts == {
        ("extracted", "tool_flag", None): 38,  # the export said so
        ("inferred", "rt_text", "D-11"): 15,
        ("inferred", "repost_via_text", "D-11"): 17,
    }

    complaint = _edges(graph, "HAS_COMPLAINT")[(("Mention", "M10149"), ("ComplaintCode", "DLV"))]
    assert complaint["model"] == "gpt-6-luna" and complaint["prompt_hash"] and complaint["reason"]
    owner = _edges(graph, "OWNED_BY")[(("ComplaintCode", "TST"), ("Team", "Quality Assurance"))]
    assert (owner["method"], owner["source_ref"]) == ("extracted", "client_complaint_taxonomy.csv:3")


def test_lines_and_products(graph):
    of_brand = _edges(graph, "OF_BRAND")
    peak = of_brand[(("ProductLine", "bluepeak:Peak Instant"), ("Brand", "bluepeak"))]
    assert peak["method"] == "extracted"  # ER-01: Bluepeak's own brands page says so
    assert peak["source_file"].endswith("bluepeak_brands_2026-09-20.md")
    assert peak["captured_at"] == date(2026, 9, 20)
    pack = load_client("brewbird").data_pack
    file, line = peak["source_ref"].rsplit(":", 1)
    assert "Peak Instant" in (pack / file).read_text().splitlines()[int(line) - 1]
    classic = of_brand[(("ProductLine", "brewbird:Classic"), ("Brand", "brewbird"))]
    assert (classic["method"], classic["source_ref"]) == ("extracted", "products.csv:2")
    in_line = _edges(graph, "IN_LINE")
    nitro = (("Product", "saltmarsh:Saltmarsh Nitro Cold Brew"),
             ("ProductLine", "saltmarsh:Saltmarsh Nitro"))  # fmt: skip
    assert (in_line[nitro]["method"], in_line[nitro]["rule"]) == ("inferred", "D-24")
    assert in_line[nitro]["source_ref"] == "competitor_pricing.csv:2"  # earliest evidence


def test_price_observations_are_dated_and_per_unit(graph):  # D-50, D-52, D-53
    obs = graph.nodes
    ours = obs[("Observation", "price:products.csv:6")]
    assert (ours["value"], ours["unit_price"], ours["price_per_100"]) == (660, 110.0, 55.0)
    assert ours["undated"] is True and "observed_at" not in ours
    theirs = obs[("Observation", "price:competitor_pricing.csv:2")]
    assert (theirs["value"], theirs["unit_price"], theirs["region"]) == (540, 90.0, "IN")
    assert (theirs["observed_at"], theirs["stale"]) == (date(2026, 9, 15), False)
    aed = obs[("Observation", "price:competitor_pricing.csv:3")]
    assert (aed["currency"], aed["region"]) == ("AED", "AE")  # ER-14: never converted
    old = obs[("Observation", "price:competitor_pricing.csv:7")]
    assert (old["value"], old["stale"]) == (420, True)  # ER-15: history, not current
    assert "unit_price:D-53" in theirs["inferred_properties"]
    assert "value" not in {p.split(":")[0] for p in theirs["inferred_properties"]}


def test_page_facts(graph):  # D-50, D-51, D-55
    facts = {
        key: n for (label, key), n in graph.nodes.items()
        if label == "Observation" and n["kind"] != "price"
    }  # fmt: skip
    shipping = sorted(
        (n["observed_at"], n["value"], n["stale"]) for n in facts.values()
        if n["kind"] == "free_shipping_threshold" and "bluepeak" in n["source_file"]
    )  # fmt: skip
    assert shipping == [(date(2025, 11, 3), 499, True), (date(2026, 9, 20), 799, False)]
    launch = next(n for n in facts.values() if n["kind"] == "launch")
    assert (launch["observed_at"], launch["text"]) == (
        date(2026, 9, 14), "today launched Saltmarsh Nitro",
    )  # fmt: skip
    assert launch["source_ref"].endswith("saltmarsh_nitro_launch_2026-09-14.md:4")
    about = _edges(graph, "ABOUT")
    assert (("Observation", launch["key"]), ("ProductLine", "saltmarsh:Saltmarsh Nitro")) in about
    assert Counter(n["kind"] for n in facts.values()) == {
        "free_shipping_threshold": 4, "launch": 1, "offer": 1,
    }  # fmt: skip


def test_ads(graph):  # D-54
    ads = {key: n for (label, key), n in graph.nodes.items() if label == "Ad"}
    assert ads["FH-A-020"]["still_running"] is False and ads["SM-A-300"]["still_running"] is True
    promotes = Counter(t[1] for (_, t) in _edges(graph, "PROMOTES"))
    assert promotes == {"saltmarsh:Saltmarsh Nitro": 14, "bluepeak:Peak Instant": 2}
    run_by = _edges(graph, "RUN_BY")
    assert run_by[(("Ad", "SM-A-300"), ("Brand", "saltmarsh"))]["method"] == "extracted"


# --- stored in Neo4j ------------------------------------------------------------------


@pytest.fixture(scope="module")
def driver():
    from halyard.settings import load_settings
    from halyard.store.neo4j_writer import connect

    try:
        settings = load_settings()
        runtime.wait_for_neo4j(settings, timeout_s=5)
    except HalyardError:
        pytest.skip("Neo4j is not running (make up)")
    with connect(settings) as d:
        yield d


@pytest.mark.integration
def test_two_builds_store_identical_counts(graph, driver):
    from halyard.store.neo4j_writer import stored_counts, write_graph

    write_graph(graph, driver)
    first = stored_counts(driver)
    write_graph(graph, driver)
    assert stored_counts(driver) == first == {k: dict(v) for k, v in graph.counts().items()}
    write_graph(graph, driver, wipe=False)  # MERGE: writing over a built graph adds nothing
    assert stored_counts(driver) == first


@pytest.mark.integration
def test_headline_figures_from_cypher(graph, driver):
    from halyard.store.neo4j_writer import write_graph

    write_graph(graph, driver)

    def rows(query, **params):
        return [r.data() for r in driver.execute_query(query, **params)[0]]

    genuine = "MATCH (m:Mention {status: 'genuine'})-[:MENTIONS]->(:Brand {key: 'brewbird'}) "
    total = rows(genuine + "RETURN count(m) AS n, count(DISTINCT m.mention_id) AS ids")[0]
    assert total == {"n": 987, "ids": 987}  # D-15

    by_line = rows(
        genuine + "OPTIONAL MATCH (m)-[:MENTIONS]->(l:ProductLine) "
        "RETURN coalesce(l.name, 'brand-level') AS line, count(m) AS n"
    )
    assert {r["line"]: r["n"] for r in by_line} == {
        "Classic": 246, "Nitro": 211, "Origins": 203, "Drip": 175, "brand-level": 152,
    }  # fmt: skip

    tst = rows(
        genuine + "MATCH (m)-[:MENTIONS]->(:ProductLine {key: 'brewbird:Nitro'}) "
        "MATCH (m)-[:HAS_COMPLAINT]->(:ComplaintCode {code: 'TST'}) "
        "RETURN m.week_ist AS week, count(m) AS n ORDER BY week"
    )
    assert [(r["week"].iso_format(), r["n"]) for r in tst] == [
        ("2026-09-14", 7), ("2026-09-21", 9), ("2026-09-28", 13),
    ]  # fmt: skip

    sov = rows(
        "MATCH (m:Mention {status: 'genuine'})-[:MENTIONS]->(b:Brand) "
        "WHERE m.week_ist >= date('2026-09-07') RETURN b.key AS brand, count(m) AS n"
    )
    assert {r["brand"]: r["n"] for r in sov} == {
        "brewbird": 585, "saltmarsh": 210, "bluepeak": 198, "filterhaus": 48,
    }  # fmt: skip

    stored = rows("MATCH (m:Mention {mention_id: 'M10001'}) RETURN m.posted_at AS at")[0]
    assert stored["at"] == "2026-08-17T00:29:34+05:30"  # D-01: no UTC conversion on the way in
