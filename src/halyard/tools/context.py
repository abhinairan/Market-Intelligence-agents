"""What every tool is given: the store, the client's settings, and the reads tools share."""

from __future__ import annotations

from functools import cached_property

from halyard.settings import ClientConfig
from halyard.store.graph_store import GraphStore, MentionRow
from halyard.tools.filters import Names


class ToolContext:
    """One per run. Mentions and names are read once and reused by every tool call."""

    def __init__(self, store: GraphStore, client: ClientConfig):
        self.store = store
        self.client = client

    @cached_property
    def mentions(self) -> list[MentionRow]:
        return self.store.mentions()

    @cached_property
    def names(self) -> Names:
        return Names(self.store)
