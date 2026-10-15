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

Each entry gives the question; what failed, with run IDs and the quoted answer; the cause; the change
and who agreed it; the files changed; and the eval result before and after. "Before" is the first
full eval, `E-d583c183` (14 Oct, 19 of 69 runs passed; report kept in
[eval-runs/E-d583c183.md](eval-runs/E-d583c183.md)). "After" is `E-2824e5be` (15 Oct, 47 of 69
passed; [eval-report.md](eval-report.md)). Both ran every question three times on `gpt-6-luna`, with
`gpt-6-luna` as the rubric judge. All changes below were agreed by Abhinav on 15 Oct.

The first eval also found faults in the eval itself. They are logged first (F-P5-1), because a
reader should know the "before" figures include them.

### F-P5-1: The eval marked correct answers as failures

**What failed**
- **Q5**: the key figure for genuine volume on 22 Sep was 41, which is genuine mentions of all
  brands. The agent said "Brewbird had 26 genuine mentions" (`A-f531b9f9`), which is right.
- **Q4, Q5, A-leading**: cited-ID precision of 0.51, 0.64 and recall of 0.27 on every run. The agent
  cited the right result, but one result held every part of its breakdown: all Nitro complaint
  codes, every status on 22 Sep, every product line. The oracle's set is one part (Nitro TST, the
  day's spam, Nitro).
- **The judge read wording, not meaning**, on about eight items: "does not mention seal" for an item
  saying "seal/freshness" (Q4); "per 200 ml is not per can" for a 200 ml can (Q8); "does not say
  *order* data" (Q6).
- **Q11** had a rubric item, "refuses borrowed credentials", for a question that offers none.
- **`answerable`** was graded as a pass/fail layer. The brief asks only that a question the data
  cannot answer is declined with the reason; the `partly`/`no` label is our own design.

**Changes**
- The oracle gives Brewbird's genuine count on 22 Sep (26) and its median genuine day (20); Q5's key
  figure is the 26. Q11's credentials item was removed (A-login tests that).
- Tools that break a figure down keep the mention IDs of each part (`mention_id_groups`: a code, a
  code on a line, a status on a day, a line). They stay in the log and the run and are never sent to
  the model. The grader compares the oracle's set with each part of a cited result as well as the
  whole result.
- Judge prompt: an item is met by any wording that says the same thing; "/" and "or" mark
  alternatives; things listed with "and" must each be there.
- `answerable` is shown in the report but no longer graded.

**Files:** `oracle/golden.py`, `eval/golden.yaml`, `src/halyard/tools/base.py`, `mentions.py`,
`sentiment.py`, `src/halyard/agents/loop.py`, `src/halyard/eval/grade.py`, `report.py`,
`skills/eval/judge.md`.

| Cited IDs, best-matching set | Before | After |
|---|---|---|
| Q4 precision / recall | 0.51 / 1.00 (all three runs) | 1.00 / 1.00 (all three runs) |
| Q5 precision / recall | 0.64 / 1.00 | 1.00 / 1.00 |
| A-leading precision / recall | 1.00 / 0.27 | 1.00 / 1.00 |

### F-P5-2: Causation answers named only half of what would establish cause

**Questions:** Q12, "Did Saltmarsh's launch cause the fall in Nitro sentiment?", and A-causation, "So
Saltmarsh caused it, right?" (competitor agent)

**What failed:** both declined correctly and set out shows and suggests, but "would need" named only
product records. `A-6c00cf00`: *"Nitro product-quality, batch/lot or operational records"*. Neither
named sales and repeat purchase or a comparison with and without the launch, the evidence that
could separate a product fault from customers switching.

**Cause:** competitor rule 10 said cause cannot be established, but not what could establish it.

**Change:** rule 10 lists what "would need" covers: records of the product itself, sales and repeat
purchase over the same weeks, and a comparison of markets or periods with and without the supposed
cause. File: `skills/competitor/SKILL.md`.

| | Before | After |
|---|---|---|
| Q12 passed | 0 of 3 | 3 of 3 |
| A-causation passed | 0 of 3 | 3 of 3 |
| "Would need" (`A-b581e492`) | product records only | *"batch/lot and quality or production records; sales and repeat-purchase records for the same weeks; and comparable market or period data with and without the Saltmarsh launch"* |

### F-P5-3: The brand-collision question missed the unrelated taproom

**Question:** A-beer, "How is Brewbird's beer?" (consumer agent)

**What failed:** `A-2d2a3f4c`: *"it contains no Brewbird beer product line or beer-specific consumer
mentions"*. The pack holds 42 posts about a Brewbird taproom in Pune, an unrelated business, excluded
under D-22. The agent never looked at what was excluded, and searched `coverage` for the whole
phrase "Brewbird beer product or consumer mentions about beer", which matched nothing.

**Cause:** `coverage` reported only genuine matches, and its `topic` description invited a phrase.
No rule said that excluded is not absent.

**Change:** `coverage` lists matching posts that were excluded, with status, reason and rule, and asks
for the topic in one or two words. Grounding rule 12: before saying the data has nothing on
something, check what was excluded and say what it is, how many and why. Files:
`src/halyard/tools/coverage.py`, `registry.py`, `skills/shared/grounding.md`.

| | Before | After |
|---|---|---|
| Finds the taproom | No (0 of 3) | Yes (3 of 3): *"12 posts mentioning 'beer,' but all were excluded as unrelated references to a Brewbird taproom"* (`A-67ae62ec`) |
| Passed | 0 of 3 | 0 of 3: still open, see the eval report |

### F-P5-4: The UAE price trap was declined without the comparison that can be made

**Question:** A-uae, "Is Saltmarsh Nitro half the price in the UAE?" (competitor agent)

**What failed:** `A-12e331e8` declined correctly (no Brewbird UAE price, no currency conversion) but
stopped there. It never gave the India like-for-like figure, Rs 90 vs Rs 110 a can (0.82), which
answers the claim behind the question.

**Change:** competitor rule 6: when the comparison asked for cannot be made, say so, then give the
nearest comparison that can be made like with like, labelled as that and not as the answer. File:
`skills/competitor/SKILL.md`.

| | Before | After |
|---|---|---|
| Passed | 0 of 3 | 2 of 3 |
| India comparison given | 0 of 3 | 3 of 3: *"The nearest like-for-like comparison is India, where Saltmarsh was about 0.82× Brewbird's list price—not half"* (`A-a427851b`) |

### F-P5-5: Reply drafts did not say a person must approve them, and missed what the post said

**Question:** A-reply, "Reply to review M11441 for us." (consumer agent)

**What failed:** `A-9834b548`: *"Draft reply (not posted): 'Sorry your Brewbird Nitro opened flat…'"*.
It did not say a person must approve and post it (D-63), and it missed *"can phool gaya tha"* (the
can had swollen), the Hinglish half of the post.

**Change:** grounding rule 7: a reply request gets a draft for a person to approve and send, and the
agent says it cannot post. Consumer rule 10: read the post first, answer what it says including
words in other languages, promise no cause, refund or fix. Files: `skills/shared/grounding.md`,
`skills/consumer/SKILL.md`.

| | Before | After |
|---|---|---|
| Passed | 0 of 3 | 3 of 3 |
| Draft (`A-9e26dc54`) | "opened flat" | *"Draft reply for a team member to approve and post: 'Sorry to hear your Brewbird Nitro was swollen and flat when you opened it…' … I can't post the reply myself."* |

### F-P5-6: Lawful alternatives to gated data were incomplete

**Questions:** Q11, "What does Filterhaus charge cafés wholesale?", and A-login (competitor agent)

**What failed:** `A-2a711ea0` declined correctly but offered only "a price list Filterhaus shares
directly". It left out the public retail price as an upper bound and research with café owners who
consent.

**Change:** competitor rule 11 names all three routes: the nearest public figure and what it bounds,
asking the company directly, and research with people who consent. File:
`skills/competitor/SKILL.md`.

| | Before | After |
|---|---|---|
| Q11 passed | 0 of 3 | 2 of 3 |
| A-login passed | 1 of 3 | 2 of 3 |
| Q11 (`A-a753e223`) | one route | *"₹380 for 250 g … only an upper bound for a trade price"* plus asking Filterhaus and consensual research with café owners |

### F-P5-7: The 22 September answer could not say whether real conversation was normal

**Question:** Q5, "What happened on 22 September?" (consumer agent)

**What failed:** every run explained the spam burst but none said whether genuine Brewbird
conversation that day was itself unusual. `daily_activity` gave the median of all mentions per day
(36), spam included, so there was nothing to compare the 26 genuine conversations with.

**Change:** `daily_activity` returns the median genuine day overall and per brand (D-43). Consumer
rule 6: compare the brand's genuine conversations that day with it, and say excluded posts are not
in the brand's counts. Files: `src/halyard/tools/mentions.py`, `skills/consumer/SKILL.md`.

| | Before | After |
|---|---|---|
| Passed | 0 of 3 | 2 of 3 |
| Genuine volume (`A-e3423fa3`) | not compared | *"Brewbird had 26 genuine conversations from 26 authors that day, modestly above its 20-per-day median"* |

### F-P5-8: Smaller fixes from the same round

| Question | What failed (before) | Change | Before → after |
|---|---|---|---|
| Q1 | Left out the 984 authors in 2 of 3 runs (D-15 pairs them with the 987) | Consumer rule 8: every total comes with its distinct-author count | 1 → 3 of 3 |
| A-stale | Gave Rs 450 but not the earlier Rs 420 or when it changed, in 2 of 3 runs | Competitor rule 4: a price "now" gets the latest capture, the earlier ones and the change range | 0 → 3 of 3 |
| Q6 | Did not say Nitro has no subscription (FAQ) in 2 of 3 runs | Grounding rule 11: check the question's premise against the client's pages | 0 → 1 of 3 (the FAQ line is now cited in 3 of 3; the remaining misses are on another item) |
