"""Date windows for the tools, in the client's local dates (D-01 to D-04).

Mentions already carry `date_ist` and `week_ist`, so a window is only ever compared with
those. Nothing here touches a timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from halyard.ingest.loaders import week_start
from halyard.settings import ClientConfig
from halyard.tools.base import ToolError


@dataclass(frozen=True)
class Window:
    start: date  # inclusive
    end: date  # inclusive
    note: str | None = None  # set when the request reached past the data and was clipped

    def __contains__(self, day: date) -> bool:
        return self.start <= day <= self.end

    def describe(self) -> str:
        return f"{_show(self.start)} to {_show(self.end)}" + (f" ({self.note})" if self.note else "")


def _show(day: date) -> str:
    return f"{day.day} {day:%b %Y}"


def _date(value: date | str, name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{name} must be a date written YYYY-MM-DD, not {value!r}.") from None


def resolve_window(
    client: ClientConfig,
    start: date | str | None = None,
    end: date | str | None = None,
    last_weeks: int | None = None,
    week: date | str | None = None,
) -> Window:
    """One window from whichever form was asked for; the whole data window when none was.

    - `start` / `end`: explicit dates; a missing one is the edge of the data window.
    - `last_weeks`: the N most recent full reporting weeks ending on the as-of date (D-03).
    - `week`: the reporting week containing this date (D-02).
    """
    covered = Window(client.window_start, client.window_end)
    if sum((start is not None or end is not None, last_weeks is not None, week is not None)) > 1:
        raise ToolError("Give start/end, or last_weeks, or week: only one of the three.")

    if last_weeks is not None:
        if last_weeks < 1:
            raise ToolError("last_weeks must be 1 or more.")
        # The last full week ends on the as-of date, or on the week end before it.
        this_week = week_start(client.as_of, client.week_starts_on)
        last = client.as_of if client.as_of == this_week + timedelta(days=6) else (
            this_week - timedelta(days=1)
        )  # fmt: skip
        asked = Window(last - timedelta(days=7 * last_weeks - 1), last)
    elif week is not None:
        first = week_start(_date(week, "week"), client.week_starts_on)
        asked = Window(first, first + timedelta(days=6))
    else:
        asked = Window(
            _date(start, "start") if start is not None else covered.start,
            _date(end, "end") if end is not None else covered.end,
        )
        if asked.start > asked.end:
            raise ToolError(f"start ({asked.start}) is after end ({asked.end}).")

    if asked.end < covered.start or asked.start > covered.end:
        # D-04: never extrapolated.
        raise ToolError(
            f"No data for {asked.describe()}. The data covers {covered.describe()} (D-04)."
        )
    if asked.start < covered.start or asked.end > covered.end:
        return Window(
            max(asked.start, covered.start),
            min(asked.end, covered.end),
            note=f"asked for {asked.describe()}; the data covers only {covered.describe()}, D-04",
        )
    return asked


def weeks_in(client: ClientConfig, window: Window) -> list[date]:
    """The reporting weeks a window touches, each named by its first day (D-02)."""
    first = week_start(window.start, client.week_starts_on)
    return [first + timedelta(days=7 * i) for i in range((window.end - first).days // 7 + 1)]
