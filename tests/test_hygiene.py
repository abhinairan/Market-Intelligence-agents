from collections import Counter
from dataclasses import replace

import pytest

from halyard.ingest.hygiene import Normaliser, load_hygiene_config, run_hygiene
from halyard.ingest.loaders import load_mentions, load_pack
from halyard.settings import load_client

HEADER = "mention_id,platform,posted_at,author_handle,text,likes,is_repost_of,url"


@pytest.fixture(scope="module")
def client():
    return load_client("brewbird")


@pytest.fixture(scope="module")
def mentions(client):
    return load_pack(client).mentions


@pytest.fixture(scope="module")
def hygiene(mentions, client):
    return run_hygiene(mentions, client)


def _run(tmp_path, client, *rows):
    lines = [HEADER, *(f"M{i},{r},1,,u" for i, r in enumerate(rows, 1))]
    tmp_path.joinpath("mentions.csv").write_text("\n".join(lines) + "\n")
    tmp = replace(client, data_pack=tmp_path)
    return run_hygiene(load_mentions(tmp, "mentions.csv")[0], tmp)


def test_normalised_text_strips_decoration_only(client):  # D-12
    norm = Normaliser(load_hygiene_config(client), client.raw["city_tags"])
    plain = "brewbird nitro order delayed twice, still waiting"
    assert norm("PSA: Brewbird Nitro order delayed twice, still waiting lol") == plain
    assert norm("ok so Brewbird Nitro order delayed twice, still waiting (Delhi) #coffee") == plain
    assert norm("RT @pooja1231: Brewbird Nitro order delayed twice, still waiting 👍") == plain
    assert norm(f"{plain} (mumbai) #repost via @pooja1231") == plain
    # Meaning is kept: an emoji inside the text, and words that only end like a decoration.
    assert "🙄" in norm("great, another bloated Brewbird nitro can 🙄 love that for me")
    assert norm("Brewbird nitro is safe??") == "brewbird nitro is safe??"
    assert norm("that was a trolol") == "that was a trolol"


def test_stored_text_is_never_altered(mentions, hygiene):  # D-12
    m = next(m for m in mentions if m.mention_id == "M10001")
    assert m.text.startswith("PSA: ") and m.text.endswith("#coffee")
    assert hygiene.normalised["M10001"].startswith("switched from instant")


def test_reposts_by_basis_all_linked(mentions, hygiene):  # D-11
    by_id = {m.mention_id: m for m in mentions}
    assert Counter((r.basis, r.method) for r in hygiene.reposts.values()) == {
        ("tool_flag", "extracted"): 38,
        ("rt_text", "inferred"): 15,
        ("repost_via_text", "inferred"): 17,
    }
    for mention_id, r in hygiene.reposts.items():
        original = by_id[r.original_id]
        assert original.posted_at < by_id[mention_id].posted_at
        assert hygiene.normalised[r.original_id] == hygiene.normalised[mention_id]
        assert hygiene.status(r.original_id) is None
        if r.quoted_handle:
            assert original.author_handle == r.quoted_handle
    assert sum(hygiene.repost_counts.values()) == 70  # D-44


def test_identical_text_alone_is_not_a_repost(tmp_path, client):  # D-12
    h = _run(
        tmp_path, client,
        "x,2026-08-17T10:00:00+05:30,a,Brewbird is my go-to coffee brand now",
        "x,2026-08-17T11:00:00+05:30,b,Brewbird is my go-to coffee brand now lol",
        "x,2026-08-17T12:00:00+05:30,c,RT @nobody: Brewbird is my go-to coffee brand now",
    )  # fmt: skip
    assert set(h.reposts) == {"M3"}
    assert h.reposts["M3"].original_id is None  # quoted handle has no such post: unlinked


def test_spam_burst(mentions, hygiene):  # D-13
    assert len(hygiene.spam) == 84 and len(hygiene.bursts) == 4
    spam = [m for m in mentions if m.mention_id in hygiene.spam]
    assert {m.date_ist.isoformat() for m in spam} == {"2026-09-22"}
    assert {m.posted_at[11:13] for m in spam} == {"02", "03", "04"}
    families = Counter(m.author_handle.rsplit("_", 1)[0] for m in spam)
    assert set(families) == {"coupon_kart", "lootbazaar", "dealsloot"}
    assert set(hygiene.account_classes.values()) == {"coupon_bot"}
    assert len(hygiene.account_classes) == 84


def test_spam_needs_a_burst_and_a_promo_marker(tmp_path, client):  # D-13
    def rows(text, handles, hours):
        return [f"x,2026-08-17T{h:02d}:00:00+05:30,{u},{text}" for u, h in zip(handles, hours)]

    promo = "Grab Brewbird at half price with code BB50"
    h = _run(
        tmp_path, client,
        *rows(promo, "abcde", [1, 2, 3, 4, 5]),  # five handles in six hours: spam
        *rows(promo + " today", "abcde", [1, 2, 3, 4, 12]),  # only four inside any window
        *rows("Brewbird is my go-to coffee brand now", "abcde", [1, 2, 3, 4, 5]),  # no promo
        *rows(promo + " now", "aaaab", [1, 2, 3, 4, 5]),  # two handles
    )  # fmt: skip
    assert set(h.spam) == {"M1", "M2", "M3", "M4", "M5"}


def test_double_post_is_same_author_platform_and_day(tmp_path, client):  # D-17
    text = "Brewbird Nitro order delayed twice and still waiting"
    h = _run(
        tmp_path, client,
        f"x,2026-08-17T10:00:00+05:30,a,{text}",
        f"x,2026-08-17T20:00:00+05:30,a,{text} lol",  # same platform within 24h
        f"instagram,2026-08-17T20:00:00+05:30,a,{text}",  # cross-post: its own conversation
        f"x,2026-08-19T10:00:00+05:30,a,{text}",  # more than 24h later
        f"x,2026-08-17T20:00:00+05:30,b,{text}",  # another author
    )  # fmt: skip
    assert h.double_posts == {"M2": "M1"}
    assert h.status("M2") == "double_post" and h.status("M3") is None


def test_status_counts(mentions, hygiene):  # D-15 inputs; entity rules come in step 4
    assert not hygiene.double_posts
    assert Counter(hygiene.status(m.mention_id) for m in mentions) == {
        None: 1750, "spam": 84, "repost": 70,
    }  # fmt: skip
