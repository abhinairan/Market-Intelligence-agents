"""Run the eval: every case `repeat` times through its agent, each run graded on every layer.

The agent and the judge are passed in, so tests run the whole eval with scripted models.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from halyard.agents.loop import AgentRun
from halyard.eval.cases import Case
from halyard.eval.grade import Grade, grade_answerable, grade_figures, grade_ids
from halyard.eval.judge import judge
from halyard.llm import LLMClient, LLMError
from halyard.llm.spend import cost_usd, load_prices
from halyard.settings import PROJECT_ROOT

EVAL_OUT = PROJECT_ROOT / "outputs" / "eval"
EVAL_PREFIX = "E-"

Ask = Callable[[str, str], AgentRun]  # (agent, question) -> a finished, saved run


@dataclass
class EvalRun:
    eval_id: str
    started_at: str
    repeat: int
    agent_model: str | None = None
    judge_model: str | None = None
    second_judge_model: str | None = None
    grades: list[Grade] = field(default_factory=list)
    cases: list[dict[str, Any]] = field(default_factory=list)  # id, set, agent, question

    @property
    def errors(self) -> list[Grade]:
        return [g for g in self.grades if g.status == "error"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_id": self.eval_id, "started_at": self.started_at, "repeat": self.repeat,
            "agent_model": self.agent_model, "judge_model": self.judge_model,
            "second_judge_model": self.second_judge_model, "cases": self.cases,
            "grades": [g.to_dict() for g in self.grades],
        }  # fmt: skip


def grade_run(
    case: Case,
    run: AgentRun,
    judge_client: LLMClient | None,
    second_judge: LLMClient | None = None,
) -> Grade:
    prices = load_prices()
    answer = run.answer
    grade = Grade(
        case.id, run.run_id, run.status, grade_answerable(case, answer),
        figures=grade_figures(case, answer), ids=grade_ids(case, answer, run.results),
        cost_usd=cost_usd(run.model or "", run.input_tokens, run.output_tokens, prices,
                          run.cached_input_tokens),
        tokens={"input": run.input_tokens, "output": run.output_tokens, "cached": run.cached_input_tokens},
    )  # fmt: skip
    if case.rubric and answer is not None:
        if judge_client is None:
            grade.rubric = {"skipped": True, "passed": None, "items": [], "met": 0, "of": len(case.rubric)}
        else:
            grade.rubric = _judged(judge_client, case, answer, prices)
            if second_judge is not None:
                grade.second_rubric = _judged(second_judge, case, answer, prices)
    elif case.rubric:
        grade.rubric = {"items": [], "met": 0, "of": len(case.rubric), "passed": False}
    return grade


def _judged(client: LLMClient, case: Case, answer: dict[str, Any], prices) -> dict[str, Any]:
    try:
        verdict = judge(client, case, answer)
    except LLMError as exc:
        return {"error": str(exc), "items": [], "met": 0, "of": len(case.rubric), "passed": False}
    verdict["cost_usd"] = cost_usd(verdict["model"], verdict["tokens"]["input"], verdict["tokens"]["output"], prices)
    return verdict


def run_eval(
    cases: list[Case],
    ask: Ask,
    judge_client: LLMClient | None,
    repeat: int = 3,
    second_judge: LLMClient | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> EvalRun:
    """Each case `repeat` times. The second judge, when given, grades the first repeat only:
    it calibrates the judge rather than doubling the grading."""
    ev = EvalRun(
        EVAL_PREFIX + uuid.uuid4().hex[:8], datetime.now(UTC).isoformat(timespec="seconds"), repeat,
        judge_model=judge_client.model if judge_client else None,
        second_judge_model=second_judge.model if second_judge else None,
        cases=[{"id": c.id, "set": c.set, "agent": c.agent, "question": c.question} for c in cases],
    )  # fmt: skip
    for case in cases:
        for i in range(repeat):
            run = ask(case.agent, case.question)
            ev.agent_model = ev.agent_model or run.model
            grade = grade_run(case, run, judge_client, second_judge if i == 0 else None)
            ev.grades.append(grade)
            progress(f"{case.id} run {i + 1}/{repeat}: {'pass' if grade.passed else 'FAIL'} ({run.run_id})")
    return ev


def save_eval(ev: EvalRun, out_dir: Path = EVAL_OUT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ev.eval_id}.json"
    path.write_text(json.dumps(ev.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
