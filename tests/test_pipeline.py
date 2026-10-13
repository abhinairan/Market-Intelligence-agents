"""The ingest steps end to end, offline: every label comes from the committed cache."""

from collections import Counter
from datetime import date, timedelta

import pytest

from halyard.ingest.pipeline import prepare
from halyard.settings import Settings, load_client

WEEKS = [date(2026, 8, 17) + timedelta(weeks=i) for i in range(7)]


@pytest.fixture(scope="module")
def prepared():
    # The provider and model the cache was filled with, and no API key.
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, load_client("brewbird"))
    return prepare(settings)


@pytest.fixture(scope="module")
def brewbird(prepared):
    """Genuine Brewbird conversations as (mention, lines, label)."""
    p = prepared
    return [
        (m, p.resolutions[m.mention_id].lines_of(p.client_brand), p.label_of(m.mention_id))
        for m in p.pack.mentions
        if p.statuses[m.mention_id] == "genuine"
        and p.resolutions[m.mention_id].names(p.client_brand)
    ]


def test_rebuild_needs_no_model_calls(prepared):  # PLAN §5a
    run = prepared.label_run
    assert (run.model_calls, run.unlabelled) == (0, 0) and run.cache_hits == 109
    assert len(prepared.labels) == 83


def test_only_genuine_texts_are_labelled(prepared):
    p = prepared
    for m in p.pack.mentions:
        if p.statuses[m.mention_id] in ("spam", "unrelated", "ambiguous"):
            assert p.label_of(m.mention_id) is None
        if p.statuses[m.mention_id] == "genuine":
            assert p.label_of(m.mention_id).sentiment in ("positive", "neutral", "negative")


def test_nitro_tst_by_week(brewbird):  # the headline finding
    by_week = Counter(
        m.week_ist for m, lines, label in brewbird
        if "Nitro" in lines and any(c.code == "TST" for c in label.codes)
    )  # fmt: skip
    assert [by_week[w] for w in WEEKS] == [0, 0, 0, 0, 7, 9, 13]


def test_complaint_codes_last_three_weeks(brewbird):  # D-42
    codes = Counter(
        c.code for m, _, label in brewbird if m.week_ist >= date(2026, 9, 14) for c in label.codes
    )
    assert codes == {"TST": 36, "PRC": 23, "DLV": 16, "CSX": 11, "PKG": 8, "SUB": 7}


def test_tst_and_pkg_boundary_and_routing(prepared):  # D-32, D-34
    labels = prepared.labels

    def codes(text):
        return [(c.code, c.owner_team) for c in labels[text].codes]

    assert codes("bb nitro can was swollen and leaking from the seal") == [
        ("TST", "Quality Assurance")
    ]
    assert codes("courier dented my brewbird nitro cans, one was leaking from the dent") == [
        ("PKG", "Logistics")
    ]
    assert codes("brewbird nitro box arrived crushed, two cans dented") == [("PKG", "Logistics")]
    sarcasm = labels["great, another bloated brewbird nitro can 🙄 love that for me"]
    assert sarcasm.sentiment == "negative" and [c.code for c in sarcasm.codes] == ["TST"]


def test_text_addressed_to_ai_tools_is_labelled_as_an_ordinary_complaint(prepared):  # D-64
    label = prepared.label_of("M11554")
    assert label.sentiment == "negative" and [c.code for c in label.codes] == ["TST"]


def test_competitor_complaints_get_sentiment_but_no_client_codes(prepared):  # D-31
    label = prepared.labels["saltmarsh support takes forever"]
    assert (label.sentiment, label.codes, label.codes_status) == ("negative", (), "not_applicable")
