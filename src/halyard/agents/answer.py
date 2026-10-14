"""The structured final answer every agent gives, as a tool the model calls to finish."""

from __future__ import annotations

from typing import Any

from halyard.llm import ToolSpec

ANSWERABLE = ("yes", "partly", "no")

ANSWER = ToolSpec(
    "answer",
    "Give the final answer. Call it once, on its own, after the tool results you need.",
    {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The answer for the reader, in plain prose.",
            },
            "claims": {
                "type": "array",
                "description": "Every figure or fact the answer states, each with what it "
                "rests on.",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "cites": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Result IDs (`R-...`) for counted figures; mention "
                            "IDs or `file:row` refs for single items. Only IDs a tool "
                            "returned in this conversation.",
                        },
                    },
                    "required": ["claim", "cites"],
                    "additionalProperties": False,
                },
            },
            "answerable": {
                "type": "string",
                "enum": list(ANSWERABLE),
                "description": "`yes` when the data answers the question; `partly` when it "
                "answers some of it and the rest is declined; `no` when it cannot answer the "
                "main thing asked.",
            },
            "needs": {
                "type": "string",
                "description": "The data that would answer what could not be answered, "
                "the whole question or a part of it. Empty when nothing is missing.",
            },
        },
        "required": ["answer", "claims", "answerable"],
        "additionalProperties": False,
    },
)


def shape_problems(answer: dict[str, Any], spec: ToolSpec = ANSWER) -> list[str]:
    """What is missing or mistyped in an answer, in words the model can act on. The tool is
    not sent as strict, so the shape is checked here."""
    problems = [f"`{k}` is missing." for k in spec.parameters["required"] if k not in answer]
    if not isinstance(answer.get("answer", ""), str) or not str(answer.get("answer", "x")).strip():
        problems.append("`answer` must be non-empty text.")
    if "answerable" in answer and answer["answerable"] not in ANSWERABLE:
        problems.append(f"`answerable` must be one of {', '.join(ANSWERABLE)}.")
    elif answer.get("answerable") in ("partly", "no") and not str(answer.get("needs", "")).strip():
        problems.append("`needs` must name the missing data when `answerable` is not `yes`.")
    claims = answer.get("claims", [])
    if not isinstance(claims, list):
        return [*problems, "`claims` must be a list."]
    for i, claim in enumerate(claims, 1):
        cites = claim.get("cites") if isinstance(claim, dict) else None
        if not isinstance(claim, dict) or not isinstance(claim.get("claim"), str):
            problems.append(f"Claim {i} needs a `claim` text and a `cites` list.")
        elif not isinstance(cites, list) or not all(isinstance(c, str) for c in cites):
            problems.append(f"Claim {i}: `cites` must be a list of ID strings.")
    return problems
