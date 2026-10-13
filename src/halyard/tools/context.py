"""What every tool is given: the store, the client's settings, and the reads tools share."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Any

from halyard.settings import ClientConfig
from halyard.store.graph_store import GraphStore, MentionRow
from halyard.tools.filters import Names


class ToolContext:
    """One per run. Mentions and names are read once and reused by every tool call."""

    def __init__(self, store: GraphStore, client: ClientConfig, tool_log: Path | None = None):
        self.store = store
        self.client = client
        self.tool_log = tool_log  # where calls are logged and result IDs looked up; None = off

    @cached_property
    def mentions(self) -> list[MentionRow]:
        return self.store.mentions()

    @cached_property
    def names(self) -> Names:
        return Names(self.store)

    @cached_property
    def products(self) -> dict[str, dict[str, Any]]:
        """Each product's name, brand and lines, from its OF_BRAND and IN_LINE edges."""
        products = {}
        for p in self.store.nodes("Product"):
            edges = self.store.node("Product", p["key"]).edges
            products[p["key"]] = {
                "key": p["key"],
                "name": p["name"],
                "brand": next(e.other[1] for e in edges if e.kind == "OF_BRAND"),
                "lines": tuple(e.other[1] for e in edges if e.kind == "IN_LINE"),
            }
        return products

    @cached_property
    def code_owners(self) -> dict[str, str]:
        """D-34: the team that owns each complaint code, from the client's taxonomy."""
        owners = {}
        for code in self.names.codes:
            view = self.store.node("ComplaintCode", code["code"])
            owners[code["code"]] = next(e.other[1] for e in view.edges if e.kind == "OWNED_BY")
        return owners
