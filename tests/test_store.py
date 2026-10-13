"""GraphStore reads, windows and filters (P3 step 1). Neo4j parity is skipped when it is down."""

from datetime import date

import pytest

from halyard import runtime
from halyard.ingest.graph import build_graph
from halyard.ingest.pipeline import prepare
from halyard.settings import HalyardError, Settings, load_client
from halyard.store.graph_store import MemoryStore
from halyard.tools.base import ToolError, ToolResult
from halyard.tools.context import ToolContext
from halyard.tools.filters import BRAND_LEVEL, MentionFilter, select_mentions
from halyard.tools.windows import Window, resolve_window, weeks_in


@pytest.fixture(scope="module")
def client():
    return load_client("brewbird")


@pytest.fixture(scope="module")
def graph(client):
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client)
    return build_graph(prepare(settings), client)


@pytest.fixture(scope="module")
def ctx(graph, client):
    return ToolContext(MemoryStore(graph), client)


@pytest.fixture(scope="module")
def mentions(ctx):
    return ctx.mentions


@pytest.fixture(scope="module")
def names(ctx):
    return ctx.names


# --- store ----------------------------------------------------------------------------


def test_store_reads(ctx, mentions):
    store = ctx.store
    assert len(mentions) == 1904 and len(store.observations()) == 20 and len(store.ads()) == 19
    assert [b["key"] for b in store.nodes("Brand")] == [
        "bluepeak", "brewbird", "filterhaus", "saltmarsh",
    ]  # fmt: skip
    with pytest.raises(HalyardError, match="not a node type"):
        store.nodes("Mention`) DETACH DELETE (n")

    m = next(m for m in mentions if m.mention_id == "M10149")
    assert m.props["source_rows"] == [158, 159]  # D-10
    assert m.date == date.fromisoformat(m.props["posted_at"][:10])  # D-01: the local date

    ad = next(a for a in store.ads() if a.ad_id == "SM-A-300")
    assert ad.brand == "saltmarsh"
    price = next(o for o in store.observations() if o.props["kind"] == "price")
    assert price.source and any(label == "Product" for label, _ in price.about)


def test_node_with_its_edges(ctx):
    view = ctx.store.node("Mention", "M10149")
    kinds = {(e.kind, e.direction, e.other[0]) for e in view.edges}
    assert ("POSTED_BY", "out", "Author") in kinds and ("MENTIONS", "out", "Brand") in kinds
    assert all(e.props["source_file"] and e.props["method"] for e in view.edges)
    assert ctx.store.node("Mention", "M00000") is None


@pytest.mark.integration
def test_neo4j_store_returns_what_the_memory_store_returns(graph, ctx):
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
        stored, memory = Neo4jStore(driver), ctx.store
        assert stored.mentions() == memory.mentions()
        assert stored.observations() == memory.observations()
        assert stored.ads() == memory.ads()
        for label in ("Brand", "ProductLine", "ComplaintCode", "Team", "Source", "Product"):
            assert stored.nodes(label) == memory.nodes(label), label
        for label, key in (("Mention", "M10149"), ("Brand", "saltmarsh"), ("Ad", "SM-A-300")):
            assert stored.node(label, key) == memory.node(label, key), key
        assert stored.node("Mention", "M00000") is None


# --- windows --------------------------------------------------------------------------


def test_windows(client):  # D-02, D-03
    assert resolve_window(client) == Window(date(2026, 8, 17), date(2026, 10, 4))
    assert resolve_window(client, last_weeks=3) == Window(date(2026, 9, 14), date(2026, 10, 4))
    assert resolve_window(client, last_weeks=4) == Window(date(2026, 9, 7), date(2026, 10, 4))
    # Any day of a week names that week; dates may arrive as text from a model.
    assert resolve_window(client, week="2026-09-30") == Window(
        date(2026, 9, 28), date(2026, 10, 4)
    )
    assert resolve_window(client, start="2026-09-22", end="2026-09-22").start == date(2026, 9, 22)
    assert weeks_in(client, resolve_window(client)) == [
        date(2026, 8, 17), date(2026, 8, 24), date(2026, 8, 31), date(2026, 9, 7),
        date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28),
    ]  # fmt: skip


def test_windows_outside_the_data(client):  # D-04
    with pytest.raises(ToolError, match="No data for"):
        resolve_window(client, start="2026-07-01", end="2026-07-31")
    clipped = resolve_window(client, last_weeks=10)
    assert (clipped.start, clipped.end) == (client.window_start, client.window_end)
    assert "the data covers only" in clipped.note
    with pytest.raises(ToolError, match="only one"):
        resolve_window(client, last_weeks=3, week="2026-09-28")
    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        resolve_window(client, start="22 Sep")


def test_last_weeks_ends_on_the_last_full_week(client):  # D-03
    from dataclasses import replace

    midweek = replace(client, as_of=date(2026, 9, 30))  # a Wednesday
    assert resolve_window(midweek, last_weeks=1) == Window(date(2026, 9, 21), date(2026, 9, 27))


# --- filters --------------------------------------------------------------------------


def test_names(names):
    assert names.client_brand == "brewbird"
    assert names.brand("Saltmarsh") == names.brand("saltmarsh coffee") == "saltmarsh"
    assert names.line("Nitro") == names.line("Brewbird Nitro") == "brewbird:Nitro"
    assert names.line("nitro", brand="saltmarsh") == "saltmarsh:Saltmarsh Nitro"
    assert names.line("peak instant") == "bluepeak:Peak Instant"
    assert names.code("tst") == "TST"
    with pytest.raises(ToolError, match="Use one of: .*brewbird:Nitro"):
        names.line("Decaf")
    with pytest.raises(ToolError, match="not a known brand"):
        names.brand("Starbucks")


def test_filters_count_only_genuine_conversations_by_default(mentions, names, client):
    def n(window=None, **flt):
        return len(select_mentions(mentions, names, MentionFilter(**flt), window))

    assert n(brand="brewbird") == 987  # D-15
    assert n(include_excluded=True) == 1904  # D-16
    assert [n(brand="brewbird", line=ln) for ln in ("Classic", "Nitro", "Origins", "Drip")] == [
        246, 211, 203, 175,
    ]  # fmt: skip
    assert n(line=BRAND_LEVEL) == 152  # the client's, when no brand is given
    last_4 = resolve_window(client, last_weeks=4)
    assert [n(last_4, brand=b) for b in ("brewbird", "saltmarsh", "bluepeak", "filterhaus")] == [
        585, 210, 198, 48,
    ]  # fmt: skip
    last_3 = resolve_window(client, last_weeks=3)
    assert n(last_3, brand="brewbird", code="TST") == 36
    assert n(last_3, line="nitro", code="tst", sentiment="NEGATIVE") == 29
    assert n(city="delhi", include_excluded=True) == 167  # D-26


def test_unknown_filter_values_fail_with_the_valid_ones(mentions, names):
    with pytest.raises(ToolError, match="not a platform in the data. Use one of: "):
        select_mentions(mentions, names, MentionFilter(platform="myspace"))
    with pytest.raises(ToolError, match="not a city"):
        select_mentions(mentions, names, MentionFilter(city="Pune"))


# --- result ---------------------------------------------------------------------------


def test_result_shape(client):
    result = ToolResult(
        data={"by_week": {date(2026, 9, 28): 13}, "window": (date(2026, 9, 14), client.as_of)},
        method_note="Genuine conversations only (D-15).",
        as_of=client.as_of,
        mention_ids=["M10149"],
    )
    assert result.to_dict() == {
        "data": {"by_week": {"2026-09-28": 13}, "window": ["2026-09-14", "2026-10-04"]},
        "mention_ids": ["M10149"],
        "source_refs": [],
        "method_note": "Genuine conversations only (D-15).",
        "as_of": "2026-10-04",
    }
