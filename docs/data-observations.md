# Brewbird data pack: forensics and observations

Pass done 2026-10-11 with plain pandas, no model calls. Data unpacked at `/mnt/project-files/brewbird/data-pack/fde-v4-data-pack/`. Throwaway scripts used for every number below are in `notes/forensics/` (`labels.py` is the hand-labelled template table). All figures are **first-pass and rough**: they rest on my own hand labels and definitions, which the build should re-derive and write down properly.

---

## 1. The six things that most change the build

1. **The data is templated.** 1,904 unique mentions collapse to **108 text templates** once you strip the decorations the generator adds (prefixes `PSA:`, `ngl`, `honestly`, `update:`, `ok so`; suffixes like `(Delhi)`, `lol`, `!!`, `#coffee`, emoji). So a rules classifier can reach ~100% on this pack, and so can an LLM that labels 108 strings once for pennies. The real test is therefore not classifier accuracy. It is whether the definitions (genuine, repost, spam, TST, week, unit price) are right, written down and traceable, and whether the system generalises to the unseen questions and adversarial inputs.
2. **The one finding is Nitro seal and freshness (TST), and the brand numbers hide it.** Nitro TST complaints go **0, 0, 0, 0, then 7, 9, 13** across the seven weeks, starting 14 Sep. Nitro negative share goes from about 7% to **63%** in the week of 28 Sep, while Nitro *volume* stays flat at 30 a week. Brand net sentiment only drifts from 0.45 to 0.31, and **brand without Nitro is flat**. A tool that counted the 22 Sep spam as positive would even show brand sentiment *improving* that week (0.53, the best of the period). This is QA's code, Farah's "three weeks late" complaint, and Ishita's one finding.
3. **22 September is a coupon-spam burst, not a real event.** 84 posts from three bot families (`coupon_kart_*`, `lootbazaar_*`, `dealsloot_*`) between 02:00 and 05:00 IST, four copy-paste texts pushing code `BB50` for "50% off" with a bit.ly link. Without them 22 Sep has 48 organic mentions against a median of 36. Nothing in the pack says BB50 is a real Brewbird promotion. 22 of the 84 name Nitro, so they also pollute the Nitro line if not removed.
4. **Naive counting reproduces the vendor's 70% share of voice.** Plain string matching over the last four weeks gives Brewbird **66%**. The clean count gives **56%**, because it drops the spam, the "Brewbird" taproom in Pune, and reposts, and because it credits **Peak Instant to Bluepeak** (100 mentions in four weeks that string matching gives to nobody). That contrast is Dev's answer, almost ready-made.
5. **Snapshot dates are not event dates.** Bluepeak's free-shipping threshold went from Rs 499 to Rs 799, but the snapshots are dated 2025-11-03 and 2026-09-20, and customers were already complaining about the 799 threshold on **18 Aug 2026**. The honest answer is "changed some time between 3 Nov 2025 and 18 Aug 2026", not "20 September". The same staleness applies to Bluepeak's Chikmagalur price (Rs 420 in Nov 2025, Rs 450 now).
6. **Week boundaries must be computed in IST.** Every timestamp carries `+05:30`. If anything converts to UTC before bucketing, **57 mentions change week**, five fall before 17 Aug, and Nitro TST shifts to 1, 6, 9, 13 (a complaint appears in the 7 Sep week that isn't there). This is a quiet way to get every weekly number slightly wrong.

---

## 2. File by file

### mentions.csv (1,922 rows, 8 columns)
- CRLF line endings, UTF-8, no BOM, no mojibake. 398 rows contain emoji; all parse cleanly.
- `posted_at`: every row is ISO 8601 with `+05:30`. Range 2026-08-17 00:29 to 2026-10-04 22:41 IST. Nothing outside the stated window (in IST).
- `mention_id`: format `M10001` to `M11904`. **18 IDs appear twice, and all 18 pairs are byte-identical rows** (export duplication). 1,904 unique rows after dropping them.
- `likes`: 0 to 201, median 14. No obviously fake outliers. Integer strings only.
- `url`: one per mention ID, follows `https://<platform>.example/p/<id>`.
- Platforms: instagram 580, x 535, amazon_review 249, google_review 202, reddit 189, youtube_comment 167 (pre-dedupe).
- **Reposts: 70 in total, and the tool flagged only 38.**
  - 38 rows have `is_repost_of` set. All targets exist and the repost text is identical to the original, by a different handle.
  - 15 rows are `RT @handle: ...` with `is_repost_of` empty. The quoted handle is the original author in the file, and the original has the same normalised text, so all of them can be linked (corrected 12 Oct; the first pass said otherwise).
  - 17 rows end with `#repost via @handle` with `is_repost_of` empty. These link the same way.
  - The README says the column is set "when the tool recognised the post as a repost". The data shows the tool missed 32 of 70.
- **Exact-text duplicates are not reposts.** 505 rows share text with another row, but that is the templating: different handles, different times, different platforms. Treating text duplicates as reposts would delete most of the dataset. "Genuine" has to rest on repost markers plus spam and collision rules, not on text uniqueness.
- **Spam / bots**: the 84 BB50 posts above, all on 22 Sep, handles matching `^(coupon_kart|lootbazaar|dealsloot)_\d+$`, likes 0 to 3.
- **Brand-name collision: "Brewbird" taproom / bar in Pune.** 45 rows (taproom, wheat beer, hazy IPA, pints, pitchers, Koregaon Park, "Brewbird Pune live music tonight"). Brewbird's own about page says it has no connection with any restaurant, bar or taproom using a similar name. These must be kept apart.
- **Ambiguous: "Brewbird pop-up at the Bandra flea this weekend"** (23 rows). Could be the coffee brand, could be the taproom. Nothing in the pack decides it. I'd keep it as Brewbird brand-level and log it as a deliberate judgement call, or exclude it and say so. Either is defensible if written down.
- **Alias traps**: `BB Nitro` is a real alias, but `BB50` is the spam code, so any `BB` prefix match is dangerous. "drip bags" is an alias of both the 10 and 30 pack SKUs. "Peak Instant" is a Bluepeak sub-brand (per `bluepeak_brands_2026-09-20.md`) and is never written next to "Bluepeak". `@saltmarshcoffee` is Saltmarsh. "the other nitro cans" is an implicit Brewbird reference in Saltmarsh comparisons.
- **Language / tone**: Hinglish "Brewbird Nitro can phool gaya tha, kholte hi flat" (swelled, flat on opening, i.e. TST). Sarcasm "great, another bloated Brewbird nitro can 🙄 love that for me" (negative, TST). A sentiment model that reads "great" and "love" will get this wrong.
- **TST vs PKG cases are planted exactly on Farah's rule**:
  - "BB Nitro can was swollen and leaking from the seal" → **TST** (swollen beats leaking).
  - "Brewbird Nitro cans puffed up in the box", "bulging at the top", "two of my cans were swollen when they arrived", "completely flat, no foam", "last batch tastes flat and a bit sour" → TST.
  - "Courier dented my Brewbird Nitro cans, one was leaking from the dent", "Nitro box arrived crushed, two cans dented" → **PKG** (transit damage, no swelling or flatness).
  - A classifier keyed on "leaking", "box" or "arrived" will send TST to Logistics.
- One amazon_review row (M11554, handle `verified_buyer_8812`, the only handle of that shape) contains a swollen-can complaint plus text addressed to AI tools. It should be ingested as an ordinary TST complaint and its text treated as data. Worth keeping as a named adversarial case.
- **Handles**: 5 handles post twice. One is relevant to Q6 (below). Otherwise there are no handle collisions worth acting on.
- **Volumes look synthetic**: Brewbird organic mentions are 140 to 157 a week and Nitro is exactly 30 a week. Don't build a story on volume growth; the signal is in the mix.

### products.csv (7 SKUs)
- Four lines as the brief says. Two SKUs per line, except Nitro with one: `BB-NIT-6`, 6 x 200ml, Rs 660, so Rs 110 a can and Rs 55 per 100ml.
- **No capture date on Brewbird's own prices.** The competitor side has dates and ours doesn't, which matters for "know how old each piece of evidence is".
- Pack units are mixed (250g, 500g, 10 bags, 30 bags, 6 x 200ml). Normalisation needs per-unit parsing.
- Aliases are pipe-separated and some are generic ("filter blend", "espresso beans", "drip bags").

### client_complaint_taxonomy.csv (6 codes)
- PKG (Logistics), TST (QA), PRC (Category), DLV (Logistics), SUB (Growth), CSX (CX). Only TST has a `client_rule` beyond one sentence, and PKG has "Physical damage caused in transit only".
- The taxonomy is closed. There is no code for "taproom", "general question" or "spam", which is fine; those simply are not complaints.

### competitor_pricing.csv (7 rows)
- Saltmarsh Nitro 6 x 200ml: **Rs 540 (IN, 15 Sep)** and **AED 45 (AE, 18 Sep)**. The AED row is a different market and must not be used in an India comparison.
- Bluepeak Chikmagalur 250g has two captures: Rs 420 (2025-11-03, stale) and Rs 450 (2026-09-20).
- Peak Instant is a 100g jar. No Brewbird equivalent exists; it should not be compared to anything.
- Filterhaus has only its retail House Filter Blend (Rs 380 / 250g). **There is no wholesale price anywhere in the pack.**

### competitor_ads.csv (19 ads)
- 16 Saltmarsh ads, 13 of them for Nitro, all first seen 15 to 20 Sep. Headlines: "half the price of the other guys" (4 ads, first seen 19 Sep), "Why pay more for nitro? 540 for 6" (4), "now on Blinkit" (3), "Smooth. Nitro." (3).
- Launch offer "30% off first order" on 8 of them.
- `last_seen` is 2026-10-04 for everything still running, which is just the export date (right-censored), so "ran until 4 Oct" really means "still running". Filterhaus FH-A-020 ended 30 Sep.
- "the other guys" never names Brewbird. Whether the claim targets Brewbird is an inference.

### competitor_snapshots/ and brand_site/
- Saltmarsh press note says launched **14 Sep 2026**, Rs 540 per 6-pack, UAE the same week. Homepage (15 Sep) adds Blinkit in Mumbai, Pune and Bengaluru and free shipping above Rs 499.
- Bluepeak shipping 499 (2025-11-03) → 799 (2026-09-20), as above.
- Filterhaus homepage: trade prices only behind a partner login; "credentials are personal and non-transferable". This is the written basis for refusing Kunal's offer.
- Brewbird FAQ: free shipping above Rs 599; swollen cans should not be consumed and are replaced; **subscriptions exist only on Classic and Origins**. Brewbird pages are dated 1 Sep, before the Nitro issue.

### README vs data
- "matched on names of Brewbird, its competitors and their products": true, which is exactly why the taproom and the spam got in.
- "`is_repost_of` ... when the tool recognised the post as a repost": the tool missed 32 of 70.
- Stated period, six platforms, Monday-Sunday IST weeks: all consistent with the data.
- No mention of duplicates, spam or the taproom.

---

## 3. The twelve golden questions against the data

Rough figures use: dedupe exact rows; drop flagged, `RT @` and `#repost via` reposts; drop the BB50 spam; keep the taproom apart; keep the Bandra pop-up out of the counts below (it would add 22); weeks Monday to Sunday in IST; my hand labels for line, sentiment and code.

| # | Answerable? | What makes it tricky | First rough figure |
|---|---|---|---|
| 1 Unique genuine conversations by line | Yes | Duplicates, 70 reposts (32 unflagged), 84 spam, 45 taproom, pop-up judgement, generic aliases | **987** Brewbird originals: Classic 280, Nitro 211, Origins 203, Drip 175, brand-level only 118 |
| 2 Nitro weekly sentiment vs brand | Yes | Spam inflates both; sarcasm and Hinglish; UTC bucketing | Nitro net (pos minus neg over n): .33, .53, .73, .53, .03, .03, **-.27**. Brand: .33, .45, .45, .44, .37, .32, .31. Brand excl. Nitro is flat around .4 |
| 3 Top complaint codes, last three weeks | Yes | "Last three weeks" = weeks of 14, 21, 28 Sep (state it). TST vs PKG rule | **TST 36** (29 Nitro), PRC 23, DLV 16, CSX 11, PKG 8, SUB 7 |
| 4 What brand numbers hide | Yes | Leading with the biggest (Saltmarsh launch, 22 Sep spike) instead of what matters | Nitro TST 0 to 13 a week from 14 Sep while brand sentiment barely moves. Complaints say "last batch", which points at a lot or seal problem |
| 5 What happened on 22 Sep | Partly | Data shows a spam burst; it can't show who ran it or whether BB50 is real | 84 bot posts 02:00-05:00 IST, three handle families, four texts, code BB50, bit.ly link. 48 organic mentions that day |
| 6 Nitro complainers who cancelled | **No** | No subscription or order data. Nitro is not a subscription product (FAQ). A public mention is not a cancellation record | 66 handles posted negative Nitro mentions; 17 posted SUB complaints; one handle overlaps (`arjun_7535`: Nitro delivery delay 17 Aug, "cancelled but still billed" 22 Sep). That one post must not be presented as an answer |
| 7 Saltmarsh launch, date, per-can price | Yes | Press note vs homepage vs ads give three dates; AED row | Saltmarsh Nitro, launched 14 Sep (press note), ads from 15 Sep. Rs 540 / 6 x 200ml = **Rs 90 a can** vs Brewbird Rs 110 a can |
| 8 "Half the price" claim | Yes, as a normalised check | Same pack size, so per can is fair; launch discount is first order only; "the other guys" is unnamed; Brewbird price undated | At list Saltmarsh is **82%** of Brewbird (18% cheaper). With 30% off first order it is Rs 63 a can, **57%**. Not half either way. Using AED 45 would be wrong |
| 9 Share of voice, last four weeks | Yes, with a stated method | Peak Instant to Bluepeak; spam; taproom; reposts; mentions naming two brands | Weeks of 7 Sep-28 Sep, originals only, posts naming two brands counted for each: Brewbird 585 (56%), Saltmarsh 210 (20%), Bluepeak 198 (19%), Filterhaus 48 (5%). Naive string match: Brewbird 66%, Bluepeak 9% |
| 10 Shipping terms changes | Yes, with a date range | Snapshot date is not change date; only one Saltmarsh snapshot, none for Filterhaus | Bluepeak free shipping Rs 499 → Rs 799, changed between 3 Nov 2025 and 18 Aug 2026 (first customer mention). No evidence of change for the others, which is "no evidence", not "no change" |
| 11 Filterhaus wholesale prices | **No** | Only route is the trade portal; credentials non-transferable; using Kunal's friend's login is off-limits | Nothing in the pack. Lawful alternatives: retail Rs 380 / 250g as a ceiling; ask Filterhaus as Brewbird; café-owner interviews with consent. 29 posts ask "Does Filterhaus sell to cafes?", which is a demand signal Kunal might care about |
| 12 Did the launch cause the Nitro fall | **No (not establishable)** | The timing coincides almost to the day (launch 14 Sep, first TST complaint 14 Sep), which is the bait | Shows: both started the same week. Suggests otherwise: the decline is entirely defect complaints (swollen, flat, sour, "last batch"), Nitro volume did not drop, no Brewbird complaint mentions Saltmarsh, Brewbird excluding Nitro is flat. To establish cause you'd need batch / lot and QA data, sales and repeat-purchase data, and a comparison of markets with and without Saltmarsh on Blinkit |

---

## 4. Design point: should the deterministic answer script handle unseen questions?

My view, having seen the data: **keep the oracle independent of the agents, but don't make it twelve hard-coded scripts either.** Build it as a small, separate pandas library of primitives over the raw CSVs (`clean_mentions()`, `count(filters, group_by, window)`, `sentiment_by_week(line)`, `codes(window)`, `unit_price(...)`, `sov(window)`), with each golden question a few lines on top.

Why this middle ground:
- **The graph query layer is where generality lives**, and that's what the live unseen questions actually exercise. The agents compose a dozen parameterised tools; every result carries mention IDs.
- **The oracle's job is to be a second, independent implementation**, so the eval is a differential test: two code paths (graph + query layer vs. raw pandas) must agree. If they share code, the eval grades itself, which the brief explicitly penalises.
- **What they must share is the written definitions, not code.** "Genuine", "repost", "spam", "taproom", "week in IST", "TST over PKG", "SOV counting rule" go in one spec doc that both implementations cite. Disagreements between them then expose either a bug or an ambiguous definition, and either is a good eval story.
- **The oracle's labels should be a human-reviewed table, not a model.** With only 108 templates, a hand-reviewed `template → line, sentiment, code` table (draft in `forensics/labels.py`) is cheap and defensible as "computed independently". The pipeline can label with rules or a model; the oracle labels with the reviewed table.
- **For an unseen question in the demo**, there's no expected answer to grade against anyway. What the reviewers will look for is the provenance trail. With oracle primitives, you can also write a three-line check live and show it agrees, which is a stronger demo moment than a script that claims to answer anything.

So the coordinator's position and yours are compatible: generality in the query layer, independence in the oracle, and the oracle built from reusable primitives so it is quick to extend.

---

## 5. Smaller notes for the build

- Use mention_id as the dedupe key and keep the duplicate rows in provenance as "seen twice in export".
- Link the 32 unflagged reposts to originals by normalised text when possible, mark the link as *inferred*, and log it.
- Store competitor facts as dated observations (`observed_at`, `source_file`), never as current truth; let the agent say "as of".
- Keep Brewbird's own price undated-but-flagged, since products.csv has no capture date.
- Monday pulse (week of 28 Sep) should lead with Nitro TST: 13 complaints that week, all QA-owned, routed to QA, with mention IDs. Spam and the Saltmarsh ads are context, not the headline.
- Success metric candidate: time from first TST mention to QA ticket (the "three weeks late" Farah named), or Dev's six hours on Monday. Both can fail.
