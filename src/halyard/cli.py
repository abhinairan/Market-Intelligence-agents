"""The `halyard` command. The Makefile only wraps these subcommands."""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager

from halyard import runtime
from halyard.settings import PROJECT_ROOT, HalyardError, load_settings


class NotBuiltYet(HalyardError):
    def __init__(self, what: str, phase: str):
        super().__init__(f"`halyard {what}` is not implemented yet ({phase} in docs/PLAN.md).")


def cmd_up(args: argparse.Namespace) -> None:
    settings = load_settings()
    runtime.up(settings)
    print(f"Neo4j is ready at {settings.neo4j_uri}. Browser: http://localhost:{settings.neo4j_http_port}")


def cmd_down(args: argparse.Namespace) -> None:
    runtime.down(wipe=args.wipe)
    print("Neo4j stopped" + (" and its data volume removed." if args.wipe else "."))


def cmd_llm_check(args: argparse.Namespace) -> None:
    from halyard.llm import get_client

    settings = load_settings()
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    for purpose in ("label", "agent"):
        client = get_client(settings, purpose)
        r = client.complete_json("Reply with ok=true.", "Health check.", schema, "health_check")
        print(f"{purpose}: {r.provider}/{r.model} ok={r.data['ok']} "
              f"({r.input_tokens} in, {r.output_tokens} out)")

    # The agents also need tool calling: one call, its result sent back, then an answer.
    from halyard.llm import Message, ToolSpec

    tool = ToolSpec("report_status", "Report the health check status.", schema)
    messages = [Message("user", "Health check. Call report_status with ok=true.")]
    first = client.run_with_tools("Use the tool.", messages, [tool], require_tool=True)
    call = first.tool_calls[0]
    messages += [first.message, Message("tool", '{"received": true}', tool_call_id=call.id)]
    last = client.run_with_tools("Reply with the word done.", messages, [tool])
    print(f"agent tools: {first.model} called {call.name}({call.arguments}), "
          f"then replied {last.text.strip()!r} "
          f"({first.input_tokens + last.input_tokens} in, "
          f"{first.output_tokens + last.output_tokens} out)")


def cmd_spend(args: argparse.Namespace) -> None:
    from halyard.llm.spend import summarise

    rows = summarise(run_id=args.run)
    if not rows:
        raise HalyardError("No model calls are logged" + (f" for run {args.run}." if args.run else "."))
    for r in rows:
        cost = "no price in config/llm_prices.yaml" if r["cost_usd"] is None else f"${r['cost_usd']:.4f}"
        print(f"{r['model']} ({r['purpose']}): {r['calls']} calls, {r['input_tokens']:,} in "
              f"({r['cached_input_tokens']:,} cached), {r['output_tokens']:,} out, {cost}")
    known = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    print(f"Total priced: ${sum(known):.4f}")


def cmd_label(args: argparse.Namespace) -> None:
    from halyard.ingest.pipeline import prepare

    p = prepare(load_settings())
    run, labels = p.label_run, p.labels
    print(f"{len(labels)} distinct texts: {run.cache_hits} answers from the cache, "
          f"{run.model_calls} model calls, {run.unlabelled} unlabelled, "
          f"{run.overridden} changed by a client rule.")
    for label in sorted({x.sentiment for x in labels.values()}):
        print(f"  {label}: {sum(1 for x in labels.values() if x.sentiment == label)} texts")


def cmd_build(args: argparse.Namespace) -> None:
    from collections import Counter

    from halyard.ingest.graph import build_graph
    from halyard.ingest.pipeline import prepare
    from halyard.store.neo4j_writer import connect, stored_counts, write_graph

    settings = load_settings()
    runtime.wait_for_neo4j(settings, timeout_s=10)
    p = prepare(settings)
    graph = build_graph(p, settings.client)
    with connect(settings) as driver:
        write_graph(graph, driver)
        stored = stored_counts(driver)

    report, run = p.pack.report, p.label_run
    print(f"Read {report.mention_rows} mention rows: {len(p.pack.mentions)} unique mentions, "
          f"{report.duplicate_rows} duplicate rows collapsed.")
    statuses = Counter(p.statuses.values())
    print("Mentions by status: " + ", ".join(f"{k} {v}" for k, v in statuses.most_common()) + ".")
    print(f"Labels: {len(p.labels)} distinct texts, {run.cache_hits} answers from the cache, "
          f"{run.model_calls} model calls, {run.unlabelled} unlabelled, "
          f"{run.overridden} changed by a client rule.")
    for kind in ("nodes", "edges"):
        print(f"{kind.capitalize()} ({sum(stored[kind].values())}): "
              + ", ".join(f"{k} {v}" for k, v in sorted(stored[kind].items())))
    expected = {k: dict(v) for k, v in graph.counts().items()}
    if stored != expected:
        raise HalyardError("The database does not hold what was built; see the counts above.")


def cmd_ontology(args: argparse.Namespace) -> None:
    from halyard.store.schema import render_ontology

    path = PROJECT_ROOT / "docs" / "ontology.md"
    path.write_text(render_ontology(), encoding="utf-8")
    print(f"Wrote {path.relative_to(PROJECT_ROOT)}.")


def cmd_skills(args: argparse.Namespace) -> None:
    from halyard.agents.skills import write_tools

    for path in write_tools():
        print(f"Wrote {path.relative_to(PROJECT_ROOT)}.")


def cmd_demo(args: argparse.Namespace) -> None:
    settings = load_settings()
    if not settings.llm_api_key:
        key = f"{settings.llm_provider.upper()}_API_KEY"
        raise HalyardError(f"{key} is empty in .env; the demo needs it for the agents.")
    runtime.up(settings)
    cmd_build(args)
    raise NotBuiltYet("demo (the sample questions)", "P4")


def cmd_ask(args: argparse.Namespace) -> None:
    import json

    from halyard.agents.citations import citation_check
    from halyard.agents.loop import Limits, run_agent, save_run
    from halyard.agents.render import render_run
    from halyard.agents.skills import load_skill
    from halyard.llm import get_client

    settings = load_settings()
    client = get_client(settings, "agent")
    with tool_context() as ctx:
        spec = load_skill(args.agent, ctx)
        limits = Limits.from_client(settings.client)
        run = run_agent(client, ctx, spec, args.question, limits, citation_check(ctx))
    path = save_run(run)
    print(json.dumps(run.answer, indent=2, ensure_ascii=False) if args.json else render_run(run))
    print(f"\nTranscript: {path.relative_to(PROJECT_ROOT)}")
    if run.status != "answered":
        raise HalyardError(f"Run {run.run_id} ended as {run.status}; see the transcript.")


def cmd_pulse(args: argparse.Namespace) -> None:
    raise NotBuiltYet("pulse", "P4")


@contextmanager
def tool_context():
    """A ToolContext over the built graph in Neo4j, with the tool-call log switched on."""
    from halyard.store.neo4j_store import Neo4jStore
    from halyard.store.neo4j_writer import connect
    from halyard.tools.context import ToolContext
    from halyard.tools.log import TOOL_LOG

    settings = load_settings()
    runtime.wait_for_neo4j(settings, timeout_s=10)
    with connect(settings) as driver:
        ctx = ToolContext(Neo4jStore(driver), settings.client, tool_log=TOOL_LOG)
        if not ctx.mentions:
            raise HalyardError("The graph is empty. Run `halyard build` first.")
        yield ctx


def cmd_tool(args: argparse.Namespace) -> None:
    import json

    from halyard.tools.registry import TOOLS, run_tool

    if args.name is None:
        for tool in TOOLS.values():
            print(f"{tool.name}({', '.join(tool.parameters['properties'])})\n  {tool.description}")
        return
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as exc:
        raise HalyardError(f"The arguments are not valid JSON: {exc}") from exc
    with tool_context() as ctx:
        print(json.dumps(run_tool(ctx, args.name, tool_args), indent=2, ensure_ascii=False))


def cmd_trace(args: argparse.Namespace) -> None:
    from halyard.tools.trace import render_trace, trace

    with tool_context() as ctx:
        # Called directly: looking something up is not itself a call worth logging.
        print(render_trace(trace(ctx, args.ids).to_dict()["data"]))


def cmd_eval(args: argparse.Namespace) -> None:
    raise NotBuiltYet("eval", "P5")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="halyard", description="Brand knowledge graph and agents.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("up", help="start Neo4j and wait until it is ready").set_defaults(func=cmd_up)

    down = sub.add_parser("down", help="stop Neo4j")
    down.add_argument("--wipe", action="store_true", help="also delete the Neo4j data volume")
    down.set_defaults(func=cmd_down)

    sub.add_parser("llm-check", help="one tiny call per configured model").set_defaults(
        func=cmd_llm_check
    )
    spend = sub.add_parser("spend", help="tokens and cost from the usage log")
    spend.add_argument("--run", help="one agent run ID (A-...)")
    spend.set_defaults(func=cmd_spend)
    sub.add_parser("label", help="label new texts and add them to the label cache").set_defaults(
        func=cmd_label
    )
    sub.add_parser("build", help="wipe and rebuild the graph from the raw pack").set_defaults(
        func=cmd_build
    )
    sub.add_parser("ontology", help="regenerate docs/ontology.md from the schema").set_defaults(
        func=cmd_ontology
    )
    sub.add_parser("demo", help="up, build, then one sample question per agent").set_defaults(
        func=cmd_demo
    )

    sub.add_parser(
        "skills", help="regenerate each agent's skills/<agent>/tools.json from the tool registry"
    ).set_defaults(func=cmd_skills)

    ask = sub.add_parser("ask", help="ask an agent a question")
    ask.add_argument("agent", help="a folder under skills/ with a SKILL.md, e.g. consumer")
    ask.add_argument("question")
    ask.add_argument("--json", action="store_true", help="print the structured answer")
    ask.set_defaults(func=cmd_ask)

    pulse = sub.add_parser("pulse", help="write the Monday pulse for a reporting week")
    pulse.add_argument("--week", required=True, help="Monday of the week, YYYY-MM-DD")
    pulse.set_defaults(func=cmd_pulse)

    trace = sub.add_parser("trace", help="trace mention or result IDs back to file and row")
    trace.add_argument("ids", nargs="+", help="mention IDs, ad IDs, observation keys, R-... IDs")
    trace.set_defaults(func=cmd_trace)

    tool = sub.add_parser("tool", help="run one query tool; with no name, list the tools")
    tool.add_argument("name", nargs="?")
    tool.add_argument("args", nargs="?", default="{}", help="arguments as JSON")
    tool.set_defaults(func=cmd_tool)

    sub.add_parser("eval", help="run golden and adversarial sets, write the report").set_defaults(
        func=cmd_eval
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except HalyardError as exc:
        print(f"halyard: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
