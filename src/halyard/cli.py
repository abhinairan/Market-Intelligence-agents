"""The `halyard` command. The Makefile only wraps these subcommands."""

from __future__ import annotations

import argparse
import sys

from halyard import runtime
from halyard.settings import HalyardError, load_settings


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


def cmd_build(args: argparse.Namespace) -> None:
    raise NotBuiltYet("build", "P2")


def cmd_demo(args: argparse.Namespace) -> None:
    settings = load_settings()
    if not settings.llm_api_key:
        key = f"{settings.llm_provider.upper()}_API_KEY"
        raise HalyardError(f"{key} is empty in .env; the demo needs it for the agents.")
    runtime.up(settings)
    cmd_build(args)


def cmd_ask(args: argparse.Namespace) -> None:
    raise NotBuiltYet("ask", "P4")


def cmd_pulse(args: argparse.Namespace) -> None:
    raise NotBuiltYet("pulse", "P4")


def cmd_trace(args: argparse.Namespace) -> None:
    raise NotBuiltYet("trace", "P3")


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
    sub.add_parser("build", help="wipe and rebuild the graph from the raw pack").set_defaults(
        func=cmd_build
    )
    sub.add_parser("demo", help="up, build, then one sample question per agent").set_defaults(
        func=cmd_demo
    )

    ask = sub.add_parser("ask", help="ask an agent a question")
    ask.add_argument("agent", choices=["consumer", "competitor"])
    ask.add_argument("question")
    ask.set_defaults(func=cmd_ask)

    pulse = sub.add_parser("pulse", help="write the Monday pulse for a reporting week")
    pulse.add_argument("--week", required=True, help="Monday of the week, YYYY-MM-DD")
    pulse.set_defaults(func=cmd_pulse)

    trace = sub.add_parser("trace", help="trace mention or result IDs back to file and row")
    trace.add_argument("ids", nargs="+")
    trace.set_defaults(func=cmd_trace)

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
