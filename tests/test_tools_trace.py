"""coverage, trace, result IDs and the Neo4j parity of the tools (P3 step 6)."""

import pytest

from halyard import runtime
from halyard.ingest.graph import build_graph
from halyard.ingest.pipeline import prepare
from halyard.settings import HalyardError, Settings, load_client
from halyard.store.graph_store import MemoryStore
from halyard.tools.base import ToolError
from halyard.tools.context import ToolContext
from halyard.tools.registry import TOOLS, run_tool
from halyard.tools.trace import render_trace


@pytest.fixture(scope="module")
def graph():
    client = load_client("brewbird")
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client)
    return build_graph(prepare(settings), client)


@pytest.fixture(scope="module")
def ctx(graph, tmp_path_factory):
    log = tmp_path_factory.mktemp("outputs") / "tool_calls.jsonl"
    return ToolContext(MemoryStore(graph), load_client("brewbird"), tool_log=log)


@pytest.fixture(scope="module")
def call(ctx):
    return lambda name, **args: run_tool(ctx, name, args)


# --- trace ----------------------------------------------------------------------------


def test_trace_a_mention_to_its_rows(call):  # D-10
    r = call("trace", ids=["M10149"])
    (m,) = r["data"]["traced"]
    assert (m["type"], m["source_file"], m["source_rows"]) == ("Mention", "mentions.csv", [158, 159])
    assert r["source_refs"] == ["mentions.csv:158", "mentions.csv:159"]
    assert r["mention_ids"] == ["M10149"]
    # Every value says how it was obtained.
    assert m["values"]["text"]["how"] == "extracted"
    assert m["values"]["sentiment"] == {"value": "negative", "how": "inferred (D-30)"}
    assert m["values"]["week_ist"]["how"] == "inferred (D-02)"
    edges = {(e["edge"], e["node"]): e for e in m["edges"]}
    brand = edges[("MENTIONS", "Brand brewbird")]
    assert (brand["method"], brand["rule"], brand["matched"].lower()) == (
        "inferred", "D-20", "brewbird",
    )  # fmt: skip
    assert edges[("HAS_COMPLAINT", "ComplaintCode DLV")]["model"]
    assert edges[("POSTED_BY", "Author pooja1231")]["method"] == "extracted"


def test_trace_other_ids(call):
    data = call(
        "trace", ids=["SM-A-300", "price:competitor_pricing.csv:2", "saltmarsh", "M00000", "R-0"]
    )["data"]
    ad, price, brand = data["traced"]
    assert (ad["type"], ad["source_ref"]) == ("Ad", "competitor_ads.csv:12")
    assert ad["values"]["still_running"]["how"] == "inferred (D-54)"
    assert price["values"]["unit_price"] == {"value": 90.0, "how": "inferred (D-53)"}
    assert price["values"]["value"]["how"] == "extracted"
    assert brand["values"]["name"]["how"] == "config" and "edges" not in brand
    assert brand["edge_counts"]["MENTIONS (in)"] == 300 + 14  # genuine and reposts
    assert data["not_found"] == ["M00000", "R-0"]
    with pytest.raises(ToolError, match="needs ids"):
        call("trace")


def test_a_result_id_gives_back_the_call_and_every_mention_id(call):
    counted = call("count_mentions", brand="brewbird", group_by="line")
    (t,) = call("trace", ids=[counted["result_id"]])["data"]["traced"]
    assert (t["tool"], t["arguments"]) == (
        "count_mentions", {"brand": "brewbird", "group_by": "line"},
    )  # fmt: skip
    assert t["mention_ids"] == counted["mention_ids"] and len(t["mention_ids"]) == 987
    assert "D-15" in t["method_note"]

    # A follow-up question reads the same mentions without repeating the filters.
    follow_up = call("get_mentions", result_id=counted["result_id"], limit=3)
    assert follow_up["data"]["matched"] == 987 and follow_up["data"]["returned"] == 3
    assert set(follow_up["mention_ids"]) <= set(counted["mention_ids"])
    with pytest.raises(ToolError, match="no logged result"):
        call("get_mentions", result_id="R-00000000")


def test_trace_renders_as_text(call):
    counted = call("exclusions", week="2026-09-21")
    text = render_trace(call("trace", ids=["M10149", counted["result_id"], "nope"])["data"])
    assert "M10149  Mention  mentions.csv rows 158, 159" in text
    assert "sentiment = negative   [inferred (D-30)]" in text
    assert "MENTIONS -> Brand brewbird" in text
    assert f"{counted['result_id']}  result of exclusions" in text
    assert text.endswith("Not found: nope")


# --- coverage -------------------------------------------------------------------------


def test_coverage_lists_what_the_graph_holds(call):
    data = call("coverage")["data"]
    holds = data["holds"]
    assert holds["mentions"]["in_export"] == 1904
    assert holds["mentions"]["genuine_conversations"] == 1686
    assert (holds["mentions"]["first_date"], holds["mentions"]["last_date"]) == (
        "2026-08-17", "2026-10-04",
    )  # fmt: skip
    assert len(holds["brands"]) == 4 and len(holds["sources"]) == 13
    assert holds["observations_by_brand"]["saltmarsh"] == {
        "free_shipping_threshold": 1, "launch": 1, "offer": 1, "price": 3,
    }  # fmt: skip
    assert holds["ads_by_brand"]["saltmarsh"] == 15
    assert len(data["not_in_data"]) == 5


def test_coverage_says_there_is_no_subscription_data(call):  # D-60
    r = call("coverage", topic="subscription cancellations")
    data = r["data"]
    (gap,) = data["not_in_data"]
    assert "no subscription, order or account data" in gap["statement"] and gap["would_need"]
    assert data["has_structured_data"] is False
    # What the client's own page says, and the complaints that use the word.
    (page,) = data["found"]["pages"]
    assert page["file"] == "brand_site/faq.md"
    assert any("subscriptions on Classic and Origins" in line for line in page["says"])
    assert "SUB" in data["found"]["complaint_codes"]
    assert data["found"]["mentions"]["count"] > 0 and "not records" in data["found"]["mentions"]["note"]
    assert r["source_refs"] == ["brand_site/faq.md:2"]


def test_coverage_says_there_is_no_wholesale_price(call):  # D-60, D-62
    data = call("coverage", topic="Filterhaus wholesale prices")["data"]
    (gap,) = data["not_in_data"]
    assert "D-62" in gap["statement"] and data["has_structured_data"] is False
    (page,) = data["found"]["pages"]
    assert page["file"] == "competitor_snapshots/filterhaus_home_2026-09-10.md"
    assert any("Trade Portal" in line for line in page["says"])


def test_coverage_of_a_topic_nobody_declared(call):
    data = call("coverage", topic="hazelnut")["data"]
    assert data["not_in_data"] == [] and data["searched_for"] == ["hazelnut"]
    assert data["found"]["pages"] == [] and data["has_structured_data"] is False


# --- every tool, on both stores -------------------------------------------------------

CALLS = [
    ("count_mentions", {"brand": "brewbird", "group_by": "line"}),
    ("get_mentions", {"line": "Nitro", "code": "TST", "last_weeks": 3, "limit": 3}),
    ("exclusions", {}),
    ("daily_activity", {"day": "2026-09-22"}),
    ("sentiment_trend", {"line": "Nitro"}),
    ("complaint_breakdown", {"brand": "brewbird", "last_weeks": 3}),
    ("share_of_voice", {"last_weeks": 4, "compare_naive": True}),
    ("competitor_observations", {}),
    ("price_compare", {"a": "Saltmarsh Nitro", "b": "Brewbird Nitro", "include_offers": True}),
    ("competitor_ads", {"brand": "saltmarsh"}),
    ("coverage", {"topic": "wholesale"}),
    ("trace", {"ids": ["M10149", "SM-A-300", "price:competitor_pricing.csv:2", "bluepeak"]}),
]


def test_every_tool_has_a_parity_call():
    assert {name for name, _ in CALLS} == set(TOOLS)


@pytest.mark.integration
def test_every_tool_answers_the_same_from_neo4j(graph, ctx):
    from halyard.settings import load_settings
    from halyard.store.neo4j_store import Neo4jStore
    from halyard.store.neo4j_writer import connect, write_graph

    try:
        settings = load_settings()
        runtime.wait_for_neo4j(settings, timeout_s=5)
    except HalyardError:
        pytest.skip("Neo4j is not running (make up)")
    with connect(settings) as driver:
        write_graph(graph, driver)
        stored = ToolContext(Neo4jStore(driver), ctx.client)
        memory = ToolContext(ctx.store, ctx.client)
        for name, args in CALLS:
            assert run_tool(stored, name, args) == run_tool(memory, name, args), name
