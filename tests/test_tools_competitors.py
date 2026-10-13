"""competitor_observations, price_compare and competitor_ads (P3 step 5)."""

import pytest

from halyard.ingest.graph import build_graph
from halyard.ingest.pipeline import prepare
from halyard.settings import Settings, load_client
from halyard.store.graph_store import MemoryStore
from halyard.tools.base import ToolError
from halyard.tools.context import ToolContext
from halyard.tools.registry import run_tool


@pytest.fixture(scope="module")
def call():
    client = load_client("brewbird")
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client)
    ctx = ToolContext(MemoryStore(build_graph(prepare(settings), client)), client)
    return lambda name, **args: run_tool(ctx, name, args, log=None)


# --- price_compare --------------------------------------------------------------------


def test_price_compare_per_can_in_the_same_market(call):  # D-53
    r = call("price_compare", a="Saltmarsh Nitro", b="Brewbird Nitro")
    (row,) = r["data"]["comparisons"]
    assert (row["region"], row["currency"]) == ("IN", "INR")
    assert row["per_unit"] == {"unit": "200 ml", "a": 90.0, "b": 110.0, "ratio_a_to_b": 0.82}
    assert row["per_100"]["ratio_a_to_b"] == 0.82 and row["a_cheaper_by_pct"] == 18.2
    # Each price says how old it is; the client's catalogue price has no date (D-52).
    assert row["a"]["observed_at"] == "2026-09-15" and row["a"]["age_days"] == 19
    assert "undated" in row["b"]["dated"] and "observed_at" not in row["b"]
    assert r["source_refs"] == [
        "competitor_pricing.csv:2", "competitor_pricing.csv:3", "products.csv:6",
    ]  # fmt: skip


def test_price_compare_never_converts_currencies(call):  # D-53
    data = call("price_compare", a="Saltmarsh Nitro", b="Brewbird Nitro")["data"]
    (aed,) = data["not_compared"]
    assert (aed["currency"], aed["region"], aed["value"]) == ("AED", "AE", 45)
    assert "never converted" in aed["why"]
    only_ae = call("price_compare", a="Saltmarsh Nitro", b="Brewbird Nitro", region="AE")["data"]
    assert only_ae["comparisons"] == []


def test_price_compare_checks_a_claim_at_list_price_and_with_offers(call):  # D-53, O-5
    data = call(
        "price_compare", a="Saltmarsh Nitro", b="Brewbird Nitro", claimed_ratio=0.5,
        include_offers=True,
    )["data"]  # fmt: skip
    (row,) = data["comparisons"]
    assert row["claim"] == {
        "claimed_ratio": 0.5, "accepted_up_to": 0.55, "holds_at_list_price": False,
    }  # fmt: skip
    (offer,) = row["a_with_offers"]
    assert offer["offer"] == "Launch offer: 30% off your first order"
    assert (offer["a_with_offer"], offer["ratio_a_to_b"]) == (63.0, 0.57)
    assert offer["claim_holds_with_offer"] is False and offer["conditional"]
    assert row["per_unit"]["a"] == 90.0  # the list price is untouched


def test_price_compare_by_weight_and_with_history(call):
    data = call("price_compare", a="Chikmagalur Medium Roast", b="Classic Filter Blend")["data"]
    (row,) = data["comparisons"]
    assert row["a"]["value"] == 450 and row["a"]["stale"] is False  # the 2025 price is history
    assert row["per_100"] == {"unit": "100 g", "a": 180.0, "b": 170.0, "ratio_a_to_b": 1.06}
    # Different units are never compared: cans against drip bags.
    assert call("price_compare", a="Saltmarsh Nitro", b="Drip")["data"]["comparisons"] == []
    with pytest.raises(ToolError, match="not a product line or product"):
        call("price_compare", a="Saltmarsh Nitro", b="Oat Latte")
    with pytest.raises(ToolError, match="needs b"):
        call("price_compare", a="Saltmarsh Nitro")


# --- competitor_observations ----------------------------------------------------------


def test_a_change_is_a_date_range_not_a_capture_date(call):  # D-51
    r = call("competitor_observations", kind="free_shipping_threshold")
    (change,) = r["data"]["changes"]
    assert change["brand"] == "bluepeak"
    assert (change["from"]["value"], change["to"]["value"]) == (499, 799)
    assert change["changed_between"] == {"after": "2025-11-03", "on_or_before": "2026-08-18"}
    assert change["to"]["first_observed_at"] == "2026-09-20"  # when it was captured
    evidence = change["earliest_evidence_of_new_value"]
    assert evidence["mention_id"] == "M10049" and r["mention_ids"] == ["M10049"]
    # One observation is no evidence of a change, not evidence of none.
    assert {s["brand"] for s in r["data"]["seen_only_once"]} == {"brewbird", "saltmarsh"}


def test_observations_carry_their_age(call):  # D-50, D-52
    data = call("competitor_observations", brand="Bluepeak")["data"]
    by_ref = {o["source_ref"]: o for o in data["observations"]}
    old = by_ref["competitor_snapshots/bluepeak_shipping_2025-11-03.md:4"]
    assert old["stale"] is True and old["age_days"] == 335
    assert by_ref["competitor_snapshots/bluepeak_shipping_2026-09-20.md:4"]["stale"] is False
    prices = [c for c in data["changes"] if c["kind"] == "price"]
    assert [(c["from"]["value"], c["to"]["value"]) for c in prices] == [(420, 450)]
    assert prices[0]["changed_between"] == {"after": "2025-11-03", "on_or_before": "2026-09-20"}
    with pytest.raises(ToolError, match="not a kind of observation"):
        call("competitor_observations", kind="wholesale_price")


def test_launch_is_dated_by_the_first_party_statement(call):  # D-55
    r = call("competitor_observations", line="Saltmarsh Nitro", kind="launch")
    (launch,) = r["data"]["observations"]
    assert launch["observed_at"] == "2026-09-14" and launch["text"].startswith("today launched")
    support = launch["corroborated_by"]
    assert support["first_ad"]["first_seen"] == "2026-09-15"
    assert support["first_customer_mention"]["date"] == "2026-09-14"
    assert r["source_refs"] == ["competitor_snapshots/saltmarsh_nitro_launch_2026-09-14.md:4"]


# --- competitor_ads -------------------------------------------------------------------


def test_competitor_ads(call):  # D-54
    r = call("competitor_ads", line="Saltmarsh Nitro")
    data = r["data"]
    assert data["ads"] == data["still_running"] == 14 and data["first_seen"] == "2026-09-15"
    assert sum(m["ads"] for m in data["messages"]) == 14 and len(r["source_refs"]) == 14
    assert "still running as of 2026-10-04" in r["method_note"]

    (claim,) = call("competitor_ads", text="half the price")["data"]["messages"]
    assert claim["advertiser"] == "saltmarsh" and claim["ads"] == 4
    assert claim["first_seen"] == "2026-09-19" and claim["offer"] == "Launch: 30% off first order"
    assert claim["other_brands_named"] == []  # D-53: "the other guys" names nobody

    ended = call("competitor_ads", brand="Filterhaus")["data"]
    assert ended["ads"] == 1 and ended["still_running"] == 0
    assert call("competitor_ads", week="2026-08-17")["data"]["ads"] == 2  # running that week
