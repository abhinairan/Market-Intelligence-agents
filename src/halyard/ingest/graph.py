"""Turn the prepared pack into graph nodes and edges, with provenance on every one.

Pure: nothing here talks to a database, so the whole graph can be checked in a test. Every
node and edge is validated against the ontology in halyard.store.schema.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import yaml

from halyard.ingest.entities import EntityResolver, load_entities_config
from halyard.ingest.pipeline import Prepared
from halyard.ingest.records import PackSize, PageRecord
from halyard.settings import PROJECT_ROOT, ClientConfig, HalyardError
from halyard.store.schema import EDGE_PROVENANCE, EDGES, NODES, inferred_properties

NodeRef = tuple[str, str]  # (label, key value)


@dataclass
class Graph:
    nodes: dict[NodeRef, dict[str, Any]] = field(default_factory=dict)
    edges: dict[tuple[str, NodeRef, NodeRef], dict[str, Any]] = field(default_factory=dict)

    def node(
        self, label: str, key: str, source_file: str | None, source_ref: str | None, **props: Any
    ) -> NodeRef:
        node_type = NODES[label]
        unknown = set(props) - set(node_type.properties)
        if unknown:
            raise HalyardError(f"{label} has no property {sorted(unknown)} in the ontology.")
        kept = {k: _value(v) for k, v in props.items() if v is not None and v != () and v != []}
        kept[node_type.key] = key
        existing = self.nodes.setdefault((label, key), {})
        existing.update(kept)
        if source_file:
            existing.setdefault("source_file", source_file)
        if source_ref:
            existing.setdefault("source_ref", source_ref)
        existing["inferred_properties"] = inferred_properties(label, existing)
        return (label, key)

    def edge(
        self,
        kind: str,
        source: NodeRef,
        target: NodeRef,
        *,
        method: str,
        source_file: str,
        source_ref: str,
        captured_at: date | None = None,
        **props: Any,
    ) -> None:
        edge_type = EDGES[kind]
        if source[0] not in edge_type.source or target[0] not in edge_type.target:
            raise HalyardError(f"{kind} cannot join {source[0]} to {target[0]} in the ontology.")
        unknown = set(props) - set(EDGE_PROVENANCE) - set(edge_type.properties)
        if unknown:
            raise HalyardError(f"{kind} has no property {sorted(unknown)} in the ontology.")
        if method not in ("extracted", "inferred"):
            raise HalyardError(f"{kind}: method must be extracted or inferred, not {method!r}.")
        if method == "inferred" and not (props.get("rule") or props.get("model")):
            raise HalyardError(f"{kind}: an inferred edge must name its rule or model.")
        all_props = {
            "method": method,
            "source_file": source_file,
            "source_ref": source_ref,
            "captured_at": captured_at,
            **props,
        }
        # The first evidence for an edge is kept, so its provenance is the earliest row.
        self.edges.setdefault(
            (kind, source, target), {k: _value(v) for k, v in all_props.items() if v is not None}
        )

    def check(self) -> None:
        for kind, source, target in self.edges:
            for ref in (source, target):
                if ref not in self.nodes:
                    raise HalyardError(f"{kind} points at {ref}, which is not in the graph.")

    def counts(self) -> dict[str, Counter[str]]:
        return {
            "nodes": Counter(label for label, _ in self.nodes),
            "edges": Counter(kind for kind, _, _ in self.edges),
        }


def _value(v: Any) -> Any:
    return list(v) if isinstance(v, tuple) else v


def _pack_props(pack: PackSize, price: float) -> dict[str, Any]:
    """D-53: per-unit prices, so packs of different sizes compare like with like."""
    props: dict[str, Any] = {
        "pack": pack.raw,
        "unit_count": pack.unit_count,
        "unit_size": pack.unit_size,
        "unit": pack.unit,
        "unit_price": round(price / pack.unit_count, 2),
    }
    if pack.unit != "bag":
        props["price_per_100"] = round(price / (pack.unit_count * pack.unit_size) * 100, 2)
    return props


def build_graph(prepared: Prepared, client: ClientConfig) -> Graph:
    g = Graph()
    entities = load_entities_config(client)
    resolver = EntityResolver(entities, prepared.pack.products)
    builder = _Builder(g, prepared, client, entities, resolver)
    builder.sources()
    builder.brands_and_lines()
    builder.catalogue()
    builder.taxonomy()
    builder.mentions()
    builder.competitor_prices()
    builder.page_facts()
    builder.ads()
    g.check()
    return g


class _Builder:
    def __init__(
        self,
        g: Graph,
        prepared: Prepared,
        client: ClientConfig,
        entities: dict[str, Any],
        resolver: EntityResolver,
    ):
        self.g, self.p, self.client = g, prepared, client
        self.entities, self.resolver = entities, resolver
        self.pack = prepared.pack
        self.files = client.raw["files"]
        self.entities_file = str(
            (client.config_dir / "entities.yaml").relative_to(PROJECT_ROOT).as_posix()
        )
        self.pages = {page.source.file: page for page in self.pack.pages}

    # --- reference data -----------------------------------------------------------------

    def sources(self) -> None:
        for kind, name in self.files.items():
            self.g.node("Source", name, name, None, kind=kind)
        for page in self.pack.pages:
            self.g.node(
                "Source", page.source.file, page.source.file, str(page.source),
                kind=page.kind, title=page.title, url=page.url,
                captured_at=page.captured_at, body=page.body,
                body_row=page.body_row if page.body else None,
            )  # fmt: skip
            # Whose page it is, read from its title and URL (D-20, D-21).
            for ref in self.resolver.resolve(f"{page.title} {page.url}").brands:
                self.g.edge(
                    "PUBLISHED_BY", ("Source", page.source.file), ("Brand", ref.brand),
                    method="inferred", rule=ref.rule, matched=ref.matched,
                    source_file=page.source.file, source_ref=str(page.source),
                    captured_at=page.captured_at,
                )  # fmt: skip

    def brands_and_lines(self) -> None:
        client_key = self.p.client_brand
        for b in self.entities["brands"]:
            self.g.node(
                "Brand", b["key"], self.entities_file, None,
                name=b["name"], is_client=bool(b.get("is_client")),
            )  # fmt: skip
        for b in self.entities["brands"]:
            if b["key"] != client_key:
                # D-21: the competitors the client tracks, as configured.
                self.g.edge(
                    "COMPETES_WITH", ("Brand", client_key), ("Brand", b["key"]),
                    method="inferred", rule="D-21",
                    source_file=self.entities_file, source_ref=self.entities_file,
                )  # fmt: skip
            for ln in b.get("lines", []):
                line = self._line(b["key"], ln["name"])
                self.g.node(
                    "ProductLine", line[1], self.entities_file, None,
                    name=ln["name"], sub_brand=ln.get("sub_brand"),
                )  # fmt: skip
                self._line_of_brand(line, b["key"], ln)

    def _line_of_brand(self, line: NodeRef, brand: str, ln: dict[str, Any]) -> None:
        first = next((p for p in self.pack.products if p.sub_brand == ln.get("sub_brand")), None)
        page = self.pages.get(ln.get("source", ""))
        if first:  # the client's catalogue names the sub-brand
            where = {"method": "extracted", "source_file": first.source.file,
                         "source_ref": str(first.source)}  # fmt: skip
        elif page:  # a saved first-party page says so (ER-01): cite the line that names it
            where = {"method": "extracted", "source_file": page.source.file,
                         "source_ref": page_line_ref(page, ln["name"]),
                         "captured_at": page.captured_at}  # fmt: skip
        else:
            where = {"method": "inferred", "rule": "D-24", "source_file": self.entities_file,
                         "source_ref": self.entities_file}  # fmt: skip
        self.g.edge("OF_BRAND", line, ("Brand", brand), **where)

    @staticmethod
    def _line(brand: str, name: str) -> NodeRef:
        return ("ProductLine", f"{brand}:{name}")

    def catalogue(self) -> None:
        """Client products and their catalogue prices, which carry no capture date (D-52)."""
        brand = self.p.client_brand
        lines = {
            ln["sub_brand"]: ln["name"]
            for b in self.entities["brands"] if b["key"] == brand
            for ln in b.get("lines", [])
        }  # fmt: skip
        cat = self.client.raw["catalogue"]
        for p in self.pack.products:
            ref, where = str(p.source), p.source.file
            product = self.g.node(
                "Product", p.sku, where, ref,
                sku=p.sku, name=p.product_name, aliases=p.aliases, launched=p.launched,
            )  # fmt: skip
            shared = {"method": "extracted", "source_file": where, "source_ref": ref}
            self.g.edge("IN_LINE", product, self._line(brand, lines[p.sub_brand]), **shared)
            self.g.edge("OF_BRAND", product, ("Brand", brand), **shared)
            obs = self.g.node(
                "Observation", f"price:{ref}", where, ref,
                kind="price", undated=True, value=p.price_inr,
                currency=cat["currency"], region=cat["region"],
                **_pack_props(p.pack, p.price_inr),
            )  # fmt: skip
            self.g.edge("ABOUT", obs, product, **shared)
            self.g.edge("FROM", obs, ("Source", where), **shared)

    def taxonomy(self) -> None:
        for t in self.pack.taxonomy:
            ref, where = str(t.source), t.source.file
            code = self.g.node(
                "ComplaintCode", t.code, where, ref,
                name=t.name, includes=t.includes, client_rule=t.client_rule,
            )  # fmt: skip
            team = self.g.node("Team", t.owner_team, where, ref)
            self.g.edge("OWNED_BY", code, team, method="extracted", source_file=where,
                        source_ref=ref)  # fmt: skip

    # --- mentions -----------------------------------------------------------------------

    def mentions(self) -> None:
        p, h = self.p, self.p.hygiene
        unrelated = {u["key"]: u for u in self.entities.get("unrelated_entities", [])}
        for u in unrelated.values():
            self.g.node("UnrelatedEntity", u["key"], self.entities_file, None,
                        name=u["name"], collides_with=u["collides_with"])  # fmt: skip
        for m in self.pack.mentions:
            mid, where = m.mention_id, m.source.file
            res, status, label = p.resolutions[mid], p.statuses[mid], p.label_of(mid)
            rule, reason = self._exclusion(mid, status)
            mention = self.g.node(
                "Mention", mid, where, str(m.source),
                platform=m.platform, posted_at=m.posted_at, text=m.text, likes=m.likes,
                url=m.url, is_repost_of=m.is_repost_of, source_rows=m.source_rows,
                date_ist=m.date_ist, week_ist=m.week_ist, city=m.city,
                normalised_text=h.normalised[mid], status=status,
                exclusion_rule=rule, exclusion_reason=reason,
                spam_burst=h.spam.get(mid), repost_count=h.repost_counts.get(mid),
                implied_references=res.implied, id_conflict=m.id_conflict or None,
                sentiment=label.sentiment if label else None,
                sentiment_source=label.sentiment_source if label else None,
                sentiment_prompt=label.sentiment_prompt if label else None,
                sentiment_reason=label.sentiment_reason if label else None,
                codes_status=label.codes_status if label else None,
                label_overrides=label.overrides if label else None,
            )  # fmt: skip
            shared = {"source_file": where, "source_ref": mid}

            author = self.g.node(
                "Author", m.author_handle, where, None,
                account_class=h.account_classes.get(m.author_handle, "person"),
            )  # fmt: skip
            self.g.edge("POSTED_BY", mention, author, method="extracted", **shared)

            for b in res.brands:
                self.g.edge("MENTIONS", mention, ("Brand", b.brand), method="inferred",
                            rule=b.rule, matched=b.matched, **shared)  # fmt: skip
            for ln in res.lines:
                self.g.edge("MENTIONS", mention, self._line(ln.brand, ln.line),
                            method="inferred", rule=ln.rule, matched=ln.matched, **shared)  # fmt: skip
            if res.set_aside and res.set_aside.kind == "unrelated":
                self.g.edge("MENTIONS", mention, ("UnrelatedEntity", res.set_aside.key),
                            method="inferred", rule=res.set_aside.rule,
                            matched=res.set_aside.matched, **shared)  # fmt: skip

            repost = h.reposts.get(mid)
            if repost and repost.original_id:
                self.g.edge(
                    "REPOST_OF", mention, ("Mention", repost.original_id),
                    method=repost.method, basis=repost.basis,
                    quoted_handle=repost.quoted_handle,
                    rule="D-11" if repost.method == "inferred" else None, **shared,
                )  # fmt: skip
            if mid in h.double_posts:
                self.g.edge("DOUBLE_POST_OF", mention, ("Mention", h.double_posts[mid]),
                            method="inferred", rule="D-17", **shared)  # fmt: skip

            for code in label.codes if label else ():
                kind, _, name = code.source.partition(":")
                self.g.edge(
                    "HAS_COMPLAINT", mention, ("ComplaintCode", code.code), method="inferred",
                    model=name if kind == "model" else None,
                    rule=name if kind == "override" else "D-31",
                    prompt_hash=label.codes_prompt, reason=label.codes_reason, **shared,
                )  # fmt: skip

    def _exclusion(self, mention_id: str, status: str) -> tuple[str | None, str | None]:
        """D-16: why a mention is not counted, as a rule ID and what the rule found."""
        h, res = self.p.hygiene, self.p.resolutions[mention_id]
        if status == "genuine":
            return None, None
        if status == "spam":
            return "D-13", "spam_burst"
        if status == "repost":
            return "D-11", f"repost:{h.reposts[mention_id].basis}"
        if status == "double_post":
            return "D-17", "double_post"
        if status == "unrelated":
            return res.set_aside.rule, f"unrelated_entity:{res.set_aside.key}"
        if status == "ambiguous":
            return res.set_aside.rule, "unresolved_entity"
        return "D-20", "no_entity_resolved"

    # --- competitor evidence ------------------------------------------------------------

    def _stale(self, observed: date) -> bool:
        return (self.client.as_of - observed).days > self.client.stale_after_days  # D-52

    def _brand_of(self, name: str, where: str) -> str:
        brand = self.resolver.brand_named(name)
        if brand is None:
            raise HalyardError(f"{where}: {name!r} is not a brand name in entities.yaml.")
        return brand

    def competitor_prices(self) -> None:
        for r in self.pack.prices:
            ref, where = str(r.source), r.source.file
            brand = self._brand_of(r.competitor, ref)
            shared = {"source_file": where, "source_ref": ref, "captured_at": r.captured_at}
            product = self.g.node("Product", f"{brand}:{r.product}", where, ref, name=r.product)
            self.g.edge("OF_BRAND", product, ("Brand", brand), method="extracted", **shared)
            for line, matched in self.resolver.lines_for(brand, r.product):
                self.g.edge("IN_LINE", product, self._line(brand, line), method="inferred",
                            rule="D-24", matched=matched, **shared)  # fmt: skip
            obs = self.g.node(
                "Observation", f"price:{ref}", where, ref,
                kind="price", observed_at=r.captured_at, stale=self._stale(r.captured_at),
                value=r.price, currency=r.currency, region=r.region, url=r.source_url,
                **_pack_props(r.pack, r.price),
            )  # fmt: skip
            self.g.edge("ABOUT", obs, product, method="extracted", **shared)
            self.g.edge("FROM", obs, ("Source", where), method="extracted", **shared)

    def page_facts(self) -> None:
        """D-50: facts stated on saved pages, dated by the page's capture date."""
        path = self.client.config_dir / "observations.yaml"
        facts = yaml.safe_load(path.read_text())["page_facts"] if path.exists() else []
        for page in self.pack.pages:
            where = page.source.file
            publishers = [
                target for (kind, source, target) in self.g.edges
                if kind == "PUBLISHED_BY" and source == ("Source", where)
            ]  # fmt: skip
            for fact in facts:
                for hit in re.finditer(fact["pattern"], page.body):
                    row = page.body_row + page.body.count("\n", 0, hit.start())
                    ref = f"{where}:{row}"
                    value = hit.groupdict().get("value")
                    obs = self.g.node(
                        "Observation", f"{fact['kind']}:{ref}", where, ref,
                        kind=fact["kind"], observed_at=page.captured_at,
                        stale=self._stale(page.captured_at), text=hit[0],
                        value=int(value) if value else None,
                        currency=fact.get("currency") if value else None, pattern=fact["kind"],
                    )  # fmt: skip
                    shared = {"source_file": where, "source_ref": ref,
                                  "captured_at": page.captured_at}  # fmt: skip
                    self.g.edge("FROM", obs, ("Source", where), method="extracted", **shared)
                    for brand in publishers:
                        self.g.edge("ABOUT", obs, brand, method="inferred", rule="D-50", **shared)
                        for line, matched in self.resolver.lines_for(brand[1], hit[0]):
                            self.g.edge("ABOUT", obs, self._line(brand[1], line),
                                        method="inferred", rule="D-24", matched=matched,
                                        **shared)  # fmt: skip

    def ads(self) -> None:
        for a in self.pack.ads:
            ref, where = str(a.source), a.source.file
            brand = self._brand_of(a.advertiser, ref)
            ad = self.g.node(
                "Ad", a.ad_id, where, ref,
                platform=a.platform, first_seen=a.first_seen, last_seen=a.last_seen,
                headline=a.headline, offer=a.offer, landing_url=a.landing_url,
                still_running=a.last_seen >= self.client.window_end,  # D-54
            )  # fmt: skip
            shared = {"source_file": where, "source_ref": ref}
            self.g.edge("RUN_BY", ad, ("Brand", brand), method="extracted", **shared)
            for line, matched in self.resolver.lines_for(brand, a.headline):
                self.g.edge("PROMOTES", ad, self._line(brand, line), method="inferred",
                            rule="D-24", matched=matched, **shared)  # fmt: skip


def page_line_ref(page: PageRecord, text: str) -> str:
    """`file:line` of the first body line that contains `text`, ignoring case; the page's
    own reference when no line does."""
    for i, line in enumerate(page.body.splitlines()):
        if text.lower() in line.lower():
            return f"{page.source.file}:{page.body_row + i}"
    return str(page.source)
