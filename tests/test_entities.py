from collections import Counter
from datetime import date

import pytest

from halyard.ingest.entities import (
    EntityResolver,
    load_entities_config,
    mention_status,
    resolve_entities,
)
from halyard.ingest.hygiene import run_hygiene
from halyard.ingest.loaders import load_pack
from halyard.settings import HalyardError, load_client


@pytest.fixture(scope="module")
def client():
    return load_client("brewbird")


@pytest.fixture(scope="module")
def pack(client):
    return load_pack(client)


@pytest.fixture(scope="module")
def resolver(client, pack):
    return EntityResolver(load_entities_config(client), pack.products)


@pytest.fixture(scope="module")
def resolved(client, pack):
    """(mention, resolution, status) for every mention in the pack."""
    hygiene = run_hygiene(pack.mentions, client)
    res = resolve_entities(pack.mentions, pack.products, client)
    return [
        (m, res[m.mention_id], mention_status(hygiene.status(m.mention_id), res[m.mention_id]))
        for m in pack.mentions
    ]


def _brands(r):
    return [b.brand for b in r.brands]


def test_brewbird_reference(resolver):  # D-20
    r = resolver.resolve("love the taste but Brewbird filter blend is getting too pricey")
    assert _brands(r) == ["brewbird"] and r.lines_of("brewbird") == ("Classic",)
    assert (r.brands[0].matched, r.brands[0].rule) == ("Brewbird", "D-20")
    assert (r.lines[0].matched, r.lines[0].rule) == ("filter blend", "D-24")
    r = resolver.resolve("BB Nitro after a run hits different")
    assert _brands(r) == ["brewbird"] and r.lines_of("brewbird") == ("Nitro",)
    # ER-10: a coupon code that starts with BB is not a reference.
    assert resolver.resolve("use code BB50 for half price nitro").status == "unresolved"


def test_line_word_without_the_brand_is_not_brewbird(resolver):  # D-24, ER-11, ER-13
    r = resolver.resolve("new nitro cans from Saltmarsh are on Blinkit already")
    assert _brands(r) == ["saltmarsh"] and r.lines_of("saltmarsh") == ("Saltmarsh Nitro",)
    assert resolver.resolve("drip bags are great for travel").status == "unresolved"
    # A Brewbird mention that names no line stays brand-level, never guessed.
    r = resolver.resolve("is Brewbird a Bangalore company?")
    assert _brands(r) == ["brewbird"] and r.lines == ()


def test_competitors(resolver):  # D-21, D-25
    r = resolver.resolve("Peak Instant jar lid broke on delivery")
    assert _brands(r) == ["bluepeak"] and r.lines_of("bluepeak") == ("Peak Instant",)
    assert r.brands[0].matched == "Peak Instant"
    assert _brands(resolver.resolve("@saltmarshcoffee delivery was super quick")) == ["saltmarsh"]
    r = resolver.resolve("Saltmarsh vs Bluepeak for French press, which one?")
    assert _brands(r) == ["saltmarsh", "bluepeak"]


def test_taproom_and_popup_are_set_aside(resolver):  # D-22, D-23
    r = resolver.resolve("Friday at Brewbird taproom, the wheat beer is so good")
    assert (r.status, r.set_aside.key, r.set_aside.rule) == ("unrelated", "brewbird_taproom", "D-22")
    assert r.brands == () and r.lines == ()
    r = resolver.resolve("Brewbird pop-up at the Bandra flea this weekend?")
    assert (r.status, r.set_aside.key) == ("ambiguous", "bandra_popup")
    # Whole words only: "bar" is not in "Baba Budangiri", and Pune alone decides nothing.
    r = resolver.resolve("Baba Budangiri from Brewbird Origins, delivered to Pune")
    assert r.status is None and r.lines_of("brewbird") == ("Origins",)
    # A beer word without the brand name sets nothing aside.
    assert _brands(resolver.resolve("Saltmarsh at the bar")) == ["saltmarsh"]


def test_implied_reference_is_recorded_not_counted(resolver):  # D-20, ER-12
    r = resolver.resolve("Saltmarsh Nitro vs the other nitro cans, anyone compared?")
    assert _brands(r) == ["saltmarsh"] and r.implied == ("the other nitro cans",)


def test_every_catalogue_sub_brand_needs_a_line(client, pack):
    config = load_entities_config(client)
    config["brands"][0]["lines"] = config["brands"][0]["lines"][:-1]
    with pytest.raises(HalyardError, match="Brewbird Origins"):
        EntityResolver(config, pack.products)


def test_statuses_and_nothing_unresolved(resolved):  # D-15, D-16
    assert Counter(s for _, _, s in resolved) == {
        "genuine": 1686, "spam": 84, "repost": 70, "unrelated": 42, "ambiguous": 22,
    }  # fmt: skip
    assert not [m.mention_id for m, r, _ in resolved if r.status == "unresolved"]
    # Before hygiene: 45 taproom and 23 pop-up mentions, 4 of them reposts (D-22, D-23).
    assert Counter(r.status for _, r, _ in resolved if r.status) == {
        "unrelated": 45, "ambiguous": 23,
    }  # fmt: skip


def test_genuine_brewbird_conversations_by_line(resolved):  # D-15, D-24
    bb = [(m, r) for m, r, s in resolved if s == "genuine" and r.names("brewbird")]
    assert len(bb) == 987 and len({m.author_handle for m, _ in bb}) == 984
    by_line = Counter(r.lines_of("brewbird") or ("brand-level",) for _, r in bb)
    assert by_line == {
        ("Classic",): 246, ("Nitro",): 211, ("Origins",): 203, ("Drip",): 175,
        ("brand-level",): 152,
    }  # fmt: skip
    reposts = sum(1 for _, r, s in resolved if s == "repost" and r.names("brewbird"))
    assert reposts == 39  # D-44


def test_share_of_voice_counts_last_four_weeks(resolved):  # D-41, D-25
    counts = Counter(
        b.brand
        for m, r, s in resolved
        if s == "genuine" and m.week_ist >= date(2026, 9, 7)
        for b in r.brands
    )
    assert counts == {"brewbird": 585, "saltmarsh": 210, "bluepeak": 198, "filterhaus": 48}


def test_peak_instant_and_generic_line_words(resolved):  # D-21, D-24
    peak = [r for _, r, _ in resolved if "Peak Instant" in r.lines_of("bluepeak")]
    assert len(peak) == 180
    assert all(r.brands[0].matched.lower() == "peak instant" for r in peak)
    nitro_only = [r for _, r, _ in resolved if r.lines_of("saltmarsh") == ("Saltmarsh Nitro",)]
    assert len(nitro_only) == 91 and not any(r.names("brewbird") for r in nitro_only)
