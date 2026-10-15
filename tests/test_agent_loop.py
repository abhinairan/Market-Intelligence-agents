"""The agent loop with a scripted model: no API calls (P4 step 2)."""

import json

import pytest

from halyard.agents.loop import AgentSpec, Limits, cap_result, run_agent, save_run
from halyard.ingest.graph import build_graph
from halyard.ingest.pipeline import prepare
from halyard.llm import LLMClient, ToolCall, ToolTurn
from halyard.llm.spend import cost_usd, summarise
from halyard.settings import Settings, load_client
from halyard.store.graph_store import MemoryStore
from halyard.tools.context import ToolContext

SPEC = AgentSpec("consumer", "Answer from the tools.", ("count_mentions", "get_mentions"))
LIMITS = Limits(
    max_turns=4, max_total_tokens=10_000, max_output_tokens=500, max_ids_sent=5, answer_retries=1
)
GOOD = {"answer": "Nitro has 211.", "claims": [], "answerable": "yes"}


@pytest.fixture(scope="module")
def client_config():
    return load_client("brewbird")


@pytest.fixture
def ctx(client_config, tmp_path):
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client_config)
    store = MemoryStore(build_graph(prepare(settings), client_config))
    return ToolContext(store, client_config, tool_log=tmp_path / "tool_calls.jsonl")


class Scripted(LLMClient):
    """Plays back turns, each a list of (tool name, arguments). Records what it was offered
    and sent."""

    provider = "fake"

    def __init__(self, turns, tokens=100, **kw):
        super().__init__("fake-model", "agent", **kw)
        self.turns, self.tokens = list(turns), tokens
        self.offered, self.sent = [], []

    def _complete_json(self, system, user, schema, name, max_tokens):
        raise NotImplementedError

    def _run_with_tools(self, system, messages, tools, max_tokens, require_tool):
        self.offered.append([t.name for t in tools])
        self.sent.append(list(messages))
        n = len(self.sent)
        calls = tuple(ToolCall(f"c{n}_{i}", name, args) for i, (name, args) in enumerate(self.turns.pop(0)))
        return ToolTurn("", calls, self.provider, self.model, self.tokens, 10, 0)


def scripted(tmp_path, turns, **kw):
    return Scripted(turns, usage_log=tmp_path / "usage.jsonl", **kw)


def test_question_to_answer_with_evidence_kept(ctx, tmp_path):
    count = ("count_mentions", {"brand": "brewbird", "line": "Nitro"})
    model = scripted(tmp_path, [[count], [("answer", GOOD)]])
    run = run_agent(model, ctx, SPEC, "How many Nitro conversations?", LIMITS)

    assert (run.status, run.stopped_by, run.answer, run.turns) == ("answered", None, GOOD, 2)
    assert model.offered[0] == ["count_mentions", "get_mentions", "answer"]

    # The model is sent 5 IDs; the run and the tool-call log keep all 211.
    sent = json.loads(model.sent[1][-1].text)
    assert sent["data"]["total"] == 211 and len(sent["mention_ids"]) == 5
    assert "5 of 211" in sent["mention_ids_note"]
    (step,) = run.steps
    assert step.result_id == sent["result_id"] and step.error is None
    assert len(run.results[step.result_id]["mention_ids"]) == 211
    logged = json.loads(ctx.tool_log.read_text().splitlines()[-1])
    assert logged["result_id"] == step.result_id and len(logged["result"]["mention_ids"]) == 211

    # Usage is logged under the run ID, and the transcript is written whole.
    assert [r["calls"] for r in summarise(tmp_path / "usage.jsonl", {}, run.run_id)] == [2]
    saved = json.loads(save_run(run, tmp_path / "runs").read_text())
    assert saved["answer"] == GOOD and saved["steps"][0]["tool"] == "count_mentions"
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant", "tool", "assistant"]


def test_tool_error_is_fed_back_not_raised(ctx, tmp_path):
    bad = ("count_mentions", {"brand": "brewbird", "flavour": "mango"})
    model = scripted(tmp_path, [[bad], [("answer", GOOD)]])
    run = run_agent(model, ctx, SPEC, "q", LIMITS)
    assert run.status == "answered" and run.results == {}
    assert "takes no argument" in run.steps[0].error
    assert "takes no argument" in json.loads(model.sent[1][-1].text)["error"]


def test_parallel_calls_each_get_a_result(ctx, tmp_path):
    two = [("count_mentions", {"brand": "brewbird"}), ("get_mentions", {"ids": ["M10149"]})]
    model = scripted(tmp_path, [two, [("answer", GOOD)]])
    run = run_agent(model, ctx, SPEC, "q", LIMITS)
    results = model.sent[1][-2:]
    assert [m.tool_call_id for m in results] == ["c1_0", "c1_1"]
    assert len(run.results) == 2 and run.turns == 2


def test_answer_alongside_other_calls_is_not_accepted(ctx, tmp_path):
    early = [("count_mentions", {"brand": "brewbird"}), ("answer", GOOD)]
    model = scripted(tmp_path, [early, [("answer", GOOD)]])
    run = run_agent(model, ctx, SPEC, "q", LIMITS)
    assert "on its own" in model.sent[1][-1].text
    assert run.status == "answered" and run.turns == 2


def test_turn_cap_forces_an_answer_and_is_recorded(ctx, tmp_path):
    count = [("count_mentions", {"brand": "brewbird"})]
    model = scripted(tmp_path, [count, count, count, [("answer", GOOD)]])
    run = run_agent(model, ctx, SPEC, "q", LIMITS)
    assert (run.status, run.stopped_by, run.turns) == ("answered", "turn_cap", 4)
    assert model.offered[3] == ["answer"]  # the last call can only answer
    assert "limit" in model.sent[3][-1].text.lower()


def test_token_cap_forces_an_answer(ctx, tmp_path):
    count = [("count_mentions", {"brand": "brewbird"})]
    model = scripted(tmp_path, [count, [("answer", GOOD)]], tokens=20_000)
    run = run_agent(model, ctx, SPEC, "q", LIMITS)
    assert (run.status, run.stopped_by, run.turns) == ("answered", "token_cap", 2)
    assert run.total_tokens == 40_020


def test_rejected_answer_gets_one_retry(ctx, tmp_path):
    def check(answer, run):
        return [] if answer["claims"] else ["No claim cites anything."]

    cited = GOOD | {"claims": [{"claim": "211", "cites": ["R-1"]}]}
    fixed = run_agent(scripted(tmp_path, [[("answer", GOOD)], [("answer", cited)]]), ctx, SPEC,
                      "q", LIMITS, check)  # fmt: skip
    assert (fixed.status, fixed.answer, fixed.problems) == ("answered", cited, [])
    assert "No claim cites anything." in fixed.messages[2].text

    stuck = run_agent(scripted(tmp_path, [[("answer", GOOD)], [("answer", GOOD)]]), ctx, SPEC,
                      "q", LIMITS, check)  # fmt: skip
    assert (stuck.status, stuck.problems) == ("failed_check", ["No claim cites anything."])
    assert stuck.answer == GOOD  # kept, marked as failed, never passed off as checked


def test_malformed_answer_is_rejected_before_any_check(ctx, tmp_path):
    model = scripted(tmp_path, [[("answer", {"answer": "211"})], [("answer", GOOD)]])
    run = run_agent(model, ctx, SPEC, "q", LIMITS)
    assert run.status == "answered" and "`claims` is missing." in run.messages[2].text


def test_answerable_must_be_known_and_a_decline_must_say_what_is_missing():
    from halyard.agents.answer import shape_problems

    assert shape_problems(GOOD) == []
    assert shape_problems(GOOD | {"answerable": "maybe"}) == [
        "`answerable` must be one of yes, partly, no."
    ]
    assert shape_problems(GOOD | {"answerable": "partly"}) == [
        "`needs` must name the missing data when `answerable` is not `yes`."
    ]
    assert shape_problems(GOOD | {"answerable": "no", "needs": "Subscription records."}) == []


def test_model_failure_ends_the_run_as_an_error(ctx, tmp_path):
    model = scripted(tmp_path, [[("drop_database", {})]])
    run = run_agent(model, ctx, SPEC, "q", LIMITS)
    assert run.status == "error" and "unknown tools" in run.error and run.answer is None


def test_cap_leaves_short_results_alone():
    short = {"mention_ids": ["M1", "M2"], "data": {"total": 2}}
    assert cap_result(short, 5) == short
    # ID groups stay in the log and the run; the model never gets them.
    assert cap_result(short | {"mention_id_groups": {"TST": ["M1"]}}, 5) == short


def test_limits_come_from_client_config(client_config):
    limits = Limits.from_client(client_config)
    assert limits.max_turns >= 2 and limits.max_ids_sent > 0


def test_spend_prices_known_models_only(tmp_path):
    prices = {"gpt-6-luna": {"input": 0.10, "output": 0.50}}
    assert cost_usd("gpt-6-luna", 1_000_000, 1_000_000, prices) == pytest.approx(0.60)
    assert cost_usd("unpriced", 5, 5, prices) is None
    log = tmp_path / "u.jsonl"
    rows = [
        {"model": "gpt-6-luna", "purpose": "agent", "input_tokens": 2_000_000,
         "output_tokens": 0, "cached_input_tokens": 500, "run_id": "A-1"},
        {"model": "gpt-6-luna", "purpose": "label", "input_tokens": 10, "output_tokens": 10},
    ]  # fmt: skip
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert [r["purpose"] for r in summarise(log, prices)] == ["agent", "label"]
    (one,) = summarise(log, prices, run_id="A-1")
    assert one["cost_usd"] == pytest.approx(0.20) and one["cached_input_tokens"] == 500
