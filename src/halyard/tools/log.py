"""The tool-call log: every call an agent makes, kept whole under a result ID.

An agent is sent a capped result; the full one, with every mention ID, stays here so a
follow-up question or a trace can get it back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halyard.settings import PROJECT_ROOT

TOOL_LOG = PROJECT_ROOT / "outputs" / "tool_calls.jsonl"
RESULT_PREFIX = "R-"


def record(log: Path, entry: dict[str, Any]) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def find(log: Path | None, result_id: str) -> dict[str, Any] | None:
    """The most recent logged call with this result ID."""
    if log is None or not log.exists():
        return None
    found = None
    with log.open(encoding="utf-8") as f:
        for line in f:
            if result_id in line:
                entry = json.loads(line)
                if entry["result_id"] == result_id:
                    found = entry
    return found
