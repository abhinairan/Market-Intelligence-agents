# Ontology note

Why the graph is shaped the way it is. The full reference (every node, edge and property, with
how each is set) is [`ontology.md`](ontology.md), generated from `src/halyard/store/schema.py`.
What was merged and kept apart is in [`er-log.md`](er-log.md). Rule IDs (D-xx) are in
[`definitions.md`](definitions.md).

The built graph has 3,889 nodes and 5,384 edges, and two builds give the same graph:

| Nodes | | Edges | |
|---|---|---|---|
| Mention | 1,904 | MENTIONS | 3,100 |
| Author | 1,899 | POSTED_BY | 1,904 |
| Observation | 20 | HAS_COMPLAINT | 190 |
| Ad | 19 | REPOST_OF | 70 |
| Source | 13 | ABOUT, FROM | 21, 20 |
| Product | 12 | RUN_BY, PROMOTES | 19, 16 |
| ProductLine, ComplaintCode, Team | 6, 6, 5 | OF_BRAND, IN_LINE | 18, 9 |
| Brand, UnrelatedEntity | 4, 1 | PUBLISHED_BY, OWNED_BY, COMPETES_WITH | 8, 6, 3 |

## Start from the questions

The ontology was designed from what the twelve questions and the Monday pulse need, not from a
generic social-listening template.

| What is asked | What it needs from the graph | The shape that gives it |
|---|---|---|
| Unique, genuine conversations by product line (Q1) | Each post once, with a reason when it does not count; lines kept apart from brands | `Mention` with `status` and `exclusion_reason`; `MENTIONS` to `Brand` and to `ProductLine` |
| Nitro sentiment week by week, against the brand (Q2) | A label per post, a reporting week per post, line vs brand | `sentiment` and `week_ist` on `Mention` |
| Top complaints in the client's codes, with examples (Q3) | The client's six codes, never our own categories | `ComplaintCode` nodes from the client taxonomy; `HAS_COMPLAINT` edges |
| What the brand-level numbers hide (Q4) | Codes by line, and who each code is routed to | `HAS_COMPLAINT` plus `ComplaintCode -OWNED_BY-> Team` |
| What happened on 22 September (Q5) | Spam, reposts and unrelated posts kept and explained, not deleted | Excluded mentions stay as nodes; `Author.account_class`; `REPOST_OF` |
| Subscription cancellations (Q6) | Knowing that the data does not hold them | No subscription or customer nodes; `coverage` says so |
| Saltmarsh's launch, price per can, "half the price" (Q7, Q8) | Dated prices with market, currency and pack size; the ads behind the claim | `Observation` with `region`, `currency`, unit fields; `Ad` |
| Share of voice and how it was counted (Q9) | The same counting rules for all four brands, with sub-brands resolved | `Brand`, `COMPETES_WITH`, Peak Instant as a Bluepeak line (ER-01) |
| Shipping changes and when (Q10) | Two dated facts about the same thing, so a change has a date range | `Observation` per capture date, never overwritten |
| Filterhaus wholesale prices (Q11) | Knowing that the source is gated and not in the data | No such observation; `coverage` and D-62 |
| Did the launch cause the fall (Q12) | Whether complaining posts name the competitor, and Nitro volume by week | `MENTIONS` edges to both brands on one post (D-25) |
| "Where did this number come from?" (Dev) | Every count back to rows | Provenance on every node and edge; `trace` |

## The choices, and why

**1. The post is the unit, and nothing is deleted.** Every one of the 1,904 unique mentions is
a node, counted or not. Spam, reposts, unrelated and ambiguous posts carry a `status` and the
rule that excluded them (D-16). Dev's complaint about the last vendor was that he could not see
how posts became a number. Keeping exclusions in the graph is what lets the agents say "987
conversations, after removing 84 spam, 70 reposts, 42 taproom and 22 pop-up posts" and point
at each one. It is also how Q5 explains a 132-mention day as spam rather than news.
Byte-identical export rows collapse into one mention that lists every source row (D-10).

**2. Brands and product lines are separate nodes.** Q1 counts by line, Q2 compares a line with
its brand, and Q4 is about a line problem hidden at brand level. That needs both levels.
A mention links to a line only when the brand is named too (D-24), because "nitro" alone in
this pack always means Saltmarsh Nitro (ER-13). A Brewbird post that names no line stays
brand-level rather than being assigned a line by guessing. Mentions never link to a `Product`
(SKU): posts rarely say which pack, and a guessed SKU would be a fabricated fact (ER-05).

**3. A name collision is a node, not a filter.** The Pune taproom called "Brewbird" is an
`UnrelatedEntity` with its own `MENTIONS` edges. A silent filter would hide 45 posts; a node
makes the exclusion visible and answers "how is Brewbird's beer?" with the reason.

**4. The client's codes and owner teams are nodes.** Farah's problem is routing: swollen Nitro
cans filed as packaging go to Logistics, and QA hears three weeks late. With
`ComplaintCode -OWNED_BY-> Team` taken verbatim from the client's taxonomy, routing is a
lookup in the graph, and a negative post with no matching code gets no code rather than a new
category (D-31). The TST-over-PKG rule for cans (D-32) is applied by code after the model and
recorded on the edge as an override.

**5. Sentiment is a property of the post; complaint codes are edges.** A post has exactly one
sentiment, so it sits on `Mention` with the model, prompt hash and reason that set it (D-35).
A post can carry several codes, and each code leads somewhere (its team), so codes are edges,
each with its own provenance. Sentiment is judged on the whole text; a post naming two brands
counts for each (D-25) with the same label.

**6. Competitor facts are dated observations, not product properties.** A price stored on a
`Product` would be overwritten by the next capture and lose its date. Instead each price,
shipping threshold, launch and offer is an `Observation` with the capture date of its source
(D-50), `ABOUT` the brand, line or product, and `FROM` the page it was read from. That is what
makes three answers possible:
- **Change dates (Q10):** Bluepeak's free-shipping threshold is two observations,
  499 (page captured 3 Nov 2025) and 799 (page captured 20 Sep 2026), and a customer post on
  18 Aug 2026 (M10049) is earlier evidence of the new value. So the change is dated "between 3 Nov 2025 and 18 Aug 2026", a range
  rather than a guess (D-51).
- **Staleness:** a fact older than 90 days is history, never "current" (D-52).
- **Like with like (Q7, Q8):** region, currency, pack and unit price are on the observation,
  so an INR price is never compared with an AED one and cans are compared per can (D-53).

**7. Ads are their own nodes.** An ad has a run (first and last seen), an advertiser and a line
it promotes. "Still running as of 4 Oct" (D-54) and "14 Saltmarsh Nitro ads from 15 Sep" are
facts about ads, not about prices. Ads corroborate a launch date but never set it (D-55).

**8. Sources keep their text.** Saved pages are `Source` nodes with their body and the line it
starts on. A page fact or a coverage answer cites `file:line` (e.g. the FAQ line saying
subscriptions cover Classic and Origins), and `trace` resolves any ID back to the row or line.

**9. Authors are nodes.** The 22 Sep spam is 84 posts from 84 handles in three handle families
in three hours (D-13). That is a pattern across authors, and `account_class = coupon_bot` is
set on the author. Author nodes also let every count of conversations come with a count of
distinct people (987 conversations from 984 authors).

**10. Time is a property, not a node.** `date_ist` and `week_ist` are derived from the
timestamp exactly as exported, in IST, never via UTC (D-01, D-02). Every question asks for a
window or a week, which is a filter, so time nodes would add hops and no answers.

## Provenance

Every edge carries `source_file`, `source_ref` (the `file:row`, the page line or the mention ID),
`captured_at` when the source states one, and `method` = `extracted` or `inferred`. An inferred
edge must name its rule (D-xx) or the model and prompt hash; the builder refuses one that does
not. Nodes carry the same `source_file` and `source_ref`, and `inferred_properties` lists each
derived property with its rule, so `week_ist` or a unit price is as traceable as an edge.

Of the 5,384 edges, 2,026 are extracted and 3,358 inferred. Most inferred edges are `MENTIONS`
(3,100, each naming D-20 to D-24) and `HAS_COMPLAINT` (190, each naming its model or override).
`REPOST_OF` is extracted for the 38 reposts flagged by the export tool and inferred for the 32
found by text markers.

The schema is defined once, in `schema.py`. The builder refuses any node, edge or property
outside it, and a test fails if `ontology.md` and the schema differ.

## Where the counting happens

The graph holds facts; the counting rules live in the query tools. The tools read the graph
through five plain reads (mentions, observations, ads, nodes by label, one node) and count in
Python. That keeps each D-rule in one place, tested on an in-memory store and on Neo4j, and
means another store only has to supply those five reads. The agents never see the raw CSVs or
write Cypher.

## Left out on purpose

- **Subscriptions, orders, customers, revenue.** None are in the data pack. Modelling them
  empty would invite an answer; leaving them out lets `coverage` say plainly what is missing
  (Q6, Dev's cancellation question). This needs a data connector, not a graph change.
- **Mention to Product edges.** See choice 2 (ER-05).
- **A `duplicate` status.** Identical rows are one mention with several source rows (D-10).
- **Who an ad targets.** "The other guys" names nobody; reading it as Brewbird is an inference
  the agent must state, not an edge (D-53, ER-12).
- **Implied references.** "The other nitro cans" is recorded on the mention
  (`implied_references`) and never counted for any brand (D-20).
