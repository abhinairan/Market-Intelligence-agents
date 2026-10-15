"""Eval cases: each question from eval/*.yaml with the oracle's expected answer.

The expected answers (eval/expected/) are written by the independent oracle; nothing here
computes one. A question's `figures` in the YAML are paths into its expected file, so the
oracle stays the only source of values and the eval config only picks which are key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from halyard.settings import PROJECT_ROOT, HalyardError

EVAL_DIR = PROJECT_ROOT / "eval"
SETS = ("golden", "adversarial")
MENTION_ID = re.compile(r"^M\d+$")


@dataclass(frozen=True)
class Figure:
    path: str  # dotted path into the expected file, e.g. answer.by_line.Nitro
    value: float
    percent: bool = False  # a ratio that may also be written as a percentage (0.82 or 82%)


@dataclass(frozen=True)
class Case:
    id: str
    set: str  # golden or adversarial
    agent: str
    question: str
    expected: dict[str, Any]
    figures: tuple[Figure, ...] = ()
    expected_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def rubric(self) -> list[str]:
        return self.expected.get("rubric", [])

    @property
    def answerable(self) -> str:
        return self.expected["answerable"]


def resolve(data: Any, path: str) -> Any:
    """The value at a dotted path; a numeric part indexes a list."""
    node = data
    for part in path.split("."):
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise HalyardError(f"No `{path}` in the expected answer (stopped at `{part}`).")
    return node


def mention_ids_in(node: Any) -> set[str]:
    """Every mention ID anywhere under `node`."""
    if isinstance(node, str):
        return {node} if MENTION_ID.match(node) else set()
    children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
    return set().union(set(), *(mention_ids_in(x) for x in children))


def expected_name(qid: str) -> str:
    """The oracle's file stem: Q1 is q01, A-teams is a-teams."""
    return f"q{int(qid[1:]):02d}" if re.fullmatch(r"Q\d+", qid) else qid.lower()


def _figure(expected: dict[str, Any], spec: str | dict[str, Any], qid: str) -> Figure:
    path, percent = (spec, False) if isinstance(spec, str) else (spec["path"], spec.get("percent", False))
    value = resolve(expected, path)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise HalyardError(f"{qid}: `{path}` is {value!r}, not a number.")
    return Figure(path, float(value), percent)


def load_cases(
    only: list[str] | None = None, eval_dir: Path = EVAL_DIR, sets: tuple[str, ...] = SETS
) -> list[Case]:
    cases = []
    for name in sets:
        for q in yaml.safe_load((eval_dir / f"{name}.yaml").read_text())["questions"]:
            if only and q["id"] not in only:
                continue
            path = eval_dir / "expected" / f"{expected_name(q['id'])}.json"
            if not path.exists():
                raise HalyardError(f"No expected answer for {q['id']}: run `python -m oracle.run`.")
            expected = json.loads(path.read_text(encoding="utf-8"))
            cases.append(Case(
                q["id"], name, q["agent"], q["question"], expected,
                tuple(_figure(expected, f, q["id"]) for f in q.get("figures", [])),
                frozenset(mention_ids_in(expected.get("mention_ids", {}))),
            ))  # fmt: skip
    if only:
        missing = sorted(set(only) - {c.id for c in cases})
        if missing:
            raise HalyardError(f"No eval question with ID {', '.join(missing)}.")
    return cases
