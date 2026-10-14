"""The rubric judge: one model call per answer, each item met or not with a quote.

The judge sees the question, the rubric items and the answer (text and claims with their
cites), nothing else: figures and IDs are graded in code. A "met" verdict counts only when
its quote is found in the answer, so the judge cannot pass an item on a passage it made up.
"""

from __future__ import annotations

import json
import re
from typing import Any

from halyard.eval.cases import Case
from halyard.llm import LLMClient
from halyard.settings import PROJECT_ROOT

PROMPT = PROJECT_ROOT / "skills" / "eval" / "judge.md"

SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "integer"},
                    "met": {"type": "boolean"},
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["item", "met", "quote", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


def _plain(text: str) -> str:
    """For finding a quote: one space for any whitespace, straight quotes and dashes, no
    markdown emphasis or code marks, lower case."""
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-"}))
    text = re.sub(r"[*`]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_found(quote: str, haystack: str) -> bool:
    """Every fragment of the quote (fragments are joined with an ellipsis) is in the answer."""
    fragments = [_plain(f).strip(" .,;") for f in re.split(r"…|\.\.\.", quote)]
    fragments = [f for f in fragments if f]
    return bool(fragments) and all(f in haystack for f in fragments)


def answer_payload(answer: dict[str, Any] | None) -> dict[str, Any]:
    answer = answer or {}
    return {
        "answer": answer.get("answer", ""),
        "claims": [{"claim": c.get("claim", ""), "cites": c.get("cites", [])}
                   for c in answer.get("claims", []) if isinstance(c, dict)],
        "answerable": answer.get("answerable"),
        "needs": answer.get("needs", ""),
    }  # fmt: skip


def judge(client: LLMClient, case: Case, answer: dict[str, Any] | None) -> dict[str, Any] | None:
    """Every rubric item of `case` judged against `answer`; None when the case has none."""
    if not case.rubric:
        return None
    payload = answer_payload(answer)
    case_json = {
        "question": case.question,
        "rubric": [{"item": i, "text": t} for i, t in enumerate(case.rubric, 1)],
        "answer": payload,
    }
    user = f"<case>\n{json.dumps(case_json, ensure_ascii=False, indent=1)}\n</case>"
    result = client.complete_json(PROMPT.read_text(encoding="utf-8"), user, SCHEMA, "rubric_verdicts")
    haystack = _plain(json.dumps(payload, ensure_ascii=False) + "\n" + "\n".join(
        [payload["answer"], payload["needs"], *(c["claim"] for c in payload["claims"])]))  # fmt: skip
    by_item = {v["item"]: v for v in result.data["verdicts"] if isinstance(v, dict)}
    items = []
    for i, text in enumerate(case.rubric, 1):
        v = by_item.get(i)
        if v is None:
            items.append({"item": text, "met": False, "quote": "", "reason": "no verdict from the judge",
                          "judge_met": None, "quote_found": False})  # fmt: skip
            continue
        quote = v.get("quote", "").strip()
        found = quote_found(quote, haystack)
        items.append({
            "item": text, "met": bool(v["met"]) and found, "quote": quote, "reason": v.get("reason", ""),
            "judge_met": bool(v["met"]), "quote_found": found,
        })  # fmt: skip
    met = sum(1 for x in items if x["met"])
    return {
        "model": result.model, "items": items, "met": met, "of": len(items),
        "passed": met == len(items),
        "tokens": {"input": result.input_tokens, "output": result.output_tokens},
    }  # fmt: skip


def agreement(first: dict[str, Any] | None, second: dict[str, Any] | None) -> tuple[int, int]:
    """(items both judges marked the same, items compared)."""
    if not first or not second:
        return 0, 0
    pairs = list(zip(first["items"], second["items"], strict=True))
    return sum(1 for a, b in pairs if a["met"] == b["met"]), len(pairs)
