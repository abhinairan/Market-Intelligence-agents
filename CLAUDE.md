# CLAUDE.md

Brewbird take-home for Zocket (FDE assignment v4): a brand knowledge graph (Neo4j) and two agents (consumer, competitor) over it. The brief PDF is in `docs/` (git-ignored, not ours to publish).

## Read first
- `docs/PLAN.md`: execution plan, phases P0 to P7, ontology, tools, eval. **§5a is the agreed labelling design.**
- `docs/definitions.md`: the rulebook (D-xx rule IDs). **Implement the D-rules from this file, never from `oracle/`.** The pipeline and the oracle must stay independent: they share definitions, not code. Cite rule IDs in code comments.
- `docs/data-observations.md`: forensics pass with the reference figures to check against.
- `docs/er-log.md`: entity-resolution log (ER-xx), to be kept in step with the pipeline.
- `docs/failure-log.md`: every agreed failure, its cause, the change and the before/after (F-xx). Shareable with reviewers.
- `oracle/label_table.csv`: human-reviewed labels for the oracle only (P5), marked reviewed 12 Oct. The pipeline never reads it.
- `oracle/`: the independent oracle (pandas over the raw CSVs) that writes `eval/expected/`. **Never import from or copy into it**; `tests/test_oracle.py` checks the oracle imports nothing from `src/halyard`.

## Working agreements
- One branch per phase, merged to `main` when the phase's "Done when" passes. `main` must always run from a clean clone. Commit only when asked or at the end of an agreed step. Never commit `.env`.
- **Before building any step, present the approach and plan and wait for Abhinav's go-ahead.** "Go ahead with the next steps" means present the plan first, not skip it.
- After each step, stop and give Abhinav a short walkthrough of the changes before moving on.
- **After a live agent or eval run, report the issues and propose changes; do not edit skills, tools, rules or the oracle until he agrees.**
- Every agreed failure and fix goes in `docs/failure-log.md` (shareable with reviewers).
- Keep answers concise. Abhinav prefers a recommendation over a survey of options.
- Client facts come from the data pack via loaders; our judgement calls and parameters go in `config/brewbird/*.yaml`; code holds only generic logic (a new brand = new config + data, no code change).

## Decisions made in chat (not all obvious from the docs)
- **Docker runtime:** OrbStack on this Mac. Neo4j `5.26-community` via `docker-compose.yml`.
- **LLM:** provider-neutral `LLMClient` (`src/halyard/llm/`). `.env` has `LLM_PROVIDER=openai`, `LABEL_MODEL=gpt-6-luna`, `AGENT_MODEL=gpt-6-luna` (`gpt-6.1-sol` commented out). The agents' tool calling is OpenAI only; the Anthropic adapter covers labelling. No pipeline/agent code imports an SDK directly; use `get_client(settings, "label" | "agent")`. P5 adds a judge model (`gpt-6.1-sol`), see below. Prices are in `config/llm_prices.yaml` (`gpt-6-luna` $0.10 in / $0.50 out per million; `gpt-6.1-sol` price not known yet, so `halyard spend` reports its tokens only).
- **Labelling (PLAN §5a, D-35):** model-first, not rules-first. The label model labels each distinct normalised text; sentiment and codes are separate cached calls; codes only for negative texts; cache key = normalised text + provider + model + hash of the generated prompt (no manual prompt versions); cache `data/cache/labels.jsonl` is append-only and committed. Deterministic client rules run last (TST over PKG for can defects, only the six codes, routing from the taxonomy). Cache miss with no key gives `unlabelled`, never neutral. Mention text is passed as delimited data (M11554 is a planted prompt injection).
- **Time (D-01):** keep timestamps exactly as exported (`+05:30`); derive `date_ist` and `week_ist` from the local IST clock time. Never convert to UTC before bucketing.
- **City tag (D-26, added at Abhinav's request):** extract the bracketed city, e.g. "(Delhi)", to `Mention.city` before normalisation. 502 of 1,904 mentions carry one (Bangalore 175, Delhi 167, Mumbai 160).
- **Extracted vs inferred (decided 13 Oct):** a value copied from a source is `extracted`; anything computed from extracted values by a rule or model is `inferred` and names its rule, including node properties (`date_ist`, `week_ist`, `city`, pack units, unit prices), not only edges. To be implemented in the graph write (step 6) and described in `docs/ontology.md`.
- **Normalisation (D-12)** never alters stored text; it only produces matching keys.

## Commands
```
uv sync                 # install
uv run halyard up       # start Neo4j and wait (make up)
uv run halyard down [--wipe]
uv run halyard llm-check   # one tiny call per configured model
uv run pytest           # tests (integration test skips if Neo4j is down)
uv run ruff check src tests
```
```
uv run halyard build      # wipe and rebuild the graph in Neo4j; prints counts
uv run halyard label      # label new texts into the cache (needs the API key only for new text)
uv run halyard ontology   # regenerate docs/ontology.md from the schema
uv run halyard tool       # list the query tools; `halyard tool <name> '<json args>'` runs one and logs it
uv run halyard trace M10149 R-c9ce8b67   # mention, ad, observation or result IDs back to file and row
uv run halyard spend [--run A-...]   # tokens and cost from the usage log
uv run halyard ask consumer "<question>" [--json]   # needs Neo4j up, a built graph and the API key
uv run halyard skills    # regenerate skills/<agent>/tools.json from the tool registry
```
`halyard eval` is a stub that fails with the phase it belongs to (P5).

## Progress (as of 14 Oct 2026)
- **P0 done**, merged and pushed to `main` (`a9a5089`): skeleton, compose, Makefile, CLI, `config/brewbird/client.yaml`.
- **P2 done**, merged to `main` and pushed. Branch `p2-pipeline`:
  - `a272030` PLAN §5a + D-35 rewrite (model-first labelling)
  - `3ea1759` provider-neutral LLM settings; exact brief filename in `.gitignore`
  - `6753896` **P2 step 1 done**: `LLMClient` + OpenAI/Anthropic adapters, usage log `outputs/llm_usage.jsonl`, `halyard llm-check` (live check passed)
  - plus this CLAUDE.md
  - **P2 step 2 done**: loaders in `src/halyard/ingest/` (`records.py`, `loaders.py`, `load_pack(client)`), pack file names and `city_tags` in `client.yaml`, `tests/test_loaders.py`
  - **P2 step 3 done**: `src/halyard/ingest/hygiene.py` (`run_hygiene(mentions, client)`: normalised text, reposts, spam bursts, double posts), `config/brewbird/hygiene.yaml`, `tests/test_hygiene.py`. Normalisation gives 93 distinct texts; the forensics' 108 counted the 15 `RT @` variants separately.
  - **P2 step 4 done**: `src/halyard/ingest/entities.py` (`resolve_entities`, `mention_status`), `config/brewbird/entities.yaml`, `tests/test_entities.py`, counts added to `docs/er-log.md`. 987 genuine and the SOV counts match the forensics. Decided: the 34 "Brewbird beans" mentions stay brand-level (ER-18), so Classic is 246 and brand-level 152; the reviewed table row was changed to match.
  - **P2 step 5 done**: `src/halyard/ingest/labelling.py` (`Labeller`, `LabelCache`), `src/halyard/ingest/pipeline.py` (`prepare(settings)` runs steps 2 to 5), `halyard label`, prompts in `skills/labelling/` (Abhinav asked for prompts in skill files, not code), rules in `config/brewbird/labels.yaml`, cache `data/cache/labels.jsonl` (109 answers for 83 texts, openai/gpt-6-luna). Codes only for negative texts about the client; competitor complaints get sentiment only (decided by Abhinav). Nitro TST by week and last-3-weeks codes match the forensics exactly. D-30 gained a rule at Abhinav's request (regular use, rebuying or stocking up is positive), which moved one text ("stocked the fridge...", 30 mentions) from neutral to positive; nothing else changed.
  - **P2 step 6 done**: ontology in `src/halyard/store/schema.py` (single definition; the builder refuses anything outside it; `docs/ontology.md` is generated by `halyard ontology` and a test fails if it drifts), `src/halyard/ingest/graph.py` (`build_graph`, pure), `src/halyard/store/neo4j_writer.py`, `halyard build` (wipe + rebuild, prints counts), page-fact patterns in `config/brewbird/observations.yaml`, `tests/test_graph.py`. Two builds give 3,889 nodes and 5,384 edges each. Nodes carry `inferred_properties` (`name:rule`). Edges with no stated capture date (mentions, ads, catalogue) have no `captured_at`.

## P2 done-check (step 7, passed 13 Oct 2026)
- Clean clone of the branch with no API key: 66 tests pass, lint clean, `halyard build` twice gives identical output (3,889 nodes, 5,384 edges), 0 model calls.
- Matches the forensics: 987 genuine conversations from 984 authors; Nitro 211, Origins 203, Drip 175; Nitro TST by week 0,0,0,0,7,9,13; last-3-weeks codes TST 36, PRC 23, DLV 16, CSX 11, PKG 8, SUB 7; SOV last 4 weeks 585 / 210 / 198 / 48 (56%, 20%, 19%, 5%); both net-sentiment trends.
- Explained differences: Classic 246 and brand-level 152 (forensics 280 / 118) because of ER-18; 93 distinct texts, not 108 (RT variants merge); 14 Saltmarsh Nitro ads, not 13.

## P3 done (13 Oct 2026), branch `p3-tools` merged to `main` and pushed (`9531e79`)
Query layer: a store interface, twelve tools, a registry, a call log and `halyard trace`.

**Store** (`src/halyard/store/`)
- `graph_store.py`: `GraphStore` protocol with five reads (`mentions`, `observations`, `ads`, `nodes(label)`, `node(label, key)`), row types, and `MemoryStore` over the in-memory graph, so tool tests need no database.
- `neo4j_store.py`: `Neo4jStore`, the only Cypher in the query layer. `connect()` switches off Neo4j's "unrecognised relationship type" warning (no `DOUBLE_POST_OF` edges exist in this pack).
- Counting is done in Python in the tools, so a second store only needs the five reads.

**Tools** (`src/halyard/tools/`). Every tool returns `ToolResult` = `{data, mention_ids, source_refs, method_note, as_of}`.
- `base.py` (`ToolResult`, `ToolError`), `context.py` (`ToolContext`: store, client, cached `mentions`, `names`, `products`, `code_owners`, `tool_log`), `windows.py` (`resolve_window`, `weeks_in`; D-01 to D-04), `filters.py` (`Names`, `MentionFilter`, `select_mentions`; `brand-level` as a line filter; genuine only unless `include_excluded`, D-16).
- `mentions.py`: `count_mentions`, `get_mentions` (by filter, `ids` or `result_id`), `exclusions`, `daily_activity` (D-43).
- `sentiment.py`: `sentiment_trend` (D-40; for a line also `brand_overall` and `brand_without_this_line`; `split_by_line`), `complaint_breakdown` (D-42, D-34).
- `share_of_voice.py`: `share_of_voice` (D-41, reach per D-44; `naive` only with `compare_naive`).
- `competitors.py`: `brand_facts` (renamed from `competitor_observations` in P4 step 4, Abhinav; age, stale, changes as date ranges per D-51, launches with corroboration per D-55), `price_compare` (same market, currency and unit only; `claimed_ratio`; `include_offers`; D-53), `competitor_ads` (D-54).
- `coverage.py`: `coverage(topic)`; `holds` from the graph, `not_in_data` from `config/brewbird/coverage.yaml` (D-60, D-62).
- `trace.py`: `trace(ids)` for mention, ad, observation and other node keys and for result IDs; `render_trace` for the CLI.
- `registry.py`: `TOOLS` (name, description, JSON Schema) and `run_tool(ctx, name, args)`, the only way a tool is called. `log.py`: calls are logged whole to `outputs/tool_calls.jsonl` (git-ignored) under a deterministic `R-xxxxxxxx` result ID when `ctx.tool_log` is set.
- Parameters added to `client.yaml`: `anomaly_median_multiple` (D-43), `sentiment` thresholds (D-40), `pricing.claim_tolerance` (O-5), `change_evidence` (D-51).

**Tests:** `test_store.py`, `test_tools_mentions.py`, `test_tools_competitors.py`, `test_tools_trace.py`. The last runs every registered tool on `Neo4jStore` and `MemoryStore` and fails if a tool is missing from that check.

**P3 done-check (step 7, passed 13 Oct 2026)**
- Clean clone of the branch with `.env.example` as `.env` (no API key): 110 tests pass, lint clean, `halyard build` twice gives identical output (3,889 nodes, 5,384 edges, 0 model calls), `halyard tool` and `halyard trace` work.
- Figures the tools are tested against, all matching the forensics: 987 conversations from 984 authors, by line 246 / 211 / 203 / 175 / 152; exclusions 84 spam, 70 reposts, 42 taproom, 22 pop-up; 22 Sep = 132 mentions = 84 spam + 41 genuine + 4 reposts + 3 unrelated (the forensics' "48 organic" is everything but spam), median day 36; Nitro net .33, .53, .73, .53, .03, .03, -.27 with 63.3% negative in the last week; week of 21 Sep flagged for negative like share (42% of posts, 57% of likes); codes TST 36 (29 on Nitro), PRC 23, DLV 16, CSX 11, PKG 8, SUB 7; SOV 585 / 210 / 198 / 48, naive 66% for Brewbird and 9% for Bluepeak; Rs 90 vs Rs 110 a can, ratio 0.82, with the 30% first-order offer Rs 63 and 0.57; AED row not compared; Bluepeak shipping 499 to 799 between 3 Nov 2025 and 18 Aug 2026 (M10049); Saltmarsh Nitro launched 14 Sep, 14 ads all still running; M10149 on rows 158 and 159.

**Decisions made by Abhinav during P3**
- Naive share of voice is shown only on request (`compare_naive`); the brief asks for the counted figure and how it was counted. D-41 updated.
- Tools keep the brand explicit (no default inside a tool). **For P4:** the agent skill says that when a question names no brand, use the client brand, and say so in the answer.
- The full list of mention IDs stays in the tool-call log under the result ID. **For P4:** send the agent a capped list plus the result ID; a follow-up gets the IDs back with `get_mentions(result_id=...)` or `trace`.
- `outputs/tool_calls.jsonl` is git-ignored.

## P4 done, branch `p4-agents` merged to `main` and pushed (`a75209a`, 14 Oct)
Stop after each step with a short walkthrough, as in P2 and P3. Steps 1 to 4 committed on 14 Oct.

**Decisions made by Abhinav (13 Oct)**
1. Agent model: build and debug on `gpt-6-luna`; at the end run the 12 questions on `gpt-6.1-sol` too and keep it only if it answers better.
2. The final answer is structured JSON (answer text, claims with their cited IDs, an `answerable` field, `yes` / `partly` / `no`, which replaced a `cannot_answer` flag on 14 Oct); the CLI prints it as text. Plan: the answer is itself a tool call (`require_tool`), so it has a schema.
3. The pulse is an agent run from its own skill file, with the same tools and citation check.
4. **Tool calling is OpenAI only.** The Anthropic adapter stays for `complete_json` (labelling) and raises "not implemented" for `run_with_tools`. No Anthropic tool-calling code or tests. PLAN §2 and the P4 row say so; the README must too (P6).

**Approach**
- One generic agent loop, three skill files (`skills/consumer/`, `skills/competitor/`, pulse). They differ only in skill file and tool subset. Tool definitions are generated from the registry (`TOOLS`), never copied.
- Grounding is checked in code: a claim cites a result ID for an aggregate and mention IDs or `file:row` refs for examples; every cited ID must have been returned by a tool in that run. One retry with the error fed back, then the answer is marked failed.
- Carried over from P3: when a question names no brand the skill says to use the client brand and say so; follow-ups use `get_mentions(result_id=...)` or `trace`.
- **Cost controls (agreed 14 Oct):** cap the mention IDs sent to the model (about 20 plus the total and the result ID; `count_mentions` and `share_of_voice` results are about 90% IDs); a turn cap and a total-token cap per question in `client.yaml`, and a run that hits one says so; the skill asks for independent tool calls in one turn; each agent gets only its tool subset; skill text and tool definitions form a stable prefix for prompt caching; tests use a scripted fake model. Usage rows carry a `run_id`. Prices for the two models are not known: report tokens, and ask Abhinav for prices to put in config.

**Step 1 done (14 Oct):** `src/halyard/llm/base.py` gained `ToolSpec`, `ToolCall`, `Message`, `ToolTurn` and `LLMClient.run_with_tools(system, messages, tools, max_tokens, require_tool, run_id)` (rejects unknown tool names and a missing required call; logs `cached_input_tokens` and `run_id`). `openai_client.py` implements it on the Responses API with non-strict function tools (`to_tool`, `to_input`, `to_call`). `halyard llm-check` now also does a tool-call round trip. 114 tests pass. Live: all twelve registry schemas are accepted (2,472 input tokens for the full tool list) and the model asks for two tools in one turn.

**Step 2 done (14 Oct):**
- `src/halyard/agents/loop.py`: `AgentSpec` (name, instructions, tool names, answer tool), `Limits.from_client` (the `agent:` block in `client.yaml`: 8 turns, 80,000 tokens, 20 IDs sent, 1 answer retry), `run_agent(client, ctx, spec, question, limits, check=None)` returning an `AgentRun` (status `answered` / `failed_check` / `error`, `stopped_by` `turn_cap` / `token_cap`, steps, `results` = every result's full mention IDs and source refs for the citation check, messages, token totals), `cap_result`, `save_run` (transcripts in `outputs/runs/`, git-ignored).
- Every turn uses `require_tool`; the run ends when the model calls `answer` on its own. At a limit the model gets one last call with only `answer` on offer. `check` is the hook step 3 fills with the citation check; a rejected answer is fed back `answer_retries` times, then kept and marked `failed_check`.
- `src/halyard/agents/answer.py`: the `ANSWER` tool (`answer`, `claims` = `[{claim, cites}]`, `answerable`, `needs`; `needs` is required unless `answerable` is `yes`) and `shape_problems`.
- `config/llm_prices.yaml` (not client-specific), `src/halyard/llm/spend.py`, `halyard spend [--run A-...]`. Price given by Abhinav: `gpt-6-luna` $0.10 in, $0.50 out per million tokens. **`gpt-6.1-sol` price still needed** before the comparison run.
- `tests/test_agent_loop.py` (scripted model, `MemoryStore`). 126 tests pass.
- Live smoke with a placeholder instruction: two questions, correct figures (Nitro net .33 to -.27; TST 29 on Nitro), the forced answer at a turn cap works, prompt caching is working, about $0.001 a question. All spend to date: $0.013.

**Step 3 built (14 Oct), awaiting Abhinav's sign-off on the last tuning proposals:**
- Skills: `skills/consumer/SKILL.md` (front matter `name`, `description`, `tools`; instructions with `{{slots}}`), `skills/shared/grounding.md`, `skills/shared/answer_format.md`, `skills/README.md`. Skill files name no brand, line or date (a test enforces it). `skills/<agent>/tools.json` is generated from the registry by `halyard skills`; a test fails if it drifts.
- `src/halyard/agents/skills.py` (`load_skill`, `render_tools`, `write_tools`), `citations.py` (`citation_check(ctx)`: every cite must be a result ID, mention ID, source ref or data value a tool returned in the run; a claim must cite something; a mention ID or result ID in the prose must be returned and cited), `render.py`, `halyard ask <agent> "<question>" [--json]`.
- `eval/golden.yaml`: the twelve questions word for word from the brief, with the agent each goes to (expected answers come in P5).
- **D-42 amended (agreed by Abhinav):** no two examples of a code share the same normalised text. `complaint_breakdown` and its test follow.
- Live on `gpt-6-luna`, three rounds: Q1 to Q6 correct every time, every citation passed with no retry, Q6 declines. About $0.001 to $0.003 a question; project spend $0.042.
- **Working rule from Abhinav:** after a live run, report the issues and propose changes; do not edit skills or tools until he agrees.
- Round 4 changes (agreed by Abhinav): top three codes is fine for Q3 (no rule forcing the full list); unusual days explained from what the data shows (repeated posts, authors, place, time, statuses) with 2 or 3 example IDs; **D-45** direction label on every `sentiment_trend` series (`data.directions`; thresholds `sentiment.direction` in `client.yaml`) and grounding rule 9 (use the tool's word); **D-60** amended: decline only the part needing records, a post is evidence of what its author did, never a count. (Superseded by `answerable`, round 6.) `coverage.yaml` subscriptions entry says posts about subscriptions are in the data.
- Round 5 changes (agreed by Abhinav): **page references point at the line** (`Source.body_row`; `coverage` returns `says: [{text, source_ref}]` with `file:line` per matched line, e.g. `brand_site/faq.md:6`; the ER-01 `OF_BRAND` edge from a page cites the line naming the sub-brand; `trace` resolves any `file:line` to the page line and every node read from that row; `src/halyard/tools/sources.py`). Audit: every other tool reference already pointed at its row. Output format labels each weekly value with its week; grounding rule 4 says to state "some authors did X" directly with the distinct-author count; the brand note is only for questions naming no brand. Graph counts unchanged (3,889 / 5,384); 136 tests.
- Round 6 changes (agreed by Abhinav): grounding rule 10 (answer about the thing asked about; a product's conversation is not a reaction to one of its plans or features); `cannot_answer` replaced by `answerable` = `yes` / `partly` / `no`, with `needs` required unless `yes`; the CLI prints "[Partly answerable …]". Live: Q1 yes, A-subscription-usage partly, A-subscription-reaction no longer uses line sentiment as a proxy. Round 7: the `partly` definition was sharpened (a nearby figure offered instead of the answer is `no`) and the A-subscription-reaction expectation changed to `yes`; Q6 still came back `partly`; fixed by putting the same clause in the `answerable` description of the answer tool's schema (Q6 `no` on two runs, A-subscription-usage still `partly`).
- `eval/adversarial.yaml` started: A-teams (full code distribution by owner team), A-subscription-reaction, A-subscription-usage.
- `coverage` already returns page lines and mentions matching the topic's words (e.g. the FAQ's "Monthly subscriptions on Classic and Origins", `brand_site/faq.md:2`), so the client's page facts are reachable for coverage-type questions without a new tool.

**Step 4 started (14 Oct):** `competitor_observations` renamed `brand_facts` (Abhinav) and given to both agents; `skills/competitor/SKILL.md` written (11 rules: date every fact, capture date is not a change date, no evidence is not no change, like-with-like prices, claims via `claimed_ratio`, how SOV was counted, shows/suggests/would need, no gated sources). First live run of Q7 to Q12: figures right on all six; open issues and proposals reported to Abhinav, not yet applied (Q11 and Q12 marked `partly`; Q12 misses that 0 of 57 negative Nitro posts name Saltmarsh and that Nitro volume is flat at 30 a week, and read 200 mentions for $0.008; Q10 omits Filterhaus having no shipping data; no adversarial login question yet).
- Round 2 of step 4 (agreed by Abhinav): `get_mentions` pages (`offset`, `next_offset`), at most `tools.get_mentions_max_rows` = 50 per call in `client.yaml` (larger limits are capped, not refused); both skills say test a pattern with counts and read posts for examples; competitor rule 5 names competitors with no evidence; rule 10 tests a causal link with counts and makes cause `answerable: no`; grounding rule 5 the same; output format sets out **Shows / Suggests / Would need** for a cause question; adversarial A-login added. Live: Q11, Q12 and A-login `no`; Q12 has the three parts and cost $0.0035 (was $0.008); A-login refuses with the reason and lawful routes. Round 3 (agreed by Abhinav): `brand_facts` with a `kind` and no brand returns `no_facts_for` (Q10 now names Filterhaus); `count_mentions` lists every brand, line, code and week with 0 where none matched (weeks added beyond the agreed brand/line/code, flagged to Abhinav); competitor rule 10 says the volume of the line in question. Q12 now states Nitro volume flat and that none of 211 Nitro conversations names Saltmarsh.
- **Full run, 14 Oct, after all changes:** 12 golden + 4 adversarial, all answered with correct figures and valid citations; `answerable` as expected on all 16 (Q6, Q11, Q12, A-login `no`; A-subscription-usage `partly`); one citation retry (Q9, a claim citing nothing, fixed). 16 questions cost about $0.035; project spend $0.157. Step 4's done-check is met; remaining known variation: Q11/A-login sometimes omit the retail price or the consent-research route, Q5 says "early hours" rather than the exact span.

**Step 5 done (14 Oct):** the pulse is the consumer agent's second skill (Abhinav): `skills/consumer/pulse.md` with its own `pulse.tools.json`; an agent folder can hold several skills (`skill_files`, `load_skill(agent, ctx, skill)`, `tools_path`). `src/halyard/agents/pulse.py` (`pulse_week` refuses a day that does not start a reporting week in the data, `pulse_request`, `write_pulse`). `halyard pulse --week 2026-09-28` writes `outputs/pulse-2026-09-28.md` (brief, evidence list, footer). Skill: gather in one or two turns, lead by what matters, route to owner teams, describe a problem by what most posts say with the split, earn every noise verdict with counts, do not repeat the lead; brief = Lead / What changed / Noise / Watch next week, about 350 words. Live (after one tuning round agreed with Abhinav): leads with Nitro TST, 13 of the week's 15, 10 of 13 describe swollen/puffed/bulging cans, QA-owned, 3 IDs; Saltmarsh's 14 running ads are noise because no Brewbird post that week names Saltmarsh and Nitro volume is flat (31, 30); 309 words, $0.0065; every figure checked against the data. 145 tests.

**Step 6 done (14 Oct):** `halyard demo` = up, build, the golden questions listed under `demo:` in `client.yaml` (Q4 consumer, Q8 competitor), the Monday pulse for `demo.pulse_week`, then `halyard spend`; exits non-zero if any run is unanswered or fails its check. `ask`, `pulse` and `demo` share `_run` in `cli.py`. README: OpenAI key needed for the agents, agent commands listed.

**P4 done-check (passed 14 Oct 2026):** clean clone of `p4-agents` with `.env` copied: 145 tests pass, lint clean, `halyard build` twice gives identical output (3,889 nodes, 5,384 edges, 0 model calls), `halyard demo` exits 0 with Q4, Q8 and the pulse answered and verified. Full run of 12 golden + 4 adversarial earlier the same day: all correct with valid citations. Agent spend for all of P4: $0.171 (208 calls on `gpt-6-luna`); project total $0.18. **Deferred by Abhinav:** the `gpt-6.1-sol` comparison (no price yet).

## P5: evaluation (plan agreed 14 Oct, not started; branch `p5-eval` not yet created)
Create `p5-eval` from `main`. Uncommitted on `main` at the end of the 14 Oct session: `docs/failure-log.md` (new) and this CLAUDE.md update; they move to the branch with `git checkout -b p5-eval`.

**Already on `main` (Abhinav):** the independent oracle (`oracle/`, pandas over the raw CSVs, labels from `oracle/label_table.csv`), `eval/expected/q01..q12.json` (figures, mention IDs, D-rules; `rubric` lists for Q4, Q5, Q6, Q8, Q9, Q10, Q11, Q12; `facts` for Q6, Q11, Q12), `tests/test_oracle.py`. Plus from P4: `eval/golden.yaml` (12 questions word for word) and `eval/adversarial.yaml` (A-teams, A-subscription-reaction, A-subscription-usage, A-login).

**Grading (agreed):**
- Figures: the oracle's key figures must appear in the answer, matched as numbers with rounding tolerance.
- Cited IDs: the mention IDs behind the answer's citations (every mention a cited `R-...` result counted, from `run.results`, plus cited mention IDs) against the oracle's `mention_ids`: precision and recall.
- Rubric items (the sentences in a question's `rubric` list): an LLM judge marks each met / not met and must quote the answer sentence that meets it. **Judge model: `gpt-6.1-sol`** (Abhinav). Needs a third purpose in `get_client` (e.g. `"judge"`, `JUDGE_MODEL` in `.env` and `.env.example`); judge prompt in a skill file (e.g. `skills/eval/judge.md`).
- `answerable` must equal the expected `yes` / `partly` / `no`.
- **Pass thresholds (agreed):** a numeric question passes when every key figure appears, ID recall >= 0.95 and precision >= 0.95; a rubric question passes when every item is met.
- **Repeats: 3 runs per question** in the report, giving a pass rate. Estimated cost of a full eval about $0.20 plus the judge.

**Steps**
1. **Oracle catch-up, from `docs/definitions.md` only (never from pipeline code):** D-42 was amended in P4: "no two examples of a code with the same normalised text (D-12)...; if a code has fewer distinct texts than examples asked for, it gets fewer". The oracle still picks examples by the old rule, so `q03.json` has duplicate-text pairs (PRC M11562 + M11226, CSX M11832 + M11125). Implement the D-12 normalisation in the oracle from the rulebook, skip an example whose normalised text matches one already picked, regenerate `eval/expected/` (`python -m oracle.run`), oracle tests and selfcheck must pass. Expect only the second PRC and CSX examples to change. D-45 and the D-60 amendment change no oracle figure (D-45 labels could optionally be computed so the eval can check "falling"/"steady").
2. **Adversarial set to about 10** (PLAN §6), each with `expects`, expected `answerable` and 2 to 4 rubric items for Abhinav to review: causation bait ("So Saltmarsh caused it, right?"), the planted injection M11554 (a question that brings it into results), brand collision ("How is Brewbird's beer?"), stale evidence ("What is Bluepeak's current price?"), unit/region trap ("Is Saltmarsh half the price in the UAE?"), "Reply to this review for us" (D-63), leading question ("Confirm sentiment is stable"). Oracle expected answers for adversarial questions with figures (e.g. A-teams: Logistics 57, QA 49, Category 44, Growth 17, CX 16).
3. **Eval runner and judge:** `halyard eval [--repeat N] [--only Q3,A-login]` (and `make eval`), reusing `_run` in `cli.py`; tests with a scripted model.
4. **First full run and `docs/eval-report.md`:** summary table, then per question: pass/fail per layer, ID overlap, rubric items with quotes, `answerable`, run IDs, cost. Report failures and proposed fixes to Abhinav before changing anything.
5. **Failure story:** agreed fixes logged in `docs/failure-log.md` under "Found by the eval (P5)" with before and after eval results; the report links to it.
6. **Done-check:** `make eval` from a clean clone, then merge `p5-eval` to `main` and push.

**Failure log:** `docs/failure-log.md` exists, backfilled with four major P4 fixes (F-P4-1 Q12 causation evidence and cost, F-P4-2 page citations pointing at the page not the line, F-P4-3 Q4 weekly counts against the wrong weeks, F-P4-4 subscription reaction answered with the lines' overall sentiment). Abhinav chose to leave the smaller P4 fixes out. Entry layout: question; what failed with run IDs and quotes; cause; change and who agreed it; files; before/after table.

**Expected first eval findings (from comparing the oracle with the agents' latest answers, 14 Oct):**
- Q3: examples differ until step 1 is done.
- Q6 rubric: "Notes Nitro is not a subscription product (FAQ)"; the agent does not say it (`coverage` does return the FAQ line).
- Q12 rubric: "would need" includes sales and repeat purchase and markets with and without Saltmarsh; the agent names only batch/QA records.
- Q11 rubric: consented café interviews; sometimes omitted.
- Q5 rubric: "genuine volume that day was close to normal"; not said outright.

After P5: P6 (outputs and packaging: readout PDF, three replies, skills package, ontology note, README, spend and "another week" notes) and P7 (clean-clone rehearsal and recording). The `gpt-6.1-sol` agent comparison is deferred (Abhinav).

**Merged main checked (14 Oct):** `main` = Abhinav's P5 oracle work (`47c6ddd`: `oracle/`, `eval/expected/q01..q12.json`, `tests/test_oracle.py`, pandas dev dependency) + P4. Clean clone: 156 tests pass, lint clean, two identical builds, `halyard demo` exits 0.

**P5 findings from comparing the oracle's expected answers with the agents (14 Oct), to address in P5:**
- Q3: the oracle picks examples by the old D-42; D-42 was amended in P4 (no two examples of a code with the same normalised text), so the oracle must follow it (the agent now cites M10963 for PRC where the oracle has a duplicate text).
- Q6 rubric: "Nitro is not a subscription product (FAQ)"; the agent does not say it.
- Q12 rubric: "would need" includes sales and repeat purchase and markets with and without Saltmarsh; the agent names only batch/QA records.
- Q11 rubric: consented café interviews; the agent sometimes omits it.
- Q5 rubric: "genuine volume that day was close to normal"; not said outright.
- D-45 (direction labels) and the D-60 amendment change no oracle figure.
