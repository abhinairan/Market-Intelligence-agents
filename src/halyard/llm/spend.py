"""Spend from the usage log: tokens per model and purpose, priced where a price is known."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from halyard.llm.base import USAGE_LOG
from halyard.settings import PROJECT_ROOT

PRICES = PROJECT_ROOT / "config" / "llm_prices.yaml"


def load_prices(path: Path = PRICES) -> dict[str, dict[str, float]]:
    return yaml.safe_load(path.read_text()) or {}


def cost_usd(
    model: str, input_tokens: int, output_tokens: int, prices: dict[str, dict[str, float]]
) -> float | None:
    """Cost of these tokens, or None when the model has no price in the config."""
    price = prices.get(model)
    if price is None:
        return None
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


def summarise(
    usage_log: Path = USAGE_LOG,
    prices: dict[str, dict[str, float]] | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """One row per model and purpose, in first-seen order. `run_id` keeps one run only."""
    prices = load_prices() if prices is None else prices
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    if not usage_log.exists():
        return []
    with usage_log.open() as f:
        for line in f:
            call = json.loads(line)
            if run_id is not None and call.get("run_id") != run_id:
                continue
            row = rows.setdefault(
                (call["model"], call["purpose"]),
                {"model": call["model"], "purpose": call["purpose"], "calls": 0,
                 "input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0},
            )  # fmt: skip
            row["calls"] += 1
            for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
                row[key] += call.get(key, 0)
    for row in rows.values():
        row["cost_usd"] = cost_usd(row["model"], row["input_tokens"], row["output_tokens"], prices)
    return list(rows.values())
