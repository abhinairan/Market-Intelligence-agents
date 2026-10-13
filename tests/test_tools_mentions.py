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
    return lambda name, **args: run_tool(ctx, name, args, log=None)


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
    assert by_week == {"2026-09-14": 7, "2026-09-21": 9, "2026-09-28": 13}
    codes = _groups(call("count_mentions", brand="brewbird", last_weeks=3, group_by="code"))
    del codes["none"]
    assert codes == {"TST": 36, "PRC": 23, "DLV": 16, "CSX": 11, "PKG": 8, "SUB": 7}
    brands = call("count_mentions", last_weeks=4, group_by="brand")
    assert _groups(brands) == {"brewbird": 585, "saltmarsh": 210, "bluepeak": 198, "filterhaus": 48}
    assert sum(_groups(brands).values()) > brands["data"]["total"]  # D-25: two brands, two groups
    assert call("count_mentions", include_excluded=True)["data"]["total"] == 1904  # D-16


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
        run_tool(ctx, "delete_everything", {}, log=None)
    with pytest.raises(ToolError, match="takes no argument"):
        run_tool(ctx, "exclusions", {"brand": "brewbird"}, log=None)
    with pytest.raises(ToolError, match="group_by must be one of"):
        run_tool(ctx, "count_mentions", {"group_by": "mood"}, log=None)

    log = tmp_path / "tool_calls.jsonl"
    args = {"brand": "brewbird", "week": "2026-09-28", "city": None}
    first = run_tool(ctx, "count_mentions", args, log=log)
    second = run_tool(ctx, "count_mentions", args, log=log)
    assert first["result_id"] == second["result_id"] and first["result_id"].startswith("R-")
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(entries) == 2 and entries[0]["args"] == {"brand": "brewbird", "week": "2026-09-28"}
    assert entries[0]["result"]["data"]["window"] == {
        "start": date(2026, 9, 28).isoformat(), "end": "2026-10-04",
    }  # fmt: skip
