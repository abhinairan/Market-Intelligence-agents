"""The agent loop: one question, the model choosing tools, an answer with its evidence.

Generic. An agent is an `AgentSpec`: instructions from a skill file and a subset of the
registry's tools. The loop offers those tools plus the answer tool, runs each call through
`run_tool`, sends back a capped result, and stops when the model calls the answer tool or a
limit is reached. Everything a tool returned is kept on the run, so the answer's citations
can be checked against it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from halyard.agents.answer import ANSWER, shape_problems
from halyard.llm import LLMClient, LLMError, Message, ToolCall, ToolSpec, ToolTurn
from halyard.settings import PROJECT_ROOT, ClientConfig
from halyard.tools.base import ToolError
from halyard.tools.context import ToolContext
from halyard.tools.registry import TOOLS, run_tool

RUNS_DIR = PROJECT_ROOT / "outputs" / "runs"
RUN_PREFIX = "A-"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    instructions: str  # the skill text, sent as the system prompt
    tools: tuple[str, ...]  # names in the registry
    answer: ToolSpec = ANSWER


@dataclass(frozen=True)
class Limits:
    """Per-question limits, from `agent:` in the client's config."""

    max_turns: int  # model calls, the final answer included
    max_total_tokens: int  # input plus output over the run; checked between turns
    max_output_tokens: int  # per model call
    max_ids_sent: int  # mention IDs of a result sent to the model; the rest stay in the log
    answer_retries: int  # times a rejected answer may be corrected

    @classmethod
    def from_client(cls, client: ClientConfig) -> Limits:
        return cls(**client.raw["agent"])


@dataclass
class Step:
    turn: int
    tool: str
    args: dict[str, Any]
    result_id: str | None = None
    error: str | None = None


@dataclass
class AgentRun:
    run_id: str
    agent: str
    question: str
    status: str = "running"  # answered, failed_check, error
    stopped_by: str | None = None  # turn_cap or token_cap, when a limit forced the answer
    answer: dict[str, Any] | None = None
    problems: list[str] = field(default_factory=list)  # why the answer failed its check
    error: str | None = None
    model: str | None = None
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    steps: list[Step] = field(default_factory=list)
    # Every result the tools returned, whole and uncapped, by result ID.
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    messages: list[Message] = field(default_factory=list)  # as sent to the model (capped)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Given an answer and the run so far, the problems with it. Empty means accepted.
AnswerCheck = Callable[[dict[str, Any], AgentRun], list[str]]


def run_agent(
    client: LLMClient,
    ctx: ToolContext,
    spec: AgentSpec,
    question: str,
    limits: Limits,
    check: AnswerCheck | None = None,
) -> AgentRun:
    run = AgentRun(RUN_PREFIX + uuid.uuid4().hex[:8], spec.name, question)
    registry = [TOOLS[name] for name in spec.tools]
    offered = [*(ToolSpec(t.name, t.description, t.parameters) for t in registry), spec.answer]
    messages = run.messages
    messages.append(Message("user", question))
    rejected = 0

    while run.status == "running":
        final = run.stopped_by is not None  # a limit was reached: only the answer is offered
        try:
            turn = client.run_with_tools(
                spec.instructions,
                messages,
                [spec.answer] if final else offered,
                limits.max_output_tokens,
                require_tool=True,
                run_id=run.run_id,
            )
        except LLMError as exc:
            run.status, run.error = "error", str(exc)
            break
        _count(run, turn)
        messages.append(turn.message)

        answers = [c for c in turn.tool_calls if c.name == spec.answer.name]
        if answers and len(turn.tool_calls) == 1:
            answer = answers[0].arguments
            problems = shape_problems(answer, spec.answer) or (check(answer, run) if check else [])
            if not problems:
                run.status, run.answer = "answered", answer
            elif final or rejected >= limits.answer_retries:
                run.status, run.answer, run.problems = "failed_check", answer, problems
            else:
                rejected += 1
                text = "Not accepted. Fix these and call `answer` again:\n- " + "\n- ".join(problems)
                messages.append(Message("tool", text, tool_call_id=answers[0].id))
        else:
            for call in turn.tool_calls:
                if call.name == spec.answer.name:
                    text = "Not accepted: call `answer` on its own, after the tool results."
                else:
                    text = _call_tool(ctx, call, run, limits)
                messages.append(Message("tool", text, tool_call_id=call.id))

        if run.status == "running" and not final:
            if run.turns >= limits.max_turns - 1:
                run.stopped_by = "turn_cap"
            elif run.total_tokens >= limits.max_total_tokens:
                run.stopped_by = "token_cap"
            if run.stopped_by:
                messages.append(Message("user", LIMIT_REACHED))
    return run


LIMIT_REACHED = (
    "The limit for this question has been reached and no more tools can be called. Call "
    "`answer` now with what the results so far support. If they do not answer the question, "
    "set `answerable` to `partly` or `no` and say in `needs` what is missing."
)


def _count(run: AgentRun, turn: ToolTurn) -> None:
    run.model = turn.model
    run.turns += 1
    run.input_tokens += turn.input_tokens
    run.output_tokens += turn.output_tokens
    run.cached_input_tokens += turn.cached_input_tokens


def _call_tool(ctx: ToolContext, call: ToolCall, run: AgentRun, limits: Limits) -> str:
    """Run one tool call and return what the model is sent: the capped result, or the error
    for it to correct."""
    step = Step(run.turns, call.name, call.arguments)
    run.steps.append(step)
    try:
        result = run_tool(ctx, call.name, call.arguments)
    except ToolError as exc:
        step.error = str(exc)
        return json.dumps({"error": step.error})
    step.result_id = result["result_id"]
    run.results[step.result_id] = {"tool": call.name} | result
    return json.dumps(cap_result(result, limits.max_ids_sent), ensure_ascii=False)


def cap_result(result: dict[str, Any], max_ids: int) -> dict[str, Any]:
    """The result as sent to the model: at most `max_ids` mention IDs. The figures are
    untouched and the full list stays in the tool-call log under the result ID."""
    ids = result["mention_ids"]
    if len(ids) <= max_ids:
        return result
    note = (
        f"{max_ids} of {len(ids)} mention IDs shown. Cite the result_id for the full set; "
        "get_mentions(result_id=...) reads the mentions behind it."
    )
    return result | {"mention_ids": ids[:max_ids], "mention_ids_note": note}


def save_run(run: AgentRun, runs_dir: Path = RUNS_DIR) -> Path:
    """Write the run's transcript: question, every step, the messages and the answer."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run.run_id}.json"
    path.write_text(json.dumps(run.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
