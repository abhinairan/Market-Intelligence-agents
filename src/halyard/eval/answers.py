"""docs/eval-answers.md: for each eval question, the expected answer and the agent's answer.

The brief asks for both side by side with the verdict. The expected side comes from the
oracle's files (via the eval cases); the agent's side is read from the saved run transcripts
(outputs/runs/), so this is rendered from saved evals without running anything again.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from halyard.agents.loop import RUNS_DIR
from halyard.eval.cases import Case
from halyard.settings import PROJECT_ROOT, HalyardError

ANSWERS = PROJECT_ROOT / "docs" / "eval-answers.md"


def load_saved_run(run_id: str, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    path = runs_dir / f"{run_id}.json"
    if not path.exists():
        raise HalyardError(f"No saved run {run_id} in {runs_dir}: the transcripts are needed.")
    return json.loads(path.read_text(encoding="utf-8"))


def latest_grades(evals: list[dict[str, Any]]) -> dict[str, tuple[str, list[dict[str, Any]]]]:
    """Each question's grades from the last of `evals` that ran it, with that eval's ID."""
    chosen: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for ev in evals:
        by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for g in ev["grades"]:
            by_case[g["case_id"]].append(g)
        for case_id, grades in by_case.items():
            chosen[case_id] = (ev["eval_id"], grades)
    return chosen


def _figure_label(path: str) -> str:
    return path.removeprefix("answer.")


def _expected(case: Case) -> list[str]:
    out = [f"- Answerable: **{case.answerable}**"]
    if case.figures:
        figs = "; ".join(f"`{_figure_label(f.path)}` {f.value:g}" for f in case.figures)
        out.append(f"- Key figures: {figs}")
    if case.expected_ids:
        out.append(f"- Mentions behind the answer: {len(case.expected_ids)}")
    if case.rubric:
        out.append("- The answer must:")
        out += [f"  - {item}" for item in case.rubric]
    return out


def _quoted(text: str) -> list[str]:
    return [f"> {line}" if line.strip() else ">" for line in text.strip().splitlines()]


def _agent(run: dict[str, Any]) -> list[str]:
    answer = run.get("answer")
    if not answer:
        return [f"No answer: {run.get('error') or run.get('status')}."]
    out = [f"Answerable: **{answer.get('answerable', 'n/a')}**", "", *_quoted(answer["answer"])]
    if answer.get("needs", "").strip():
        out += [">", *_quoted(f"*Would need:* {answer['needs'].strip()}")]
    claims = answer.get("claims", [])
    if claims:
        out += ["", "<details><summary>Claims and what each cites</summary>", ""]
        out += [f"{i}. {c['claim']} [{', '.join(c['cites'])}]" for i, c in enumerate(claims, 1)]
        out += ["", "</details>"]
    return out


def render_answers(
    evals: list[dict[str, Any]],
    cases: list[Case],
    load_run: Callable[[str], dict[str, Any]] = load_saved_run,
) -> str:
    chosen = latest_grades(evals)
    ids = ", ".join(f"`{ev['eval_id']}`" for ev in evals)
    lines = [
        "# Eval answers", "",
        ("For each question: the expected answer, computed by the independent oracle (`oracle/`, "
         "pandas over the raw CSVs), the agent's actual answer, and whether it passed. How each "
         "layer is graded, every run's verdict and the recorded result are in "
         "[eval-report.md](eval-report.md)."), "",
        (f"Answers are taken from the saved evals {ids}; where a question was run in more than "
         "one, the latest is used. One run is shown per question: the first that passed, or the "
         "first run when none did. Pass counts are as graded in that eval; the recorded result in "
         "the eval report can differ where a run was re-judged."), "",
        "| Question | Set | Passed | Eval |", "|---|---|---|---|",
    ]  # fmt: skip
    shown = [c for c in cases if c.id in chosen]
    for c in shown:
        eval_id, grades = chosen[c.id]
        lines.append(f"| [{c.id}](#{c.id.lower()}) | {c.set} | {sum(g['passed'] for g in grades)}/{len(grades)} | `{eval_id}` |")
    for c in shown:
        eval_id, grades = chosen[c.id]
        pick = next((g for g in grades if g["passed"]), grades[0])
        passed = sum(g["passed"] for g in grades)
        lines += [
            "", f"## {c.id}", "", f"**{c.question}** ({c.agent} agent)", "",
            "**Expected (oracle)**", "", *_expected(c), "",
            f"**Agent's answer** (run `{pick['run_id']}`, {'passed' if pick['passed'] else 'failed'})", "",
            *_agent(load_run(pick["run_id"])), "",
            f"**Result:** passed {passed} of {len(grades)} runs in `{eval_id}`.",
        ]  # fmt: skip
    missing = [c.id for c in cases if c.id not in chosen]
    if missing:
        lines += ["", f"Not run in these evals: {', '.join(missing)}."]
    return "\n".join(lines).rstrip() + "\n"
