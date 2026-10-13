"""The ingest steps in order: load, hygiene, entity resolution, labelling."""

from __future__ import annotations

from dataclasses import dataclass

from halyard.ingest.entities import (
    Resolution,
    load_entities_config,
    mention_status,
    resolve_entities,
)
from halyard.ingest.hygiene import Hygiene, run_hygiene
from halyard.ingest.labelling import Labeller, LabelRun, TextLabel
from halyard.ingest.loaders import load_pack
from halyard.ingest.records import DataPack
from halyard.llm import get_client
from halyard.llm.base import LLMClient
from halyard.settings import HalyardError, Settings


@dataclass(frozen=True)
class Prepared:
    """Everything known about the pack before it is written to the graph."""

    pack: DataPack
    hygiene: Hygiene
    resolutions: dict[str, Resolution]  # by mention_id
    statuses: dict[str, str]  # by mention_id (D-15, D-16)
    client_brand: str  # key of the client's brand in entities.yaml
    labels: dict[str, TextLabel]  # by normalised text
    label_run: LabelRun

    def label_of(self, mention_id: str) -> TextLabel | None:
        """A mention's label, or None when its text was never a genuine conversation."""
        return self.labels.get(self.hygiene.normalised[mention_id])


def texts_to_label(
    pack: DataPack,
    hygiene: Hygiene,
    resolutions: dict[str, Resolution],
    statuses: dict[str, str],
    client_brand: str,
) -> dict[str, bool]:
    """Distinct normalised texts with a genuine mention -> whether any names the client.

    Spam, unrelated and ambiguous texts are never counted, so they are never labelled.
    """
    texts: dict[str, bool] = {}
    for m in pack.mentions:
        if statuses[m.mention_id] == "genuine":
            text = hygiene.normalised[m.mention_id]
            texts[text] = texts.get(text, False) or resolutions[m.mention_id].names(client_brand)
    return texts


def prepare(settings: Settings, llm: LLMClient | None = None) -> Prepared:
    client = settings.client
    pack = load_pack(client)
    hygiene = run_hygiene(pack.mentions, client)
    resolutions = resolve_entities(pack.mentions, pack.products, client)
    statuses = {
        m.mention_id: mention_status(hygiene.status(m.mention_id), resolutions[m.mention_id])
        for m in pack.mentions
    }
    brands = [b["key"] for b in load_entities_config(client)["brands"] if b.get("is_client")]
    if len(brands) != 1:
        raise HalyardError("entities.yaml must mark exactly one brand with is_client: true.")

    # With no key the labeller still serves every cached answer; misses are `unlabelled`.
    if llm is None and settings.llm_api_key and settings.label_model:
        llm = get_client(settings, "label")
    labeller = Labeller(client, pack.taxonomy, settings.llm_provider, settings.label_model, llm)
    labels = labeller.label(texts_to_label(pack, hygiene, resolutions, statuses, brands[0]))
    return Prepared(pack, hygiene, resolutions, statuses, brands[0], labels, labeller.run)
