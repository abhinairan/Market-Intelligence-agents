"""Grading in code: key figures, cited mention IDs, `answerable` and the pass rule.

The rubric layer is graded by the judge (judge.py); everything here is deterministic.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from halyard.eval.cases import MENTION_ID, Case, Figure

# A number as written in prose: 987, 1,904, 0.82, .33, -0.27, −.27 (a minus only when it
# does not follow a digit or letter, so 499-799 and 2026-08-17 are not negatives).
NUMBER = re.compile(r"(?<![\w.])([-−])?(\d{1,3}(?:,\d{3})+|\d+)?(\.\d+)?(?![\d])")
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
WORD = re.compile(r"\b(" + "|".join(WORDS) + r")\b", re.IGNORECASE)
ID_THRESHOLD = 0.95  # agreed 14 Oct: ID precision and recall must both reach this


@dataclass(frozen=True)
class Number:
    value: float
    decimals: int


def numbers_in(text: str) -> list[Number]:
    out = []
    for m in NUMBER.finditer(text):
        sign, whole, frac = m.groups()
        if whole is None and frac is None:
            continue
        digits = (whole or "0").replace(",", "") + (frac or "")
        value = float(digits) * (-1 if sign else 1)
        out.append(Number(value, len(frac) - 1 if frac else 0))
    out += [Number(float(WORDS.index(m[1].lower())), 0) for m in WORD.finditer(text)]
    return out


def _decimals(value: float) -> int:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return len(text.split(".")[1]) if "." in text else 0


def matches(value: float, n: Number) -> bool:
    """`n` is `value` as written at its own precision: at most one decimal place coarser than
    the oracle's, and a value under 1 never rounded to a whole number (-0.27 is not 0)."""
    if n.decimals < _decimals(value) - 1:
        return False
    if n.decimals == 0 and value != int(value) and abs(value) < 1:
        return False
    return abs(round(value, n.decimals) - n.value) < 1e-9


def figure_found(fig: Figure, numbers: list[Number]) -> bool:
    forms = [fig.value] + ([round(fig.value * 100, 1)] if fig.percent else [])
    return any(matches(v, n) for v in forms for n in numbers)


def answer_text(answer: dict[str, Any] | None) -> str:
    """The answer and its claims as one text: what the figures are looked for in."""
    if not answer:
        return ""
    claims = [c.get("claim", "") for c in answer.get("claims", []) if isinstance(c, dict)]
    return "\n".join([answer.get("answer", ""), *claims, answer.get("needs", "")])


def grade_figures(case: Case, answer: dict[str, Any] | None) -> dict[str, Any] | None:
    if not case.figures:
        return None
    numbers = numbers_in(answer_text(answer))
    found = [f.path for f in case.figures if figure_found(f, numbers)]
    missing = [{"path": f.path, "value": f.value} for f in case.figures if f.path not in found]
    return {"found": found, "missing": missing, "passed": not missing}


def cited_sets(answer: dict[str, Any] | None, results: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    """The mention-ID sets the answer cites: one per cited result, one for the mention IDs
    cited directly, and their union."""
    sets: dict[str, set[str]] = {}
    direct: set[str] = set()
    for claim in (answer or {}).get("claims", []):
        for cite in claim.get("cites", []) if isinstance(claim, dict) else []:
            if cite in results:
                sets[cite] = set(results[cite].get("mention_ids", []))
            elif MENTION_ID.match(cite):
                direct.add(cite)
    if direct:
        sets["direct"] = direct
    if len(sets) > 1:
        sets["union"] = set().union(*sets.values())
    return sets


def grade_ids(case: Case, answer: dict[str, Any] | None, results: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Precision and recall of the cited mentions against the oracle's. The answer may cite
    several results (a line's figure and the brand's beside it), so the cited set compared is
    whichever of them, or their union, best matches the oracle's set (highest F1)."""
    if not case.expected_ids:
        return None
    expected = case.expected_ids
    best = {"set": None, "precision": 0.0, "recall": 0.0, "f1": 0.0, "cited": 0}
    for name, ids in cited_sets(answer, results).items():
        hit = len(ids & expected)
        p, r = (hit / len(ids) if ids else 0.0), hit / len(expected)
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        if f1 > best["f1"]:
            best = {"set": name, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3), "cited": len(ids)}
    best["expected"] = len(expected)
    best["passed"] = best["precision"] >= ID_THRESHOLD and best["recall"] >= ID_THRESHOLD
    return best


@dataclass
class Grade:
    """One run of one question, graded on every layer that applies to it."""

    case_id: str
    run_id: str
    status: str  # the agent run's status: answered, failed_check or error
    answerable: dict[str, Any]
    figures: dict[str, Any] | None = None
    ids: dict[str, Any] | None = None
    rubric: dict[str, Any] | None = None
    second_rubric: dict[str, Any] | None = None  # the calibration judge, when one ran
    cost_usd: float | None = None
    tokens: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        layers = [self.figures, self.ids, self.rubric]
        return (
            self.status == "answered"
            and self.answerable["passed"]
            and all(layer["passed"] for layer in layers if layer and not layer.get("skipped"))
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"passed": self.passed}


def grade_answerable(case: Case, answer: dict[str, Any] | None) -> dict[str, Any]:
    got = (answer or {}).get("answerable")
    return {"expected": case.answerable, "got": got, "passed": got == case.answerable}
