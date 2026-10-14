"""Lines of a saved page, each with the `file:line` reference that cites it."""

from __future__ import annotations

import re
from typing import Any

REF = re.compile(r"^(?P<file>.+):(?P<line>\d+)$")


def page_lines(source: dict[str, Any]) -> list[tuple[str, str]]:
    """(`file:line`, text) for every non-blank line of a Source node's body."""
    if not source.get("body"):
        return []
    first = source["body_row"]
    return [
        (f"{source['file']}:{first + i}", line.strip())
        for i, line in enumerate(source["body"].splitlines())
        if line.strip()
    ]
