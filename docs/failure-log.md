# Failure log

Every failure we agreed to fix, with its cause, the change, and the answer before and after. Each
fix was proposed after a live run and agreed before it was made.

- **Found in manual review during P4** covers failures found by reading agent answers against the
  forensics figures, before the eval existed.
- **Found by the eval (P5)** covers failures the eval runner flags against the independent oracle.

Run IDs (`A-...`) name agent runs. Their transcripts are in `outputs/runs/` on the machine that ran
them; that folder is not committed, so the quotes below are copied from the transcripts. Any result
ID (`R-...`) or mention ID in a quote can be traced with `halyard trace <id>`. Costs are on
`gpt-6-luna` at $0.10 per million input tokens and $0.50 per million output tokens.

---

## Found in manual review during P4

### F-P4-1: Q12 missed the strongest evidence against causation, and read 200 posts to look for it

**Date:** 14 Oct 2026
**Question:** Q12, "Did Saltmarsh's launch cause the fall in Nitro sentiment?" (competitor agent)

**What failed** (run `A-2c9c5f0e`)
- The answer was right not to claim cause, but it missed the two facts that count most against it:
  none of the negative Nitro posts names Saltmarsh, and Nitro's conversation volume stayed flat at
  30 a week through the launch. Both are in the data and in the forensics.
- It did not set out shows, suggests and would need as separate parts (D-61), which the brief grades.
- It marked the question `partly` answerable, though whether the launch caused the fall cannot be
  established from this data.
- It read 200 mentions with `get_mentions` (limit 100, twice) to look for patterns: 70,667 input
  tokens and $0.0080, the most expensive question in the set.

**Cause**
- `count_mentions` grouped by brand returned only `brewbird: 211`. Brands with no matches were left
  out, so "Saltmarsh: 0" was invisible. In a later run the agent saw the result and still hedged:
  "it only shows no Saltmarsh-tagged group in this result".
- The skill told the agent to look at the client's own data, but not to test a pattern with counts.
  `get_mentions` had no page size limit and no paging.
- The skill checked "the client's volume". The agent read that as the whole brand (132 to 152 a week),
  which does not bear on the question, instead of Nitro's own volume.
- Nothing said a question about cause is `answerable: no` when the data cannot establish it.

**Changes** (agreed by Abhinav, 14 Oct, over three rounds)
- `count_mentions` lists every brand, line, complaint code and week, with 0 where nothing matched
  (`src/halyard/tools/mentions.py`).
- `get_mentions` returns at most 50 rows a call and pages with `offset` / `next_offset`
  (`tools.get_mentions_max_rows` in `config/brewbird/client.yaml`).
- Both agent skills: test a pattern with counts and read posts only for examples. Competitor skill
  rule 10: test a causal link with counts (whether the client's complaints name the competitor, and
  whether the line in question changed volume), and a cause question is `answerable: no`.
- Output format: a cause question sets out **Shows**, **Suggests** and **Would need**
  (`skills/shared/answer_format.md`). Grounding rule 5 says the same about `answerable`.

**Before and after**

| | Before (`A-2c9c5f0e`) | After (`A-8ca5fd4d`) |
|---|---|---|
| `answerable` | `partly` | `no` |
| Shows / Suggests / Would need | Not set out | Three labelled parts |
| Posts naming Saltmarsh | Not mentioned | "No Brewbird Nitro mentions named Saltmarsh in the observation window." |
| Nitro volume | Not mentioned | "Nitro mention volume stayed around 30–31 per week" |
| Tool calls / input tokens / cost | 7 / 70,667 / $0.0080 | 7 / 22,046 / $0.0030 |

The full run after all P4 changes (14 Oct) kept both facts: "none of the 211 Brewbird Nitro
conversations also matched Saltmarsh".

### F-P4-2: Citations to a saved page pointed at the page, not the sentence

**Date:** 14 Oct 2026
**Questions:** the subscription questions (consumer agent), and any answer citing a page found by `coverage`

**What failed** (run `A-548ccf37`)
- The answer quoted the FAQ ("monthly subscriptions are available on Classic and Origins") and cited
  `brand_site/faq.md:2`. Line 2 of that file is "Captured 2026-09-01 from brewbird.example/faq". The
  sentence is on line 6.
- The citation check passed, because a tool really had returned that reference. But a reviewer
  tracing the claim would land on the wrong line, and the brief judges whether every claim traces
  back to its row.

**Cause**
- `coverage` searches page text stored on each `Source` node, but it returned the page's own
  reference (the line holding its capture date) for every line it matched.
- An audit of every tool's references found one more case: the graph edge recording that Bluepeak's
  own brands page names Peak Instant (ER-01) also cited the capture line. Every other reference (CSV
  rows, and page facts such as prices, shipping and launches) already pointed at the right line.

**Changes** (agreed by Abhinav, 14 Oct)
- `Source` nodes keep `body_row`, the file line where the page text starts (`src/halyard/store/schema.py`,
  `src/halyard/ingest/graph.py`).
- `coverage` returns each matched line with its own `file:line` reference (`src/halyard/tools/coverage.py`,
  `src/halyard/tools/sources.py`). The Peak Instant edge cites the line that names it.
- `trace` resolves any `file:line` to the page line and every node read from that row
  (`src/halyard/tools/trace.py`).
- A test traces every reference every tool returns, and fails if any points at a page's capture line
  (`tests/test_tools_trace.py`).

**Before and after**

| | Before (`A-548ccf37`) | After (`A-2a04dea5`) |
|---|---|---|
| Reference cited for the FAQ sentence | `brand_site/faq.md:2` (the capture line) | `brand_site/faq.md:6` (the sentence) |
| `halyard trace` on that reference | Not resolvable | The FAQ line, its capture date and the page |

The graph's node and edge counts did not change (3,889 / 5,384).

### F-P4-3: Q4 put weekly complaint counts against the wrong weeks

**Date:** 14 Oct 2026
**Question:** Q4, "Is anything going wrong that the brand-level numbers are hiding?" (consumer agent)

**What failed** (run `A-0cfd2134`)
- The answer's table read: "Nitro TST complaints | 0 → 7 → 9 → 13 per week, from 31 Aug through
  28 Sep". That is four numbers for five weeks, so a reader would date the first 7 to the week of
  7 Sep. The real counts are 0 in each of the four weeks to 7 Sep, then 7, 9 and 13 in the weeks of
  14, 21 and 28 Sep.
- Every figure was correct and every citation valid, so the citation check could not catch it. Only
  the reading was wrong.

**Cause**
- `count_mentions` grouped by week returned only weeks with at least one match (`14 Sep: 7`,
  `21 Sep: 9`, `28 Sep: 13`). The empty weeks were missing, which invited the agent to fill in the
  start of the series itself.
- The output format did not ask for each weekly value to carry its week.

**Changes** (agreed by Abhinav, 14 Oct)
- Output format: "When giving a figure per week, label each value with its week (a table, or 'week of
  14 Sep: 7'), never a bare sequence of numbers." (`skills/shared/answer_format.md`)
- The zero-groups change in F-P4-1 also covers weeks, so every week in the window is listed.

**Before and after**

| | Before (`A-0cfd2134`) | After (`A-742abf09`) |
|---|---|---|
| Nitro TST by week | "0 → 7 → 9 → 13 per week, from 31 Aug through 28 Sep" | "rose from none in the first four weeks to 7, 9 and 13 in the final three" |

### F-P4-4: The answer on subscriptions used the lines' overall sentiment as the reaction to subscriptions

**Date:** 14 Oct 2026
**Question:** adversarial A-subscription-reaction, "How are consumers reacting to our subscription
products?" (consumer agent)

**What failed** (run `A-2a04dea5`)
- The answer opened: "Reactions are mostly positive for the two lines the FAQ says are available by
  monthly subscription—Classic and Origins—but there is a clear billing complaint to address. Across
  17 Aug–4 Oct 2026, Classic had 101 positive, 88 neutral and 57 negative conversations; Origins had
  144 positive, 43 neutral and 16 negative."
- Those figures are the overall sentiment of every Classic and Origins conversation, most of which
  are not about subscriptions. Every one of the 17 conversations that are about subscriptions is a
  complaint (code SUB, owned by Growth). The answer stood in a broader figure for the thing asked
  about, and led with it, so its headline was the opposite of what the data shows.
- Each figure was correct and cited, so the citation check passed. Only the reasoning was wrong.
- It took 8 tool calls in 5 turns (42,029 input tokens, $0.0054), the most expensive consumer answer.

**Cause**
- The skill tells the agent to look below the brand level and to answer what public conversation can
  show. Having found in the FAQ which lines offer subscriptions, it took those lines' sentiment as a
  measure of the subscription. No rule said that a product's conversation is not a reaction to one
  of its plans or features.

**Change** (agreed by Abhinav, 14 Oct)
- Grounding rule 10, shared by every agent (`skills/shared/grounding.md`): "Answer about the thing
  asked about. Conversation about a product is not a reaction to one of its plans, features or
  services; only posts about that plan, feature or service are. Never stand in figures for something
  broader or nearby."
- The adversarial expectation for this question (`eval/adversarial.yaml`) says the answer must not use
  the lines' overall sentiment as the reaction to subscriptions.

**Before and after**

| | Before (`A-2a04dea5`) | After (`A-0a806d2f`) |
|---|---|---|
| Headline | "Reactions are mostly positive for the two lines ... Classic and Origins" | "The public subscription-related feedback is negative: all 17 genuine Brewbird conversations carrying the SUB code were negative, from 17 distinct authors." |
| Figures used | Classic and Origins sentiment, all conversations | The 17 SUB conversations, with two quoted examples and their owner team (Growth) |
| Limits stated | Account records needed for totals | Same, plus that the posts do not show which line drives the complaints |
| Tool calls / input tokens / cost | 8 / 42,029 / $0.0054 | 4 / 17,649 / $0.0023 |

Run `A-2a04dea5` is also the "after" run in F-P4-2: it cited the FAQ line correctly while drawing the
wrong conclusion from it.

---

## Found by the eval (P5)

None yet. Each entry follows the same layout: the question; what failed, with run IDs and the quoted
answer; the cause; the change and who agreed it; the files changed; and the eval result before and
after.
