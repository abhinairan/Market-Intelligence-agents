"""Tests for the independent oracle."""
import ast
import json
from pathlib import Path

import pytest

from oracle import golden, rules
from oracle.selfcheck import run as selfcheck

ORACLE = Path(__file__).resolve().parent.parent / "oracle"
EXPECTED = ORACLE.parent / "eval" / "expected"


@pytest.fixture(scope="module")
def df():
    return rules.mentions()


def test_oracle_never_imports_the_pipeline():
    for path in ORACLE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                assert not name.split(".")[0] in {"src", "halyard"}, f"{path.name} imports {name}"


def test_selfcheck_matches_definitions(df):
    failed = [c for c in selfcheck(df) if not c["ok"]]
    assert not failed, failed


def test_committed_expected_answers_are_current(df):
    for i, fn in enumerate(golden.ALL, start=1):
        committed = json.loads((EXPECTED / f"q{i:02d}.json").read_text(encoding="utf-8"))
        fresh = json.loads(json.dumps(fn(df), default=str))
        committed = {k: v for k, v in committed.items() if k not in ("id", "status")}
        assert committed == fresh, f"q{i:02d}.json is stale: run python -m oracle.run"


@pytest.mark.parametrize("text,expected", [
    ("PSA: Brewbird Nitro cans puffed up in the box, whole 6 pack!!", "brewbird nitro cans puffed up in the box, whole 6 pack"),
    ("honestly brewbird nitro cans puffed up in the box, whole 6 pack #coffee", "brewbird nitro cans puffed up in the box, whole 6 pack"),
    ("RT @kabir747: Stocked the fridge with Brewbird Nitro cold brew cans for the week (Delhi)", "stocked the fridge with brewbird nitro cold brew cans for the week"),
    ("Peak Instant sachets in my bag always #coffee #repost via @rohan_6205", "peak instant sachets in my bag always"),
])
def test_normalise(text, expected):
    assert rules.normalise(text) == expected


def test_ist_weeks_not_utc(df):
    # M10928 is posted 00:12 IST on Monday 14 Sep: in UTC it would fall in the previous week (D-01).
    row = df[df["mention_id"] == "M10928"].iloc[0]
    assert str(row["week_ist"]) == "2026-09-14"


def test_bb50_is_not_a_brewbird_reference(df):
    spam = df[df["status"] == "spam"]
    assert spam["text"].str.contains("BB50").all()
    assert not rules.genuine(df)["mention_id"].isin(spam["mention_id"]).any()


def test_half_price_claim_uses_inr_only(df):
    q8 = golden.q08(df)["answer"]
    assert q8["list_ratio"] == pytest.approx(90 / 110, abs=1e-3)
    assert q8["verdict"] == "not accurate"


def test_shipping_change_is_a_range(df):
    change = golden.q10(df)["answer"]["changed"][0]
    assert (change["changed_after"], change["changed_by"]) == ("2025-11-03", "2026-08-18")
