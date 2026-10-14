"""The citation check: an answer may cite only what a tool returned in the same run.

This is the grounding rule enforced in code rather than asked for in a prompt. A cited ID
that no tool returned, a claim with nothing cited, or a mention ID in the answer text that
no tool returned, each reject the answer.
"""

from __future__ import annotations

import re
from typing import Any

from halyard.agents.loop import AgentRun, AnswerCheck
from halyard.tools.context import ToolContext
from halyard.tools.log import RESULT_PREFIX

WORD = re.compile(r"[\w-]+")


def returned_ids(run: AgentRun) -> set[str]:
    """Everything citable from this run: result IDs, the mention IDs and source refs of
    every result, and any ID that appears as a value in a result's data (examples, ads)."""
    known: set[str] = set(run.results)
    for result in run.results.values():
        known.update(result["mention_ids"])
        known.update(result["source_refs"])
        known.update(_strings(result["data"]))
    return known


def _strings(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_strings(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_strings(v) for v in value))
    return {value} if isinstance(value, str) else set()


def _shape(token: str) -> str:
    return re.sub(r"\d", "0", token)


def citation_check(ctx: ToolContext) -> AnswerCheck:
    """A check for `run_agent`. It reads the graph once, to know what a mention ID looks
    like, so an ID written in the answer's prose is checked like a cited one."""
    id_shapes = {_shape(m.mention_id) for m in ctx.mentions}

    def check(answer: dict[str, Any], run: AgentRun) -> list[str]:
        known = returned_ids(run)
        problems = []
        if not answer["claims"]:
            problems.append("`claims` is empty. List every figure or fact with what it cites.")
        for i, claim in enumerate(answer["claims"], 1):
            if not claim["cites"]:
                problems.append(f"Claim {i} cites nothing. Cite a result ID, or remove it.")
            for cite in claim["cites"]:
                if cite not in known:
                    problems.append(f"Claim {i} cites {cite}, which no tool returned in this run.")
        cited = {c for claim in answer["claims"] for c in claim["cites"]}
        for token in dict.fromkeys(WORD.findall(answer["answer"])):
            is_id = token.startswith(RESULT_PREFIX) or _shape(token) in id_shapes
            if is_id and token not in known:
                problems.append(f"The answer mentions {token}, which no tool returned in this run.")
            elif is_id and token not in cited:
                problems.append(f"The answer mentions {token} but no claim cites it.")
        return problems

    return check
