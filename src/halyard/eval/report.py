"""docs/eval-report.md from a saved eval (outputs/eval/E-....json), so it can be rewritten
from the saved results without running anything again."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from halyard.eval.grade import ID_THRESHOLD
from halyard.settings import PROJECT_ROOT

REPORT = PROJECT_ROOT / "docs" / "eval-report.md"
# Notes written by hand for one saved eval (what was fixed and re-run after it), included when
# that eval's report is rendered. Front matter `eval: E-...` names the eval they belong to.
NOTES = PROJECT_ROOT / "eval" / "report_notes.md"

METHOD = f"""\
Each question is run through its agent and graded on every layer that applies to it:

- **Figures**: the oracle's key figures (picked in `eval/*.yaml`, values from
  `eval/expected/`) must each appear in the answer, as numbers at the answer's precision.
- **IDs**: the mentions behind the answer's citations (every mention a cited `R-...` result
  counted, plus mention IDs cited directly) against the oracle's mention IDs. The cited set
  compared is the cited result, or the union, that best matches. Precision and recall must
  both be at least {ID_THRESHOLD}.
- **Rubric**: a judge model marks each rubric item met or not, quoting the answer; a "met"
  counts only when the quote is found in the answer. Every item must be met.
- **Citation check**: the run must end `answered`, i.e. pass the agents' own citation check.

A run passes when every layer that applies passes. The answer's `answerable` (`yes` /
`partly` / `no`) is shown against the expected value but not graded: the brief asks that a
question the data cannot answer is declined with the reason, and the rubric items check that.
The expected answers come from the independent oracle (`oracle/`), which shares only
`docs/definitions.md` with the pipeline.

**Limits of the grading.**
- Figures are matched by value, not by position: a figure counts as found if the same number
  appears anywhere in the answer, so two figures with the same value cannot be told apart.
- The judge is `gpt-6-luna`, the same model as the agents, and still reads some items too
  literally. A "met" verdict must quote the answer, so the judge cannot pass an item on a
  passage that is not there; the errors seen so far run the other way, items marked not met
  that a reader would accept. Every verdict is listed with its quote or reason below.
- Three runs per question show how stable an answer is, not a rate to rely on."""


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:.4f}"


def _rubric_cost(g: dict[str, Any]) -> float:
    return sum((r or {}).get("cost_usd") or 0.0 for r in (g.get("rubric"), g.get("second_rubric")))


def _cell(grades: list[dict[str, Any]], key: str) -> str:
    parts = []
    for g in grades:
        layer = g.get(key)
        if layer is None:
            return "–"
        if key == "figures":
            parts.append(f"{len(layer['found'])}/{len(layer['found']) + len(layer['missing'])}")
        elif key == "ids":
            parts.append(f"{layer['precision']:.2f}/{layer['recall']:.2f}")
        elif layer.get("skipped"):
            return "not judged"
        else:
            parts.append(f"{layer['met']}/{layer['of']}")
    return " · ".join(parts)


def report_notes(eval_id: str, path: Path = NOTES) -> str | None:
    """The hand-written notes for `eval_id`, or None when the notes belong to another eval."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not m or yaml.safe_load(m[1]).get("eval") != eval_id:
        return None
    return text[m.end():].strip()


def render_report(ev: dict[str, Any], notes: str | None = None) -> str:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in ev["grades"]:
        by_case[g["case_id"]].append(g)
    cases = [c for c in ev["cases"] if c["id"] in by_case]
    agent_cost = sum(g["cost_usd"] or 0.0 for g in ev["grades"])
    judge_cost = sum(_rubric_cost(g) for g in ev["grades"])
    passes = sum(1 for g in ev["grades"] if g["passed"])
    full = sum(1 for c in cases if all(g["passed"] for g in by_case[c["id"]]))

    lines = [
        "# Eval report", "",
        f"Eval `{ev['eval_id']}`, started {ev['started_at']}. Agent model `{ev['agent_model']}`, "
        f"judge `{ev['judge_model'] or 'none (rubric not judged)'}`"
        + (f", calibration judge `{ev['second_judge_model']}` on the first repeat" if ev.get("second_judge_model") else "")
        + f". {ev['repeat']} run(s) per question.", "",
        (f"**{full} of {len(cases)} questions passed every run; {passes} of {len(ev['grades'])} runs passed.** "
        f"Cost: agents {_money(agent_cost)}, judges {_money(judge_cost)}."), "",
        ("Failures found here, their causes and fixes are logged in "
        "[failure-log.md](failure-log.md) under \"Found by the eval (P5)\"."), "",
        *([notes, ""] if notes else []),
        "## How it is graded", "", METHOD, "",
        "## Summary", "",
        "Cells list each run in order. IDs are precision/recall.", "",
        "| Question | Set | Passed | Figures | IDs | Rubric | Answerable (expected) | Agent cost |",
        "|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for c in cases:
        gs = by_case[c["id"]]
        got = " · ".join(str(g["answerable"]["got"]) for g in gs)
        lines.append(
            f"| {c['id']} | {c['set']} | {sum(g['passed'] for g in gs)}/{len(gs)} | {_cell(gs, 'figures')} "
            f"| {_cell(gs, 'ids')} | {_cell(gs, 'rubric')} | {got} ({gs[0]['answerable']['expected']}) "
            f"| {_money(sum(g['cost_usd'] or 0.0 for g in gs))} |"
        )

    if ev.get("second_judge_model"):
        lines += ["", *_calibration(ev, cases, by_case)]

    lines += ["", "## Per question"]
    for c in cases:
        lines += ["", f"### {c['id']} ({c['agent']} agent)", "", f"> {c['question']}", ""]
        for i, g in enumerate(by_case[c["id"]], 1):
            lines += _run_detail(i, g)
    return "\n".join(lines).rstrip() + "\n"


def _calibration(ev, cases, by_case) -> list[str]:
    same = total = 0
    rows, splits = [], []
    for c in cases:
        g = by_case[c["id"]][0]
        a, b = g.get("rubric"), g.get("second_rubric")
        if not a or not b or not a.get("items") or not b.get("items"):
            continue
        pairs = list(zip(a["items"], b["items"], strict=True))
        k = sum(1 for x, y in pairs if x["met"] == y["met"])
        same, total = same + k, total + len(pairs)
        rows.append(f"| {c['id']} | {k}/{len(pairs)} |")
        splits += [f"- {c['id']}: \"{x['item']}\": `{ev['judge_model']}` {'met' if x['met'] else 'not met'}, "
                   f"`{ev['second_judge_model']}` {'met' if y['met'] else 'not met'}."
                   for x, y in pairs if x["met"] != y["met"]]  # fmt: skip
    share = f"{100 * same / total:.0f}%" if total else "n/a"
    return [
        "## Judge calibration", "",
        (f"On the first run of each rubric question, `{ev['second_judge_model']}` judged the same answer. "
        f"The two judges agreed on **{same} of {total} items ({share})**."), "",
        "| Question | Items agreed |", "|---|---|", *rows, "",
        *(["Items the judges split on:", "", *splits] if splits else ["The judges split on no item."]),
    ]  # fmt: skip


def _run_detail(i: int, g: dict[str, Any]) -> list[str]:
    a = g["answerable"]
    head = (f"**Run {i}** `{g['run_id']}`: {'pass' if g['passed'] else 'FAIL'}. Status {g['status']}; "
            f"answerable {a['got']} (expected {a['expected']}, not graded); "
            f"agent {_money(g['cost_usd'])}.")  # fmt: skip
    out = [head, ""]
    if f := g.get("figures"):
        miss = ", ".join(f"`{m['path']}` = {m['value']:g}" for m in f["missing"])
        out.append(f"- Figures: {len(f['found'])} of {len(f['found']) + len(f['missing'])} found"
                   + (f"; missing {miss}." if miss else "."))  # fmt: skip
    if ids := g.get("ids"):
        out.append(f"- IDs: precision {ids['precision']:.2f}, recall {ids['recall']:.2f} "
                   f"({ids['cited']} cited in `{ids['set']}`, {ids['expected']} expected).")  # fmt: skip
    if r := g.get("rubric"):
        if r.get("skipped"):
            out.append("- Rubric: not judged.")
        elif r.get("error"):
            out.append(f"- Rubric: judge failed: {r['error']}")
        else:
            out.append(f"- Rubric ({r['met']}/{r['of']}, `{r.get('model', '')}`):")
            for item in r["items"]:
                mark = "✓" if item["met"] else "✗"
                if item["met"]:
                    out.append(f"  - {mark} {item['item']} \"{item['quote']}\"")
                else:
                    why = "quote not found in the answer" if item.get("judge_met") else item["reason"]
                    out.append(f"  - {mark} {item['item']} ({why})")
    return [*out, ""]
