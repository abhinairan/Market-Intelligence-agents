"""Skills, the citation check and the rendered answer (P4 step 3). No API calls."""

import pytest

from halyard.agents.citations import citation_check, returned_ids
from halyard.agents.loop import AgentRun
from halyard.agents.render import render_run
from halyard.agents.skills import (
    SKILLS_DIR,
    load_skill,
    render_tools,
    skill_files,
    tools_path,
)
from halyard.ingest.graph import build_graph
from halyard.ingest.pipeline import prepare
from halyard.settings import HalyardError, Settings, load_client
from halyard.store.graph_store import MemoryStore
from halyard.tools.context import ToolContext
from halyard.tools.registry import TOOLS, run_tool


@pytest.fixture(scope="module")
def ctx():
    client = load_client("brewbird")
    settings = Settings("", "", "", "", "openai", None, "gpt-6-luna", None, client)
    return ToolContext(MemoryStore(build_graph(prepare(settings), client)), client)


@pytest.fixture(scope="module")
def run(ctx):
    """A run that made two tool calls, as the loop would have recorded them."""
    run = AgentRun("A-test", "consumer", "q", model="gpt-6-luna")
    for name, args in (
        ("count_mentions", {"brand": "brewbird", "line": "Nitro"}),
        ("complaint_breakdown", {"brand": "brewbird", "last_weeks": 3, "examples": 2}),
    ):
        result = run_tool(ctx, name, args)
        run.results[result["result_id"]] = {"tool": name} | result
    return run


def _answer(text, *claims):
    return {"answer": text, "answerable": "yes",
            "claims": [{"claim": c, "cites": list(cites)} for c, cites in claims]}  # fmt: skip


@pytest.mark.parametrize(("name", "skill"), skill_files())
def test_every_skill_loads_with_all_slots_filled(ctx, name, skill):
    spec = load_skill(name, ctx, skill)
    assert spec.name.startswith(name) and "{{" not in spec.instructions
    assert set(spec.tools) <= set(TOOLS)
    # Client facts arrive through slots, and the shared rules are included.
    assert "Brewbird Coffee Co." in spec.instructions and "`brewbird`" in spec.instructions
    assert "## Grounding rules" in spec.instructions and "## Output format" in spec.instructions


def test_skill_files_name_no_client(ctx):
    """A new client must need no change to a skill: no brand, line or date in the files."""
    names = [b["name"].split()[0] for b in ctx.names.brands] + [ln["name"] for ln in ctx.names.lines]
    agent_files = [SKILLS_DIR / a / f"{s}.md" for a, s in skill_files()]
    for path in [*agent_files, *SKILLS_DIR.glob("shared/*.md")]:
        text = path.read_text()
        assert not [n for n in names if n in text], path
        assert "2026" not in text and "2025" not in text, path


@pytest.mark.parametrize(("name", "skill"), skill_files())
def test_tools_json_matches_the_registry(name, skill):
    """Each skill's tools file is generated. Run `halyard skills` if this fails."""
    assert tools_path(name, skill).read_text(encoding="utf-8") == render_tools(name, skill)


def test_unknown_agent_is_a_clear_error(ctx):
    with pytest.raises(HalyardError, match="no agent 'pricing'"):
        load_skill("pricing", ctx)


def test_citations_from_the_run_are_accepted(ctx, run):
    count_id, codes_id = run.results
    example = run.results[codes_id]["data"]["codes"][0]["examples"][0]["mention_id"]
    ref = run.results[codes_id]["source_refs"][0]
    assert {count_id, example, ref} <= returned_ids(run)
    answer = _answer(
        f"Nitro has 211 conversations. Taste leads, e.g. ({example}).",
        ("211 Nitro conversations", [count_id]),
        ("Taste is the top code", [codes_id, example, ref]),
    )
    assert citation_check(ctx)(answer, run) == []


def test_invented_and_uncited_ids_are_rejected(ctx, run):
    count_id, codes_id = run.results
    check = citation_check(ctx)
    real_but_not_returned = next(
        m.mention_id for m in ctx.mentions if m.mention_id not in returned_ids(run)
    )
    cases = {
        "cites M99999, which no tool returned": _answer("211.", ("211", ["M99999"])),
        "cites R-deadbeef, which no tool returned": _answer("211.", ("211", ["R-deadbeef"])),
        f"cites {real_but_not_returned}, which no tool": _answer("x", ("x", [real_but_not_returned])),
        "Claim 1 cites nothing": _answer("211.", ("211", [])),
        "`claims` is empty": _answer("211."),
        "answer mentions M99999, which no tool returned": _answer(
            "211, see M99999.", ("211", [count_id])
        ),
    }
    for expected, answer in cases.items():
        assert any(expected in p for p in check(answer, run)), expected

    # An ID in the prose that a tool did return must still be cited by a claim.
    example = run.results[codes_id]["mention_ids"][0]
    (problem,) = check(_answer(f"See {example}.", ("211", [count_id])), run)
    assert problem == f"The answer mentions {example} but no claim cites it."


def test_render_shows_answer_evidence_and_cost(run):
    run.answer = _answer("Nitro has 211.", ("211 Nitro conversations", ["R-1"]))
    run.status, run.turns, run.input_tokens, run.output_tokens = "answered", 2, 1_000_000, 0
    text = render_run(run)
    assert text.startswith("Nitro has 211.")
    assert "1. 211 Nitro conversations [R-1]" in text and "$0.1000" in text

    run.status, run.problems = "failed_check", ["Claim 1 cites R-1, which no tool returned."]
    assert render_run(run).startswith("NOT VERIFIED")
    run.answer = run.answer | {"answerable": "no", "needs": "Subscription records."}
    assert "cannot answer" in render_run(run) and "Would need: Subscription records." in render_run(run)
    run.answer = run.answer | {"answerable": "partly"}
    assert render_run(run).count("Partly answerable") == 1


def test_the_pulse_is_a_skill_of_the_consumer_agent(ctx):
    assert ("consumer", "pulse") in skill_files()
    spec = load_skill("consumer", ctx, "pulse")
    assert spec.name == "consumer (pulse)" and "Monday pulse" in spec.instructions
    with pytest.raises(HalyardError, match="no skill 'digest'"):
        load_skill("consumer", ctx, "digest")


def test_pulse_week_must_start_a_reporting_week_in_the_data():
    from halyard.agents.pulse import pulse_request, pulse_week

    client = load_client("brewbird")
    week = pulse_week(client, "2026-09-28")
    assert (week.start.isoformat(), week.end.isoformat()) == ("2026-09-28", "2026-10-04")
    assert "week: 2026-09-28" in pulse_request(week)
    with pytest.raises(HalyardError, match="starts on 2026-09-28"):
        pulse_week(client, "2026-09-30")
    with pytest.raises(HalyardError):
        pulse_week(client, "2026-10-05")  # after the data ends


def test_pulse_is_written_with_its_evidence(run, tmp_path):
    from halyard.agents.pulse import pulse_week, write_pulse

    week = pulse_week(load_client("brewbird"), "2026-09-28")
    run.answer = _answer("# Monday pulse: week of 28 Sep\n\nNitro TST 13.", ("13", ["R-1"]))
    run.status = "answered"
    text = write_pulse(run, week, tmp_path).read_text()
    assert text.startswith("# Monday pulse: week of 28 Sep")
    assert "1. 13 [R-1]" in text and "NOT VERIFIED" not in text
    run.status = "failed_check"
    path = write_pulse(run, week, tmp_path)
    assert path.name == "pulse-2026-09-28.md" and path.read_text().startswith("> NOT VERIFIED")
