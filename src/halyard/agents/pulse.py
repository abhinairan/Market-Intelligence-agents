"""The Monday pulse: an agent run from the pulse skill, written to a one-page brief."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from halyard.agents.loop import AgentRun
from halyard.agents.render import _footer
from halyard.settings import PROJECT_ROOT, ClientConfig, HalyardError
from halyard.tools.base import ToolError
from halyard.tools.windows import Window, resolve_window

OUTPUT_DIR = PROJECT_ROOT / "outputs"


def pulse_week(client: ClientConfig, week: str) -> Window:
    """The reporting week asked for, which must start on the given day and lie in the data."""
    try:
        window = resolve_window(client, week=week)
    except ToolError as exc:
        raise HalyardError(str(exc)) from exc
    if window.start.isoformat() != week:
        raise HalyardError(f"{week} is not the first day of a reporting week; "
                           f"that week starts on {window.start}.")  # fmt: skip
    return window


def pulse_request(window: Window) -> str:
    return (
        f"Write the Monday pulse for the reporting week {window.start:%d %b %Y} to "
        f"{window.end:%d %b %Y} (pass `week: {window.start}` to the tools for this week)."
    )


def write_pulse(run: AgentRun, window: Window, out_dir: Path = OUTPUT_DIR) -> Path:
    """The brief and the run's footer, as Markdown. The brief carries its example mention IDs
    inline; the claims and what each cites stay in the run's transcript, not in the brief the
    team reads."""
    if run.answer is None:
        raise HalyardError(f"The pulse run ended without a brief: {run.error}")
    lines = [run.answer["answer"].strip(), ""]
    if run.status != "answered":
        lines = ["> NOT VERIFIED: this brief failed the citation check.", "", *lines]
    lines += ["---", "", f"<sub>{_footer(run)}. Generated {date.today():%d %b %Y}.</sub>", ""]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pulse-{window.start}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
