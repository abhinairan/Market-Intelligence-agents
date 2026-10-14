"""The ontology: every node type, edge type and property the graph may contain.

This is the single definition. The graph builder refuses anything not declared here, the
Neo4j writer creates its constraints from it, and docs/ontology.md is generated from it
(`halyard ontology`), so the three cannot drift apart.

Each property and edge says how its value is obtained:
- `extracted`: copied from a source file as it stands.
- `inferred:<rule>`: computed from extracted values by a named rule in docs/definitions.md,
  or by a named model.
"""

from __future__ import annotations

from dataclasses import dataclass

EXTRACTED = "extracted"
CONFIG = "config"  # our own configuration under config/<client>/, not client data


def inferred(rule: str) -> str:
    return f"inferred:{rule}"


@dataclass(frozen=True)
class NodeType:
    key: str  # the property that identifies a node of this type
    about: str
    properties: dict[str, tuple[str, str]]  # name -> (method, meaning)


@dataclass(frozen=True)
class EdgeType:
    source: tuple[str, ...]
    target: tuple[str, ...]
    method: str  # extracted, inferred:<rule>, or "either" when it varies per edge
    about: str
    properties: dict[str, str]  # name -> meaning, beyond the shared provenance properties


# On every node, besides its own properties.
NODE_PROVENANCE = {
    "source_file": "File the node was read from, relative to the data pack (or the config file).",
    "source_ref": "`file:row` of the row or line it came from.",
    "inferred_properties": "The node's inferred properties as `name:rule`. "
    "Every other property is extracted.",
}

# On every edge.
EDGE_PROVENANCE = {
    "source_file": "File the evidence for the edge comes from.",
    "source_ref": "The row (`file:row`) or the mention ID the edge rests on.",
    "captured_at": "Capture date of that source. Absent when the source states none.",
    "method": "`extracted` or `inferred`.",
    "rule": "For inferred edges, the rule ID in docs/definitions.md.",
    "model": "For edges a model decided, the model name (with `prompt_hash` and `reason`).",
    "matched": "For edges decided by matching text, the exact string that matched.",
}

NODES: dict[str, NodeType] = {
    "Brand": NodeType(
        "key",
        "The client or a competitor.",
        {
            "key": (CONFIG, "Short identifier, e.g. `brewbird`."),
            "name": (CONFIG, "Company name as the data pack writes it."),
            "is_client": (CONFIG, "True for the client."),
        },
    ),
    "ProductLine": NodeType(
        "key",
        "A range of a brand, e.g. Brewbird Nitro or Peak Instant.",
        {
            "key": (CONFIG, "`<brand key>:<line name>`."),
            "name": (CONFIG, "Line name."),
            "sub_brand": (EXTRACTED, "The client catalogue's `sub_brand` for this line."),
        },
    ),
    "Product": NodeType(
        "key",
        "A client SKU or a competitor product.",
        {
            "key": (EXTRACTED, "The SKU, or `<brand key>:<product name>` for competitors."),
            "sku": (EXTRACTED, "Client SKU."),
            "name": (EXTRACTED, "Product name."),
            "aliases": (EXTRACTED, "Customer nicknames from the client catalogue."),
            "launched": (EXTRACTED, "Launch date in the client catalogue."),
        },
    ),
    "UnrelatedEntity": NodeType(
        "key",
        "Something that shares a brand's name but is not the brand (D-22).",
        {
            "key": (CONFIG, "Short identifier."),
            "name": (CONFIG, "What it is."),
            "collides_with": (CONFIG, "Key of the brand whose name it shares."),
        },
    ),
    "Author": NodeType(
        "handle",
        "A public handle that posted at least one mention.",
        {
            "handle": (EXTRACTED, "`author_handle` in the export."),
            "account_class": (inferred("D-13"), "`person`, or `coupon_bot` for spam authors."),
        },
    ),
    "Mention": NodeType(
        "mention_id",
        "One post or review. Every mention in the export is kept, counted or not (D-16).",
        {
            "mention_id": (EXTRACTED, "ID assigned by the listening tool."),
            "platform": (EXTRACTED, "Where it was posted."),
            "posted_at": (EXTRACTED, "Timestamp exactly as exported, offset included (D-01)."),
            "text": (EXTRACTED, "Post text as captured, never altered (D-12)."),
            "likes": (EXTRACTED, "Likes at capture time."),
            "url": (EXTRACTED, "Link to the post."),
            "is_repost_of": (EXTRACTED, "The export tool's repost flag, when set."),
            "source_rows": (EXTRACTED, "Every row of the export holding this mention (D-10)."),
            "date_ist": (inferred("D-01"), "Local date of `posted_at` in the client timezone."),
            "week_ist": (inferred("D-02"), "First day of the reporting week of `date_ist`."),
            "city": (inferred("D-26"), "City named in a bracketed tag in the text."),
            "normalised_text": (inferred("D-12"), "Matching key: the text without decoration."),
            "status": (
                inferred("D-15"),
                ("`genuine`, or why it is not a conversation: `repost`, `spam`, `double_post`, "
                "`unrelated`, `ambiguous`, `unresolved`."),
            ),
            "exclusion_rule": (inferred("D-16"), "Rule that excluded it, e.g. `D-13`."),
            "exclusion_reason": (inferred("D-16"), "What that rule found."),
            "spam_burst": (inferred("D-13"), "Number of the spam burst it belongs to."),
            "repost_count": (inferred("D-44"), "Reposts linked to this mention."),
            "implied_references": (
                inferred("D-20"),
                "Phrases pointing at an unnamed rival; recorded, never counted.",
            ),
            "id_conflict": (
                inferred("D-10"),
                "True when another row has this ID with different content.",
            ),
            "sentiment": (
                inferred("D-30"),
                ("`positive`, `neutral`, `negative`, or `unlabelled` when no label could be "
                "assigned. Absent on mentions whose text is never counted."),
            ),
            "sentiment_source": (inferred("D-35"), "`model:<name>` that assigned the sentiment."),
            "sentiment_prompt": (inferred("D-35"), "Hash of the prompt that produced it."),
            "sentiment_reason": (inferred("D-35"), "The model's one-line reason."),
            "codes_status": (
                inferred("D-31"),
                ("`labelled`, `unlabelled`, or `not_applicable` (not negative, or not about the "
                "client)."),
            ),
            "label_overrides": (inferred("D-35"), "Client rules that changed the model's codes."),
        },
    ),
    "ComplaintCode": NodeType(
        "code",
        "One of the client's own complaint codes (D-31).",
        {
            "code": (EXTRACTED, "The code."),
            "name": (EXTRACTED, "Its name."),
            "includes": (EXTRACTED, "What the client says it covers."),
            "client_rule": (EXTRACTED, "The client's routing rule, verbatim."),
        },
    ),
    "Team": NodeType(
        "name",
        "A client team that owns complaint codes (D-34).",
        {"name": (EXTRACTED, "`owner_team` in the taxonomy.")},
    ),
    "Source": NodeType(
        "file",
        "A file of the data pack. Saved web pages keep their text.",
        {
            "file": (EXTRACTED, "Path relative to the data pack."),
            "kind": (EXTRACTED, "What the file is: an export, the catalogue, or a page folder."),
            "title": (EXTRACTED, "Page title."),
            "url": (EXTRACTED, "Where the page was captured from."),
            "captured_at": (EXTRACTED, "Capture date stated on the page."),
            "body": (EXTRACTED, "Page text."),
            "body_row": (EXTRACTED, "First line of `body` in the file, for `file:line` refs."),
        },
    ),
    "Observation": NodeType(
        "key",
        "A dated fact about a brand or product: a price, a shipping rule, a launch, an offer "
        "(D-50).",
        {
            "key": (EXTRACTED, "`<kind>:<file>:<row>`."),
            "kind": (
                EXTRACTED,
                "`price`, `free_shipping_threshold`, `launch` or `offer`.",
            ),
            "observed_at": (
                EXTRACTED,
                "Capture date of the source. Absent on the client's own catalogue prices.",
            ),
            "undated": (inferred("D-52"), "True when the source gives no capture date."),
            "stale": (inferred("D-52"), "True when older than the staleness limit at the as-of."),
            "text": (EXTRACTED, "The words in the source, for facts read from a page."),
            "value": (EXTRACTED, "The number: a price or a threshold."),
            "currency": (EXTRACTED, "Currency of `value`."),
            "region": (EXTRACTED, "Market the price applies to."),
            "url": (EXTRACTED, "Page the price was captured from."),
            "pack": (EXTRACTED, "Pack size as written, e.g. `6 x 200ml`."),
            "unit_count": (inferred("D-53"), "Units in the pack."),
            "unit_size": (inferred("D-53"), "Size of one unit."),
            "unit": (inferred("D-53"), "`g`, `kg`, `ml`, `l` or `bag`."),
            "unit_price": (inferred("D-53"), "Price per unit (per can, per bag, per pack)."),
            "price_per_100": (inferred("D-53"), "Price per 100 g or 100 ml."),
            "pattern": (inferred("D-50"), "Name of the page pattern that found the fact."),
        },
    ),
    "Ad": NodeType(
        "ad_id",
        "One ad from the public ad-library export.",
        {
            "ad_id": (EXTRACTED, "Ad ID."),
            "platform": (EXTRACTED, "Ad platform."),
            "first_seen": (EXTRACTED, "First date seen."),
            "last_seen": (EXTRACTED, "Last date seen."),
            "headline": (EXTRACTED, "Ad headline."),
            "offer": (EXTRACTED, "Offer text, if any."),
            "landing_url": (EXTRACTED, "Where the ad points."),
            "still_running": (inferred("D-54"), "True when last seen on the export's last day."),
        },
    ),
}

EDGES: dict[str, EdgeType] = {
    "POSTED_BY": EdgeType(("Mention",), ("Author",), EXTRACTED, "Who posted it.", {}),
    "MENTIONS": EdgeType(
        ("Mention",),
        ("Brand", "ProductLine", "UnrelatedEntity"),
        inferred("D-20 to D-24"),
        "What the mention is about. A mention naming two brands has an edge to each (D-25). "
        "Line edges exist only when the brand is named too (D-24).",
        {},
    ),
    "REPOST_OF": EdgeType(
        ("Mention",),
        ("Mention",),
        "either",
        "A repost and its original (D-11). Extracted for the export tool's flag, inferred for "
        "text markers.",
        {
            "basis": "`tool_flag`, `rt_text` or `repost_via_text`.",
            "quoted_handle": "The handle a text marker quotes.",
        },
    ),
    "DOUBLE_POST_OF": EdgeType(
        ("Mention",),
        ("Mention",),
        inferred("D-17"),
        "A repeat of the same author's own post on the same platform within a day.",
        {},
    ),
    "HAS_COMPLAINT": EdgeType(
        ("Mention",),
        ("ComplaintCode",),
        inferred("D-31 to D-35"),
        "A complaint code on a negative mention about the client. Carries the model or the "
        "override rule that assigned it.",
        {"prompt_hash": "Hash of the prompt.", "reason": "The model's one-line reason."},
    ),
    "OWNED_BY": EdgeType(("ComplaintCode",), ("Team",), EXTRACTED, "Routing (D-34).", {}),
    "OF_BRAND": EdgeType(
        ("ProductLine", "Product"),
        ("Brand",),
        "either",
        "Whose line or product it is. Extracted when a source states it, else inferred.",
        {},
    ),
    "IN_LINE": EdgeType(
        ("Product",),
        ("ProductLine",),
        "either",
        "The line a product belongs to. Extracted for the client catalogue, inferred from the "
        "product name for competitors.",
        {},
    ),
    "COMPETES_WITH": EdgeType(
        ("Brand",), ("Brand",), inferred("D-21"), "The client's tracked competitors.", {}
    ),
    "PUBLISHED_BY": EdgeType(
        ("Source",),
        ("Brand",),
        inferred("D-20, D-21"),
        "Whose page a saved web page is, read from its title and URL.",
        {},
    ),
    "ABOUT": EdgeType(
        ("Observation",),
        ("Brand", "ProductLine", "Product"),
        "either",
        "What an observation is a fact about.",
        {},
    ),
    "FROM": EdgeType(("Observation",), ("Source",), EXTRACTED, "The file it was read from.", {}),
    "RUN_BY": EdgeType(("Ad",), ("Brand",), EXTRACTED, "The advertiser.", {}),
    "PROMOTES": EdgeType(
        ("Ad",),
        ("ProductLine",),
        inferred("D-24"),
        "The line an ad's headline names.",
        {},
    ),
}


def inferred_properties(label: str, props: dict[str, object]) -> list[str]:
    """`name:rule` for each inferred property a node actually carries."""
    declared = NODES[label].properties
    return sorted(
        f"{name}:{declared[name][0].removeprefix('inferred:')}"
        for name in props
        if name in declared and declared[name][0].startswith("inferred:")
    )


def render_ontology() -> str:
    """docs/ontology.md, generated so it always matches what the builder may write."""
    out = [
        "# Ontology",
        "",
        ("Generated from `src/halyard/store/schema.py` by `halyard ontology`. Do not edit by "
        "hand: change the schema and regenerate. A test fails when the two differ."),
        "",
        "## Extracted and inferred",
        "",
        "- **Extracted**: copied from a source file as it stands.",
        ("- **Inferred**: computed from extracted values by a named rule in "
        "`docs/definitions.md`, or by a named model. Inferred does not mean guessed: every "
        "inferred value names what produced it."),
        "- **Config**: our own configuration under `config/<client>/`, such as brand keys.",
        "",
        "Every node carries:",
        "",
        *[f"- `{name}`: {meaning}" for name, meaning in NODE_PROVENANCE.items()],
        "",
        "Every edge carries:",
        "",
        *[f"- `{name}`: {meaning}" for name, meaning in EDGE_PROVENANCE.items()],
        "",
        "## Nodes",
        "",
    ]
    for label, node in NODES.items():
        out += [f"### {label}", "", f"{node.about} Key: `{node.key}`.", ""]
        out += ["| Property | How | Meaning |", "|---|---|---|"]
        out += [
            f"| `{name}` | {method.replace('inferred:', 'inferred, ')} | {meaning} |"
            for name, (method, meaning) in node.properties.items()
        ]
        out.append("")
    out += ["## Edges", "", "| Edge | From | To | How | Meaning |", "|---|---|---|---|---|"]
    for name, edge in EDGES.items():
        how = {"either": "extracted or inferred"}.get(
            edge.method, edge.method.replace("inferred:", "inferred, ")
        )
        extra = "".join(f" `{p}`: {m}" for p, m in edge.properties.items())
        out.append(
            f"| `{name}` | {', '.join(edge.source)} | {', '.join(edge.target)} | {how} | "
            f"{edge.about}{extra} |"
        )
    out += [
        "",
        "## Not in the graph, on purpose",
        "",
        ("- **Mention to Product edges.** Mentions rarely say which SKU, so they link to the "
        "line and never to a guessed product (ER-05)."),
        ("- **A `duplicate` status.** Byte-identical rows collapse into one mention whose "
        "`source_rows` lists every copy (D-10)."),
        ("- **Who an ad targets.** \"The other guys\" names nobody; comparing it with the client "
        "is an inference the agent must state (D-53)."),
        "",
    ]
    return "\n".join(out)
