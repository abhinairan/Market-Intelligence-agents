from collections import Counter
from dataclasses import replace
from datetime import date

import pytest

from halyard.ingest.loaders import LoadError, load_mentions, load_pack, parse_pack, week_start
from halyard.ingest.records import SourceRef
from halyard.settings import load_client

WEEKS = [date(2026, 8, 17), date(2026, 8, 24), date(2026, 8, 31), date(2026, 9, 7),
         date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28)]  # fmt: skip
HEADER = "mention_id,platform,posted_at,author_handle,text,likes,is_repost_of,url"


@pytest.fixture(scope="module")
def pack():
    return load_pack(load_client("brewbird"))


def _client(tmp_path, *rows):
    tmp_path.joinpath("mentions.csv").write_text("\r\n".join([HEADER, *rows]) + "\r\n", newline="")
    return replace(load_client("brewbird"), data_pack=tmp_path)


def test_every_file_in_the_pack_is_loaded(pack):
    sizes = (len(pack.products), len(pack.taxonomy), len(pack.prices), len(pack.ads))
    assert sizes == (7, 6, 7, 19)
    assert Counter(p.kind for p in pack.pages) == {"brand_site": 2, "competitor_snapshots": 6}


def test_duplicates_collapse_and_keep_their_rows(pack):  # D-10
    assert (pack.report.mention_rows, len(pack.mentions)) == (1922, 1904)
    assert (pack.report.duplicate_rows, pack.report.id_conflicts) == (18, 0)
    assert len({m.mention_id for m in pack.mentions}) == 1904
    m = next(m for m in pack.mentions if m.mention_id == "M10149")
    assert (str(m.source), m.source_rows) == ("mentions.csv:158", (158, 159))
    assert sum(len(m.source_rows) for m in pack.mentions) == 1922


def test_same_id_with_different_content_keeps_both(tmp_path):  # D-10
    a = "M1,x,2026-08-17T10:00:00+05:30,h,one,1,,u"
    mentions, report = load_mentions(_client(tmp_path, a, a.replace("one", "two")), "mentions.csv")
    assert [(m.text, m.id_conflict) for m in mentions] == [("one", True), ("two", True)]
    assert (report.duplicate_rows, report.id_conflicts) == (0, 1)


def test_dates_and_weeks_use_the_exported_clock_time(pack):  # D-01, D-02
    m = pack.mentions[0]
    # 00:29 IST on Monday 17 Aug is still 16 Aug in UTC.
    assert m.posted_at == "2026-08-17T00:29:34+05:30"
    assert (m.date_ist, m.week_ist) == (date(2026, 8, 17), date(2026, 8, 17))
    assert sorted({m.week_ist for m in pack.mentions}) == WEEKS
    assert all(m.posted_at[:10] == m.date_ist.isoformat() for m in pack.mentions)
    assert (pack.report.other_offsets, pack.report.out_of_window) == (0, 0)


def test_another_offset_is_moved_to_client_time_not_utc(tmp_path):  # D-01
    row = "M1,x,2026-08-23T20:00:00+00:00,h,late on Sunday in UTC,1,,u"
    mentions, report = load_mentions(_client(tmp_path, row), "mentions.csv")
    assert mentions[0].posted_at == "2026-08-23T20:00:00+00:00"
    assert (mentions[0].date_ist, mentions[0].week_ist) == (date(2026, 8, 24), date(2026, 8, 24))
    assert report.other_offsets == 1


def test_week_start():  # D-02
    assert week_start(date(2026, 10, 4), "monday") == date(2026, 9, 28)
    assert week_start(date(2026, 9, 28), "monday") == date(2026, 9, 28)
    assert week_start(date(2026, 9, 28), "sunday") == date(2026, 9, 27)


def test_city_tag_is_extracted_and_text_untouched(pack):  # D-26
    assert Counter(m.city for m in pack.mentions if m.city) == {
        "Bangalore": 175, "Delhi": 167, "Mumbai": 160,
    }  # fmt: skip
    by_id = {m.mention_id: m for m in pack.mentions}
    assert by_id["M10002"].city == "Delhi" and by_id["M10002"].text.endswith("(delhi)")
    assert by_id["M11838"].city == "Bangalore"  # tag sits before "#repost via"
    assert by_id["M10001"].city is None
    assert not pack.report.unrecognised_tags


def test_unknown_bracketed_tag_is_reported_not_guessed(tmp_path):  # D-26
    row = "M1,x,2026-08-17T10:00:00+05:30,h,great coffee (again),1,,u"
    mentions, report = load_mentions(_client(tmp_path, row), "mentions.csv")
    assert mentions[0].city is None and report.unrecognised_tags == {"again": 1}


def test_mention_fields(pack):
    assert sum(1 for m in pack.mentions if m.is_repost_of) == 38  # D-11 (a), tool flag only
    assert all(isinstance(m.likes, int) for m in pack.mentions)
    assert len({m.platform for m in pack.mentions}) == 6


def test_pack_sizes():  # D-53
    at = SourceRef("t.csv", 2)
    assert [(p.unit_count, p.unit_size, p.unit) for p in (
        parse_pack("6 x 200ml", at), parse_pack("250g", at),
        parse_pack("10 bags", at), parse_pack("100g jar", at),
    )] == [(6, 200, "ml"), (1, 250, "g"), (10, 1, "bag"), (1, 100, "g")]  # fmt: skip
    with pytest.raises(LoadError, match="t.csv:2"):
        parse_pack("family size", at)


def test_products_prices_ads_and_pages(pack):
    nitro = next(p for p in pack.products if p.sku == "BB-NIT-6")
    assert (nitro.price_inr, nitro.pack.unit_count, nitro.aliases[0]) == (660, 6, "BB Nitro")
    assert str(nitro.source) == "products.csv:6"
    assert {t.code: t.owner_team for t in pack.taxonomy}["TST"] == "Quality Assurance"
    assert sum(1 for t in pack.taxonomy if t.client_rule) == 2
    aed = next(p for p in pack.prices if p.currency == "AED")
    assert (aed.price, aed.region, aed.captured_at) == (45, "AE", date(2026, 9, 18))
    assert sum(1 for a in pack.ads if a.offer) == 8
    shipping = [p for p in pack.pages if "shipping" in p.source.file]
    assert [p.captured_at for p in shipping] == [date(2025, 11, 3), date(2026, 9, 20)]
    assert shipping[0].url == "bluepeak.example/shipping" and "Rs 499" in shipping[0].body
    assert shipping[0].source.row == 2


def test_wrong_columns_is_a_clear_error(tmp_path):
    tmp_path.joinpath("mentions.csv").write_text("id,text\n1,hi\n")
    with pytest.raises(LoadError, match="expected columns"):
        load_mentions(replace(load_client("brewbird"), data_pack=tmp_path), "mentions.csv")
