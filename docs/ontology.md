# Ontology

Generated from `src/halyard/store/schema.py` by `halyard ontology`. Do not edit by hand: change the schema and regenerate. A test fails when the two differ.

## Extracted and inferred

- **Extracted**: copied from a source file as it stands.
- **Inferred**: computed from extracted values by a named rule in `docs/definitions.md`, or by a named model. Inferred does not mean guessed: every inferred value names what produced it.
- **Config**: our own configuration under `config/<client>/`, such as brand keys.

Every node carries:

- `source_file`: File the node was read from, relative to the data pack (or the config file).
- `source_ref`: `file:row` of the row or line it came from.
- `inferred_properties`: The node's inferred properties as `name:rule`. Every other property is extracted.

Every edge carries:

- `source_file`: File the evidence for the edge comes from.
- `source_ref`: The row (`file:row`) or the mention ID the edge rests on.
- `captured_at`: Capture date of that source. Absent when the source states none.
- `method`: `extracted` or `inferred`.
- `rule`: For inferred edges, the rule ID in docs/definitions.md.
- `model`: For edges a model decided, the model name (with `prompt_hash` and `reason`).
- `matched`: For edges decided by matching text, the exact string that matched.

## Nodes

### Brand

The client or a competitor. Key: `key`.

| Property | How | Meaning |
|---|---|---|
| `key` | config | Short identifier, e.g. `brewbird`. |
| `name` | config | Company name as the data pack writes it. |
| `is_client` | config | True for the client. |

### ProductLine

A range of a brand, e.g. Brewbird Nitro or Peak Instant. Key: `key`.

| Property | How | Meaning |
|---|---|---|
| `key` | config | `<brand key>:<line name>`. |
| `name` | config | Line name. |
| `sub_brand` | extracted | The client catalogue's `sub_brand` for this line. |

### Product

A client SKU or a competitor product. Key: `key`.

| Property | How | Meaning |
|---|---|---|
| `key` | extracted | The SKU, or `<brand key>:<product name>` for competitors. |
| `sku` | extracted | Client SKU. |
| `name` | extracted | Product name. |
| `aliases` | extracted | Customer nicknames from the client catalogue. |
| `launched` | extracted | Launch date in the client catalogue. |

### UnrelatedEntity

Something that shares a brand's name but is not the brand (D-22). Key: `key`.

| Property | How | Meaning |
|---|---|---|
| `key` | config | Short identifier. |
| `name` | config | What it is. |
| `collides_with` | config | Key of the brand whose name it shares. |

### Author

A public handle that posted at least one mention. Key: `handle`.

| Property | How | Meaning |
|---|---|---|
| `handle` | extracted | `author_handle` in the export. |
| `account_class` | inferred, D-13 | `person`, or `coupon_bot` for spam authors. |

### Mention

One post or review. Every mention in the export is kept, counted or not (D-16). Key: `mention_id`.

| Property | How | Meaning |
|---|---|---|
| `mention_id` | extracted | ID assigned by the listening tool. |
| `platform` | extracted | Where it was posted. |
| `posted_at` | extracted | Timestamp exactly as exported, offset included (D-01). |
| `text` | extracted | Post text as captured, never altered (D-12). |
| `likes` | extracted | Likes at capture time. |
| `url` | extracted | Link to the post. |
| `is_repost_of` | extracted | The export tool's repost flag, when set. |
| `source_rows` | extracted | Every row of the export holding this mention (D-10). |
| `date_ist` | inferred, D-01 | Local date of `posted_at` in the client timezone. |
| `week_ist` | inferred, D-02 | First day of the reporting week of `date_ist`. |
| `city` | inferred, D-26 | City named in a bracketed tag in the text. |
| `normalised_text` | inferred, D-12 | Matching key: the text without decoration. |
| `status` | inferred, D-15 | `genuine`, or why it is not a conversation: `repost`, `spam`, `double_post`, `unrelated`, `ambiguous`, `unresolved`. |
| `exclusion_rule` | inferred, D-16 | Rule that excluded it, e.g. `D-13`. |
| `exclusion_reason` | inferred, D-16 | What that rule found. |
| `spam_burst` | inferred, D-13 | Number of the spam burst it belongs to. |
| `repost_count` | inferred, D-44 | Reposts linked to this mention. |
| `implied_references` | inferred, D-20 | Phrases pointing at an unnamed rival; recorded, never counted. |
| `id_conflict` | inferred, D-10 | True when another row has this ID with different content. |
| `sentiment` | inferred, D-30 | `positive`, `neutral`, `negative`, or `unlabelled` when no label could be assigned. Absent on mentions whose text is never counted. |
| `sentiment_source` | inferred, D-35 | `model:<name>` that assigned the sentiment. |
| `sentiment_prompt` | inferred, D-35 | Hash of the prompt that produced it. |
| `sentiment_reason` | inferred, D-35 | The model's one-line reason. |
| `codes_status` | inferred, D-31 | `labelled`, `unlabelled`, or `not_applicable` (not negative, or not about the client). |
| `label_overrides` | inferred, D-35 | Client rules that changed the model's codes. |

### ComplaintCode

One of the client's own complaint codes (D-31). Key: `code`.

| Property | How | Meaning |
|---|---|---|
| `code` | extracted | The code. |
| `name` | extracted | Its name. |
| `includes` | extracted | What the client says it covers. |
| `client_rule` | extracted | The client's routing rule, verbatim. |

### Team

A client team that owns complaint codes (D-34). Key: `name`.

| Property | How | Meaning |
|---|---|---|
| `name` | extracted | `owner_team` in the taxonomy. |

### Source

A file of the data pack. Saved web pages keep their text. Key: `file`.

| Property | How | Meaning |
|---|---|---|
| `file` | extracted | Path relative to the data pack. |
| `kind` | extracted | What the file is: an export, the catalogue, or a page folder. |
| `title` | extracted | Page title. |
| `url` | extracted | Where the page was captured from. |
| `captured_at` | extracted | Capture date stated on the page. |
| `body` | extracted | Page text. |
| `body_row` | extracted | First line of `body` in the file, for `file:line` refs. |

### Observation

A dated fact about a brand or product: a price, a shipping rule, a launch, an offer (D-50). Key: `key`.

| Property | How | Meaning |
|---|---|---|
| `key` | extracted | `<kind>:<file>:<row>`. |
| `kind` | extracted | `price`, `free_shipping_threshold`, `launch` or `offer`. |
| `observed_at` | extracted | Capture date of the source. Absent on the client's own catalogue prices. |
| `undated` | inferred, D-52 | True when the source gives no capture date. |
| `stale` | inferred, D-52 | True when older than the staleness limit at the as-of. |
| `text` | extracted | The words in the source, for facts read from a page. |
| `value` | extracted | The number: a price or a threshold. |
| `currency` | extracted | Currency of `value`. |
| `region` | extracted | Market the price applies to. |
| `url` | extracted | Page the price was captured from. |
| `pack` | extracted | Pack size as written, e.g. `6 x 200ml`. |
| `unit_count` | inferred, D-53 | Units in the pack. |
| `unit_size` | inferred, D-53 | Size of one unit. |
| `unit` | inferred, D-53 | `g`, `kg`, `ml`, `l` or `bag`. |
| `unit_price` | inferred, D-53 | Price per unit (per can, per bag, per pack). |
| `price_per_100` | inferred, D-53 | Price per 100 g or 100 ml. |
| `pattern` | inferred, D-50 | Name of the page pattern that found the fact. |

### Ad

One ad from the public ad-library export. Key: `ad_id`.

| Property | How | Meaning |
|---|---|---|
| `ad_id` | extracted | Ad ID. |
| `platform` | extracted | Ad platform. |
| `first_seen` | extracted | First date seen. |
| `last_seen` | extracted | Last date seen. |
| `headline` | extracted | Ad headline. |
| `offer` | extracted | Offer text, if any. |
| `landing_url` | extracted | Where the ad points. |
| `still_running` | inferred, D-54 | True when last seen on the export's last day. |

## Edges

| Edge | From | To | How | Meaning |
|---|---|---|---|---|
| `POSTED_BY` | Mention | Author | extracted | Who posted it. |
| `MENTIONS` | Mention | Brand, ProductLine, UnrelatedEntity | inferred, D-20 to D-24 | What the mention is about. A mention naming two brands has an edge to each (D-25). Line edges exist only when the brand is named too (D-24). |
| `REPOST_OF` | Mention | Mention | extracted or inferred | A repost and its original (D-11). Extracted for the export tool's flag, inferred for text markers. `basis`: `tool_flag`, `rt_text` or `repost_via_text`. `quoted_handle`: The handle a text marker quotes. |
| `DOUBLE_POST_OF` | Mention | Mention | inferred, D-17 | A repeat of the same author's own post on the same platform within a day. |
| `HAS_COMPLAINT` | Mention | ComplaintCode | inferred, D-31 to D-35 | A complaint code on a negative mention about the client. Carries the model or the override rule that assigned it. `prompt_hash`: Hash of the prompt. `reason`: The model's one-line reason. |
| `OWNED_BY` | ComplaintCode | Team | extracted | Routing (D-34). |
| `OF_BRAND` | ProductLine, Product | Brand | extracted or inferred | Whose line or product it is. Extracted when a source states it, else inferred. |
| `IN_LINE` | Product | ProductLine | extracted or inferred | The line a product belongs to. Extracted for the client catalogue, inferred from the product name for competitors. |
| `COMPETES_WITH` | Brand | Brand | inferred, D-21 | The client's tracked competitors. |
| `PUBLISHED_BY` | Source | Brand | inferred, D-20, D-21 | Whose page a saved web page is, read from its title and URL. |
| `ABOUT` | Observation | Brand, ProductLine, Product | extracted or inferred | What an observation is a fact about. |
| `FROM` | Observation | Source | extracted | The file it was read from. |
| `RUN_BY` | Ad | Brand | extracted | The advertiser. |
| `PROMOTES` | Ad | ProductLine | inferred, D-24 | The line an ad's headline names. |

## Not in the graph, on purpose

- **Mention to Product edges.** Mentions rarely say which SKU, so they link to the line and never to a guessed product (ER-05).
- **A `duplicate` status.** Byte-identical rows collapse into one mention whose `source_rows` lists every copy (D-10).
- **Who an ad targets.** "The other guys" names nobody; comparing it with the client is an inference the agent must state (D-53).
