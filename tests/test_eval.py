"""The eval runner, graders and judge with scripted models: no API calls (P5 step 3)."""

import json

import pytest

from halyard.agents.citations import citation_check
from halyard.agents.loop import AgentRun, AgentSpec, Limits, run_agent
from halyard.eval.cases import Case, Figure, load_cases, mention_ids_in, resolve
from halyard.eval.grade import Grade, figure_found, grade_ids, matches, numbers_in
from halyard.eval.judge import judge
from halyard.eval.report import render_report
from halyard.eval.runner import run_eval, save_eval
from halyard.ingest.graph import build_graph
from halyard.ingest.pipeline import prepare
from halyard.llm import JsonResult, LLMClient, ToolCall, ToolTurn
from halyard.settings import HalyardError, Settings, load_client
from halyard.store.graph_store import MemoryStore
from halyard.tools.context import ToolContext

LIMITS = Limits(max_turns=4, max_total_tokens=10_000, max_output_tokens=500, max_ids_sent=5, answer_retries=1)
SPEC = AgentSpec("consumer", "Answer from the tools.", ("count_mentions",))


# ---------- cases ----------

def test_every_case_loads_with_its_figures_and_expectations():
    cases = load_cases()
    assert len(cases) == 23 and len({c.id for c in cases}) == 23
    q1 = next(c for c in cases if c.id == "Q1")
    assert [f.value for f in q1.figures][:2] == [987, 984] and len(q1.expected_ids) == 987
    for c in cases:
        assert c.answerable in ("yes", "partly", "no")
        assert c.figures or c.rubric, f"{c.id} would be graded on nothing but `answerable`"


def test_only_names_unknown_questions():
    assert [c.id for c in load_cases(["Q3", "A-login"])] == ["Q3", "A-login"]
    with pytest.raises(HalyardError, match="Q99"):
        load_cases(["Q99"])


def test_paths_and_ids():
    data = {"answer": [{"n": 3}], "mention_ids": {"a": ["M1", "M2"], "b": {"w": ["M2", "x"]}}}
    assert resolve(data, "answer.0.n") == 3
    with pytest.raises(HalyardError, match="answer.1.n"):
        resolve(data, "answer.1.n")
    assert mention_ids_in(data["mention_ids"]) == {"M1", "M2"}


# ---------- figures ----------

def test_numbers_as_written_in_prose():
    text = ("987 conversations from 984 authors; net −.27 then -0.27; 1,904 rows; week of "
            "2026-08-17; shipping Rs 499-799; 63.3% negative; two complaints; M10963 and R-c9ce8b67.")
    values = [n.value for n in numbers_in(text)]
    assert {987, 984, -0.27, 1904, 2026, 8, 17, 499, 799, 63.3, 2}.issubset(values)
    assert -799 not in values and -8 not in values and 10963 not in values


@pytest.mark.parametrize("value,written,ok", [
    (0.818, "0.82", True), (0.818, "0.8", False), (63.3, "63%", True), (63.3, "63.3", True),
    (-0.27, "-.27", True), (-0.27, "0", False), (4.6, "5%", True), (987, "987", True),
    (987, "986", False), (0.33, "0.3", True),
])  # fmt: skip
def test_figure_matches_at_the_answer_precision(value, written, ok):
    assert any(matches(value, n) for n in numbers_in(written)) is ok


def test_ratio_may_be_written_as_a_percentage():
    assert figure_found(Figure("r", 0.818, percent=True), numbers_in("about 82% of the price"))
    assert not figure_found(Figure("r", 0.818), numbers_in("about 82% of the price"))


# ---------- IDs ----------

def _case(**kw):
    base = {"id": "T", "set": "golden", "agent": "consumer", "question": "?", "expected": {"answerable": "yes"}}
    return Case(**(base | kw))


def test_ids_compared_with_the_best_matching_cited_set():
    case = _case(expected_ids=frozenset({"M1", "M2", "M3"}))
    results = {"R-line": {"mention_ids": ["M1", "M2", "M3"]},
               "R-brand": {"mention_ids": [f"M{i}" for i in range(1, 101)]}}  # fmt: skip
    answer = {"claims": [{"claim": "brand", "cites": ["R-brand"]},
                         {"claim": "line", "cites": ["R-line", "M2"]}]}  # fmt: skip
    ids = grade_ids(case, answer, results)
    assert (ids["set"], ids["precision"], ids["recall"], ids["passed"]) == ("R-line", 1.0, 1.0, True)

    only_brand = grade_ids(case, {"claims": [{"claim": "brand", "cites": ["R-brand"]}]}, results)
    assert only_brand["recall"] == 1.0 and only_brand["precision"] == 0.03 and not only_brand["passed"]
    assert grade_ids(case, {"claims": []}, results)["passed"] is False

    # A part of a cited result's breakdown counts as a cited set of its own.
    results["R-brand"]["mention_id_groups"] = {"TST/Nitro": ["M1", "M2", "M3"], "TST": ["M1", "M9"]}
    part = grade_ids(case, {"claims": [{"claim": "brand", "cites": ["R-brand"]}]}, results)
    assert (part["set"], part["precision"], part["passed"]) == ("R-brand#TST/Nitro", 1.0, True)


# ---------- judge ----------

class ScriptedJudge(LLMClient):
    provider = "fake"

    def __init__(self, verdicts, **kw):
        super().__init__("fake-judge", "judge", usage_log=None, **kw)
        self.verdicts, self.users = verdicts, []

    def _complete_json(self, system, user, schema, name, max_tokens):
        self.users.append(user)
        return JsonResult({"verdicts": self.verdicts}, self.provider, self.model, 50, 10)


def test_judge_counts_a_met_item_only_when_its_quote_is_in_the_answer():
    case = _case(expected={"answerable": "no", "rubric": ["Declines.", "Names the FAQ.", "Offers a route."]})
    answer = {"answer": "We cannot say.\nThe  FAQ says subscriptions are on Classic.", "claims": [], "answerable": "no"}
    model = ScriptedJudge([
        {"item": 1, "met": True, "quote": "We cannot say.", "reason": "declines"},
        {"item": 2, "met": True, "quote": "the faq says subscriptions are on classic", "reason": "names it"},
        {"item": 3, "met": True, "quote": "Ask the client for records.", "reason": "made up"},
    ])  # fmt: skip
    r = judge(model, case, answer)
    assert [x["met"] for x in r["items"]] == [True, True, False]
    assert r["items"][2]["judge_met"] and not r["items"][2]["quote_found"]
    assert (r["met"], r["of"], r["passed"]) == (2, 3, False)
    assert "<case>" in model.users[0] and "Offers a route." in model.users[0]

    stitched = judge(ScriptedJudge([
        {"item": 1, "met": True, "quote": "We **cannot** say … subscriptions are on Classic.", "reason": ""},
        {"item": 2, "met": True, "quote": "We cannot say subscriptions are on Classic.", "reason": "joined"},
    ]), case, answer)  # fmt: skip
    assert [x["met"] for x in stitched["items"]] == [True, False, False]

    missing = judge(ScriptedJudge([]), case, answer)
    assert missing["met"] == 0 and missing["items"][0]["reason"] == "no verdict from the judge"


def test_pass_rule():
    ok = {"passed": True}
    g = Grade("T", "A-1", "answered", {"passed": True}, figures=ok, rubric={"skipped": True, "passed": None})
    assert g.passed
    assert Grade("T", "A-1", "answered", {"passed": False}, figures=ok).passed  # reported, not graded
    assert not Grade("T", "A-1", "failed_check", {"passed": True}, figures=ok).passed
    assert not Grade("T", "A-1", "answered", {"passed": True}, figures={"passed": False}).passed


# ---------- end to end ----------

@pytest.fixture(scope="module")
def ctx():
    client = load_client("brewbird")
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client)
    return ToolContext(MemoryStore(build_graph(prepare(settings), client)), client)


class Answering(LLMClient):
    """Counts Brewbird conversations, then answers Q1 citing that result."""

    provider = "fake"

    def __init__(self, text):
        super().__init__("fake-model", "agent", usage_log=None)
        self.text = text

    def _complete_json(self, *a):
        raise NotImplementedError

    def _run_with_tools(self, system, messages, tools, max_tokens, require_tool):
        if messages[-1].role == "user":
            call = ToolCall("c1", "count_mentions", {"brand": "Brewbird"})
        else:
            rid = json.loads(messages[-1].text)["result_id"]
            claims = [{"claim": "987 conversations", "cites": [rid]}]
            call = ToolCall("c2", "answer", {"answer": self.text, "claims": claims, "answerable": "yes"})
        return ToolTurn("", (call,), self.provider, self.model, 100, 10)


def test_eval_end_to_end_with_report(ctx, tmp_path):
    (q1,) = load_cases(["Q1"])
    full = "987 conversations from 984 authors: Classic 246, Nitro 211, Origins 203, Drip 175, brand-level 152."

    def ask_with(text):
        return lambda agent, q: run_agent(Answering(text), ctx, SPEC, q, LIMITS, citation_check(ctx))

    ev = run_eval([q1], ask_with(full), ScriptedJudge([]), repeat=2)
    assert [g.passed for g in ev.grades] == [True, True]
    g = ev.grades[0]
    assert g.figures["missing"] == [] and g.ids["precision"] == 1.0 and g.ids["recall"] == 1.0
    assert g.rubric is None  # Q1 has no rubric: the judge is not called

    short = run_eval([q1], ask_with("987 conversations, 211 on Nitro."), None, repeat=1)
    assert not short.grades[0].passed
    assert {m["value"] for m in short.grades[0].figures["missing"]} == {984, 246, 203, 175, 152}

    report = render_report(json.loads(save_eval(short, tmp_path).read_text()))
    assert "| Q1 | golden | 0/1 | 2/7 | 1.00/1.00 |" in report
    assert "`answer.authors` = 984" in report


def test_an_errored_run_is_reported_not_graded_as_passed():
    run = AgentRun("A-x", "consumer", "?", status="error", error="boom")
    ev = run_eval([_case(figures=(Figure("f", 1.0),))], lambda a, q: run, None, repeat=1)
    assert ev.errors and not ev.grades[0].passed
