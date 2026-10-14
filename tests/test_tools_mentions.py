"""count_mentions, get_mentions, exclusions, daily_activity and the registry (P3 step 2)."""

import json
from datetime import date

import pytest

from halyard.ingest.graph import build_graph
from halyard.ingest.pipeline import prepare
from halyard.settings import Settings, load_client
from halyard.store.graph_store import MemoryStore
from halyard.tools.base import ToolError
from halyard.tools.context import ToolContext
from halyard.tools.registry import TOOLS, run_tool


@pytest.fixture(scope="module")
def ctx():
    client = load_client("brewbird")
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client)
    return ToolContext(MemoryStore(build_graph(prepare(settings), client)), client)


@pytest.fixture(scope="module")
def call(ctx):
    return lambda name, **args: run_tool(ctx, name, args)


def _groups(result):
    by = result["data"]["group_by"]
    return {g[by]: g["count"] for g in result["data"]["groups"]}


def test_count_mentions_by_line(call):  # D-15
    r = call("count_mentions", brand="Brewbird", group_by="line")
    assert r["data"]["total"] == 987 and r["data"]["distinct_authors"] == 984
    assert _groups(r) == {
        "brewbird:Classic": 246, "brewbird:Nitro": 211, "brewbird:Origins": 203,
        "brewbird:Drip": 175, "brand-level": 152,
    }  # fmt: skip
    assert len(r["mention_ids"]) == len(set(r["mention_ids"])) == 987
    assert r["data"]["filters"] == {"brand": "brewbird"}
    assert "D-15" in r["method_note"] and r["as_of"] == "2026-10-04"


def test_count_mentions_other_groupings(call):
    by_week = _groups(call("count_mentions", line="Nitro", code="TST", group_by="week"))
    assert by_week == {"2026-08-17": 0, "2026-08-24": 0, "2026-08-31": 0, "2026-09-07": 0,
                       "2026-09-14": 7, "2026-09-21": 9, "2026-09-28": 13}  # fmt: skip
    codes = _groups(call("count_mentions", brand="brewbird", last_weeks=3, group_by="code"))
    del codes["none"]
    assert codes == {"TST": 36, "PRC": 23, "DLV": 16, "CSX": 11, "PKG": 8, "SUB": 7}
    brands = call("count_mentions", last_weeks=4, group_by="brand")
    assert _groups(brands) == {"brewbird": 585, "saltmarsh": 210, "bluepeak": 198, "filterhaus": 48}
    assert sum(_groups(brands).values()) > brands["data"]["total"]  # D-25: two brands, two groups
    assert call("count_mentions", include_excluded=True)["data"]["total"] == 1904  # D-16
    # An empty group shows as 0: no Nitro conversation names another brand.
    nitro = _groups(call("count_mentions", line="Nitro", group_by="brand"))
    assert nitro == {"brewbird": 211, "saltmarsh": 0, "bluepeak": 0, "filterhaus": 0}


def test_get_mentions(call):
    r = call("get_mentions", line="Nitro", code="TST", last_weeks=3, limit=2)
    shown = r["data"]["mentions"]
    assert r["data"]["matched"] == 29 and r["data"]["returned"] == len(shown) == 2
    assert shown[0]["likes"] >= shown[1]["likes"]  # D-42
    assert all(m["status"] == "genuine" and "TST" in m["codes"] for m in shown)
    assert r["mention_ids"] == [m["mention_id"] for m in shown]
    assert call("get_mentions", line="Nitro", code="TST", last_weeks=3, limit=2) == r


def test_get_mentions_by_id_shows_excluded_ones_too(call):  # D-16
    spam = call("exclusions")["data"]["reasons"][0]["example_ids"][0]
    r = call("get_mentions", ids=["M10149", spam, "M00000"])
    first, second = r["data"]["mentions"]
    assert first["source_ref"] == "mentions.csv:158" and first["codes"] == ["DLV"]
    assert second["status"] == "spam" and second["exclusion_rule"] == "D-13"
    assert r["data"]["not_found"] == ["M00000"]


def test_exclusions(call):  # D-16
    data = call("exclusions")["data"]
    assert data["mentions_in_export"] == 1904 and data["counted_as_genuine"] == 1686
    assert data["by_status"] == {"spam": 84, "repost": 70, "unrelated": 42, "ambiguous": 22}
    assert data["duplicate_rows_collapsed"] == 18  # D-10
    reasons = {r["reason"]: (r["rule"], r["count"]) for r in data["reasons"]}
    assert reasons == {
        "spam_burst": ("D-13", 84),
        "unrelated_entity:brewbird_taproom": ("D-22", 42),
        "repost:tool_flag": ("D-11", 38),
        "unresolved_entity": ("D-23", 22),
        "repost:repost_via_text": ("D-11", 17),
        "repost:rt_text": ("D-11", 15),
    }
    assert data["reasons"][0]["brands_named"] == {"brewbird": 84}
    week = call("exclusions", week="2026-08-17")["data"]
    assert week["by_status"].get("spam") is None and week["excluded"] < data["excluded"]


def test_daily_activity_finds_and_explains_the_spike(call):  # D-43
    r = call("daily_activity")
    data = r["data"]
    assert data["median_mentions_per_day"] == 36 and data["unusual_days"] == ["2026-09-22"]
    (day,) = data["days"]
    assert day["total"] == 132 and day["total_excluding_spam"] == 48
    assert day["by_status"] == {"spam": 84, "genuine": 41, "repost": 4, "unrelated": 3}
    texts = day["most_repeated_texts"]
    assert [t["count"] for t in texts[:4]] == [25, 22, 20, 17]
    assert all(t["statuses"] == {"spam": t["count"]} for t in texts[:4])
    assert all("T02:" <= t["first_posted_at"][10:] <= t["last_posted_at"][10:] < "T05:"
               for t in texts[:4])  # fmt: skip
    assert len(r["mention_ids"]) == 132 and "D-14" in r["method_note"]


def test_daily_activity_for_an_ordinary_day(call):
    data = call("daily_activity", day="2026-09-23")["data"]
    assert data["days"][0]["total"] == 52 and data["days"][0]["unusual"] is False
    with pytest.raises(ToolError, match="No data for"):
        call("daily_activity", day="2026-11-01")  # D-04


def test_registry(ctx, tmp_path):
    for tool in TOOLS.values():
        schema = tool.parameters
        assert tool.description and schema["type"] == "object"
        assert all("type" in p for p in schema["properties"].values()), tool.name
    with pytest.raises(ToolError, match="no tool named"):
        run_tool(ctx, "delete_everything", {})
    with pytest.raises(ToolError, match="takes no argument"):
        run_tool(ctx, "exclusions", {"brand": "brewbird"})
    with pytest.raises(ToolError, match="group_by must be one of"):
        run_tool(ctx, "count_mentions", {"group_by": "mood"})

    log = tmp_path / "tool_calls.jsonl"
    logged = ToolContext(ctx.store, ctx.client, tool_log=log)
    args = {"brand": "brewbird", "week": "2026-09-28", "city": None}
    first = run_tool(logged, "count_mentions", args)
    second = run_tool(logged, "count_mentions", args)
    assert first["result_id"] == second["result_id"] and first["result_id"].startswith("R-")
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(entries) == 2 and entries[0]["args"] == {"brand": "brewbird", "week": "2026-09-28"}
    assert entries[0]["result"]["data"]["window"] == {
        "start": date(2026, 9, 28).isoformat(), "end": "2026-10-04",
    }  # fmt: skip


# --- sentiment_trend, complaint_breakdown (step 3) --------------------------------------


def test_sentiment_trend_for_a_line_and_its_brand(call):  # D-40
    r = call("sentiment_trend", line="Nitro")
    data = r["data"]
    assert [w["net"] for w in data["weeks"]] == [0.33, 0.53, 0.73, 0.53, 0.03, 0.03, -0.27]
    assert [w["net"] for w in data["brand_overall"]] == [0.33, 0.45, 0.45, 0.44, 0.37, 0.32, 0.31]
    last = data["weeks"][-1]
    assert (last["week"], last["n"], last["negative"], last["pct_negative"]) == (
        "2026-09-28", 30, 19, 63.3,
    )  # fmt: skip
    # Without Nitro the brand does not fall: the drop is Nitro's.
    rest = [w["net"] for w in data["brand_without_this_line"]]
    assert min(rest[-3:]) >= min(rest[:4]) - 0.05
    assert len(r["mention_ids"]) == 211 and data["overall"]["n"] == 211


def test_sentiment_trend_direction_labels(call):  # D-45
    d = call("sentiment_trend", line="Nitro")["data"]["directions"]
    assert (d["weeks"]["label"], d["weeks"]["change"]) == ("falling", -0.6)
    assert d["weeks"]["moves_the_same_way"] == "3 of 6"
    assert d["brand_overall"]["label"] == "steady"
    assert (d["brand_without_this_line"]["label"], d["brand_without_this_line"]["change"]) == (
        "mildly rising", 0.13,
    )  # fmt: skip
    by_line = call("sentiment_trend", brand="brewbird", split_by_line=True)["data"]["directions"]
    assert by_line["by_line"]["brewbird:Nitro"]["label"] == "falling"
    small = call("sentiment_trend", line="Nitro", city="Delhi")["data"]["directions"]["weeks"]
    assert small["label"] == "too few weeks"


def test_sentiment_trend_flags_complaints_that_draw_outsized_likes(call):  # D-40
    weeks = call("sentiment_trend", line="Nitro")["data"]["weeks"]
    flagged = [w["week"] for w in weeks if w.get("complaints_draw_outsized_likes")]
    assert flagged == ["2026-09-21"]
    week = weeks[5]
    assert (round(week["pct_negative"]), round(week["negative_like_share"])) == (42, 57)


def test_sentiment_trend_split_by_line_and_small_weeks(call):
    by_line = call("sentiment_trend", brand="brewbird", split_by_line=True)["data"]["by_line"]
    assert set(by_line) == {
        "brewbird:Classic", "brewbird:Drip", "brewbird:Nitro", "brewbird:Origins", "brand-level",
    }  # fmt: skip
    assert by_line["brewbird:Nitro"][-1]["net"] == -0.27
    with pytest.raises(ToolError, match="needs a brand"):
        call("sentiment_trend", split_by_line=True)
    with pytest.raises(ToolError, match="takes no argument"):
        call("sentiment_trend", include_excluded=True)  # D-40: genuine conversations only
    small = call("sentiment_trend", line="Nitro", city="Delhi")["data"]["weeks"]
    assert any(w.get("too_few_to_read") and "net" not in w for w in small)


def test_complaint_breakdown(call):  # D-42, D-34
    r = call("complaint_breakdown", brand="brewbird", last_weeks=3)
    codes = r["data"]["codes"]
    assert [(c["code"], c["count"]) for c in codes] == [
        ("TST", 36), ("PRC", 23), ("DLV", 16), ("CSX", 11), ("PKG", 8), ("SUB", 7),
    ]  # fmt: skip
    tst = codes[0]
    assert tst["owner_team"] == "Quality Assurance" and tst["by_line"]["brewbird:Nitro"] == 29
    assert tst["client_rule"]  # the client's routing rule, verbatim
    assert all(len(c["examples"]) == 2 for c in codes)
    assert tst["examples"][0]["likes"] >= tst["examples"][1]["likes"]
    # D-42: two examples of a code are two different complaints, not one text posted twice.
    for c in codes:
        assert len({e["text"].lower().strip() for e in c["examples"]}) == 2, c["code"]
    assert r["source_refs"][0].startswith("client_complaint_taxonomy.csv:")

    nitro = call("complaint_breakdown", line="Nitro", top_n=1, examples=0)["data"]["codes"]
    assert [c["code"] for c in nitro] == ["TST"]
    assert list(nitro[0]["by_week"].values()) == [0, 0, 0, 0, 7, 9, 13]
    # D-31: competitor complaints carry sentiment and no client codes.
    other = call("complaint_breakdown", brand="saltmarsh")["data"]
    assert other["codes"] == [] and other["negative"] == other["negative_without_a_code"] > 0


# --- share_of_voice (step 4) ----------------------------------------------------------


def test_share_of_voice(call):  # D-41
    r = call("share_of_voice", last_weeks=4)
    data = r["data"]
    rows = {b["brand"]: b for b in data["brands"]}
    assert [(b["brand"], b["conversations"], round(b["share_pct"])) for b in data["brands"]] == [
        ("brewbird", 585, 56), ("saltmarsh", 210, 20), ("bluepeak", 198, 19), ("filterhaus", 48, 5),
    ]  # fmt: skip
    assert data["sum_of_brand_counts"] == 1041
    # D-25: a mention naming two brands is counted for each.
    assert data["distinct_conversations"] + data["naming_more_than_one_brand"] == 1041
    assert len(r["mention_ids"]) == data["distinct_conversations"]
    assert rows["bluepeak"]["of_which_by_line"] == {"bluepeak:Peak Instant": 100}  # D-21
    assert data["left_out"]["by_status"]["spam"] == 84
    assert "naive" not in data and "naive" not in r["method_note"]  # only on request


def test_share_of_voice_reach_is_reported_next_to_the_counts(call):  # D-44
    brewbird = call("share_of_voice")["data"]["brands"][0]
    assert brewbird["conversations"] == 987
    reach = brewbird["reach"]
    assert reach["reposts"] == 39 and reach["reposts_per_100_conversations"] == 4.0
    assert len(reach["most_reposted"]) == 3
    assert reach["most_reposted"][0]["reposts"] >= reach["most_reposted"][1]["reposts"]


def test_share_of_voice_naive_figure_on_request(call):  # D-41
    data = call("share_of_voice", last_weeks=4, compare_naive=True)["data"]
    naive = {b["brand"]: b for b in data["naive"]["brands"]}
    assert round(naive["brewbird"]["share_pct"]) == 66 and round(naive["bluepeak"]["share_pct"]) == 9
    # Why they differ: spam and the taproom inflate the client, the sub-brand is missed.
    assert naive["brewbird"]["matched_but_not_counted"]["spam"] == 84
    assert naive["brewbird"]["matched_but_not_counted"]["unrelated"] == 24
    assert naive["bluepeak"]["counted_but_not_matched"] == 100  # the Peak Instant mentions (ER-01)
    assert [round(b["share_pct"]) for b in data["brands"]] == [56, 20, 19, 5]  # unchanged


def test_share_of_voice_between_chosen_brands(call):
    data = call("share_of_voice", last_weeks=4, brands=["Brewbird", "Saltmarsh"])["data"]
    assert [(b["brand"], b["conversations"]) for b in data["brands"]] == [
        ("brewbird", 585), ("saltmarsh", 210),
    ]  # fmt: skip
    assert round(data["brands"][0]["share_pct"], 1) == round(100 * 585 / 795, 1)
    with pytest.raises(ToolError, match="at least two"):
        call("share_of_voice", brands=["Brewbird"])


def test_get_mentions_reads_page_by_page(call):
    """At most 50 a call, and the pages together are exactly the full list."""
    first = call("get_mentions", line="Nitro", limit=500)["data"]
    assert first["matched"] == 211 and first["returned"] == 50
    assert (first["limit_capped_at"], first["next_offset"]) == (50, 50)
    ids, offset = [], 0
    while offset is not None:
        page = call("get_mentions", line="Nitro", limit=50, offset=offset)["data"]
        ids += [m["mention_id"] for m in page["mentions"]]
        offset = page.get("next_offset")
    everything = call("count_mentions", line="Nitro")["mention_ids"]
    assert len(ids) == len(set(ids)) == 211 and set(ids) == set(everything)
    last = call("get_mentions", line="Nitro", limit=50, offset=200)["data"]
    assert last["returned"] == 11 and "next_offset" not in last
