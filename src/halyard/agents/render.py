"""An agent run as text for the terminal: the answer, what each claim rests on, the cost."""

from __future__ import annotations

from halyard.agents.loop import AgentRun
from halyard.llm.spend import cost_usd, load_prices

NOTICE = {
    "partly": "[Partly answerable: the data answers some of this question; the rest is declined.]",
    "no": "[The data cannot answer this question as asked.]",
}
STOPPED = {"turn_cap": "the turn limit", "token_cap": "the token limit"}


def render_run(run: AgentRun) -> str:
    if run.answer is None:
        return f"No answer: {run.error}"
    answer = run.answer
    lines = []
    if run.status == "failed_check":
        lines += ["NOT VERIFIED: this answer failed the citation check.",
                  *(f"  - {p}" for p in run.problems), ""]  # fmt: skip
    if answer.get("answerable") in NOTICE:
        lines += [NOTICE[answer["answerable"]], ""]
    lines += [answer["answer"].strip(), ""]
    if answer.get("needs", "").strip():
        lines += [f"Would need: {answer['needs'].strip()}", ""]
    lines.append("Evidence")
    for i, claim in enumerate(answer.get("claims", []), 1):
        lines.append(f"  {i}. {claim['claim']} [{', '.join(claim['cites'])}]")
    lines += ["", _footer(run)]
    return "\n".join(lines)


def _footer(run: AgentRun) -> str:
    cost = cost_usd(
        run.model or "", run.input_tokens, run.output_tokens, load_prices(), run.cached_input_tokens
    )
    parts = [
        f"Run {run.run_id}",
        f"{run.agent} agent on {run.model}",
        f"{len(run.steps)} tool calls in {run.turns} turns",
        f"{run.input_tokens:,} tokens in, {run.output_tokens:,} out",
        "no price set" if cost is None else f"${cost:.4f}",
    ]
    if run.stopped_by:
        parts.append(f"stopped by {STOPPED[run.stopped_by]}")
    return " | ".join(parts)
