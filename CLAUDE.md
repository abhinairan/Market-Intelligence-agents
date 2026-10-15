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
- **LLM:** provider-neutral `LLMClient` (`src/halyard/llm/`). `.env` has `LLM_PROVIDER=openai`, `LABEL_MODEL=gpt-6-luna`, `AGENT_MODEL=gpt-6-luna`, `PULSE_MODEL=gpt-6.1-sol` (the pulse only; falls back to `AGENT_MODEL` when empty, decided 15 Oct). The agents' tool calling is OpenAI only; the Anthropic adapter covers labelling. No pipeline/agent code imports an SDK directly; use `get_client(settings, "label" | "agent" | "judge" | "pulse")`. P5 adds a judge model (`gpt-6.1-sol`), see below. Prices are in `config/llm_prices.yaml` (`gpt-6-luna` $0.10 in, $0.01 cached input, $0.50 out per million; `gpt-6.1-sol` $2.00 in, $10.00 out). `halyard spend` prices cached input at `cached_input`; it reports $0.45 against $0.51 billed by OpenAI (OpenAI counts about 5% more tokens and charges cache writes at $0.125).
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
uv run halyard build      # start Neo4j if needed, wipe and rebuild the graph; prints counts
uv run halyard label      # label new texts into the cache (needs the API key only for new text)
uv run halyard ontology   # regenerate docs/ontology.md from the schema
uv run halyard tool       # list the query tools; `halyard tool <name> '<json args>'` runs one and logs it
uv run halyard trace M10149 R-c9ce8b67   # mention, ad, observation or result IDs back to file and row
uv run halyard spend [--run A-...]   # tokens and cost from the usage log
uv run halyard ask consumer "<question>" [--json]   # needs Neo4j up, a built graph and the API key
uv run halyard skills    # regenerate skills/<agent>/tools.json from the tool registry
```
`uv run halyard eval [--repeat 3] [--only Q3,A-login] [--report E-id]` runs the golden and adversarial questions through the agents and grades them against `eval/expected/` (needs Neo4j, a built graph and the API key; a full run is about $0.09 and 25 minutes). `python -m oracle.run` regenerates the expected answers.

## Progress (as of 15 Oct 2026)
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

## P5: evaluation (done 15 Oct 2026, `p5-eval` merged to `main` and pushed, `4bcd993`)
**P5 done-check (passed 15 Oct):** clean clone of `p5-eval` with `.env` copied: 181 tests pass, lint clean, `python -m oracle.run` reproduces `eval/expected/` exactly, `halyard build` twice gives identical output (3,889 nodes, 5,384 edges, 0 model calls), `halyard eval --only Q1,A-login --repeat 1` runs end to end (Q1 pass; A-login missed "the portal is gated", the same one-run gap seen in `E-2824e5be`).
Recorded result: **58 of 69 runs** (23 questions x 3): golden 32 of 36, adversarial 26 of 33. Full evals went 19 -> 47 -> 51 of 69 (`E-d583c183`, `E-2824e5be`, `E-07443f38`); 58 adds the Q5 and A-beer fixes re-run after the last one and a Q10 judge error. `docs/eval-report.md` is `E-07443f38` plus `eval/report_notes.md`; kept reports in `docs/eval-runs/`. Failure log F-P5-1 to F-P5-11.

**Built**
- Oracle (`oracle/`, from `docs/definitions.md` only): amended D-42 (no two examples share a normalised text), D-45 directions, `oracle/adversarial.py`, `answerable` and rubric in every expected file, Brewbird's genuine count on 22 Sep (26) and median genuine day (20).
- `eval/adversarial.yaml`: 11 questions (A-teams, A-subscription-reaction, A-subscription-usage, A-login, A-causation, A-injection (M11554), A-beer, A-stale, A-uae, A-reply, A-leading). Key `figures` for each question are paths into its expected file, in both YAMLs.
- `src/halyard/eval/`: `cases.py`, `grade.py` (figures at the answer's precision, words for small numbers; cited-ID precision/recall against the best-matching cited set, including parts of a result's breakdown; pass rule), `judge.py` (a met item counts only when its quote, or ellipsis-joined fragments, is in the answer), `runner.py`, `report.py` (`report_notes` for one eval). `halyard eval [--repeat 3] [--only ...] [--no-judge] [--second-judge MODEL] [--report E-id]`; an `--only` run writes its report to `outputs/eval/` (git-ignored); exits non-zero only when a run errors.
- `get_client(settings, "judge")`, `JUDGE_MODEL` in `.env` / `.env.example`; judge prompt `skills/eval/judge.md`. `gpt-6.1-sol` price in `config/llm_prices.yaml` ($2.00 in, $10.00 out per million).
- Tools: `mention_id_groups` on breakdown results (`count_mentions` with `group_by`, `complaint_breakdown`, `sentiment_trend`, `daily_activity`), kept in the log and run, never sent to the model; `daily_activity` `median_genuine_per_day`; `coverage` lists excluded posts matching the topic with reason, entity name and total for that reason.
- Skills: grounding rules 4 (decline: say there are no records, name each part declined), 7 (drafts for a person to approve), 11 (check the premise; say what is true instead), 12 (excluded is not absent); consumer rules 6 (unusual day: total vs median day, genuine vs median genuine day, burst accounts and span), 8 (every total with its author count), 9, 10 (reply drafts); competitor rules 4 (price history), 6 (nearest like-for-like comparison), 9 (SOV left-out sizes, sub-brand counts), 10 (what would establish cause), 11 (three lawful routes); answer format: a ranking gives its counts.

**Decisions by Abhinav (14 and 15 Oct)**
- Judge model `gpt-6-luna`, not `gpt-6.1-sol`; no full calibration run. A spot re-judge of 5 runs with `gpt-6.1-sol` agreed on 11 of 14 items (`docs/eval-runs/E-07443f38-rejudge-gpt-6.1-sol.json`).
- `answerable` stays in the answer but is not graded (the brief asks only that a question the data cannot answer is declined with the reason; rubric items check that).
- Rubric corrections where the expectation asked more than the question: Q11 credentials item dropped; A-beer key figure dropped; the two subscription items trimmed.
- Record 58 of 69 without a further full run.
- After a live run, report issues and propose fixes before changing anything (still applies).

## P6: outputs and packaging (15 Oct 2026, branch `p6-outputs`)
Built in a separate worktree (`../Market-Intelligence-agents-p6`) while P5 finished, then rebased onto `main` after the P5 merge. Each output reviewed by Abhinav before commit.

**Outputs** (all linked from the README's deliverables table)
- `docs/ontology-note.md`: why the graph is shaped this way, from the questions (hand-written; `docs/ontology.md` stays the generated reference).
- `skills/README.md`: the skills package guide: the four parts per agent, reusable vs Brewbird config (each `config/brewbird/*.yaml`), redeploy steps, limits of config-only (fixed input columns, tests check Brewbird figures, labels re-made), client asks needing core product changes (subscription connector, reply queue, same-day QA alerts, chat interface, pulse scheduler; the Filterhaus login is a boundary, not a product gap).
- `docs/replies.md`: Ishita (prompt injection M11554 named; reply queue with a person approving; no rule IDs), Kunal (portal terms; retail Rs 380/250 g as a ceiling, consented café conversations, ask Filterhaus), Dev (method first, then 1,183 posts -> 1,023 conversations -> 1,041 brand mentions; Brewbird 585 = 56%, naive 66%, Bluepeak 19% vs naive 9%). SOV divides by brand mentions (1,041), not conversations (1,023).
- `docs/readout.md` and `docs/readout.pdf` (one A4 page, Markdown -> HTML -> headless Chrome `--print-to-pdf`): finding = Nitro can defects (TST 0,0,0,0,7,9,13; 29 posts, 22 swollen/puffed, 7 flat/sour; 11 mention box/leak/delivery) hidden by steady brand sentiment; not Saltmarsh (0 of 57 negative Nitro posts name it, volume 30 a week). Metric: share of Nitro can-defect posts 12 to 18 Oct logged by QA within 24 hours, target 90%, baseline about 0 (Farah). "What success looks like": QA matches the defect to batches (Abhinav chose routing as the metric, batches as the success line).
- `docs/another-week.md`: daily QA alert, reply queue, run on the next export, competitor claim watch, per-team weekly scorecard, harden the agents, benchmark models and providers; not subscription data. Spend: $0.51 billed.
- `README.md` rewritten: one build command, agents, eval, `make demo`, deliverables table, "which key you need", how it works.

**Code and config changes (agreed)**
- Tool descriptions in `registry.py` name no client (no Saltmarsh/TST/beer examples); `price_compare` a/b "named as `brand_facts` returns it". Checked after the recorded eval: `E-8a88f98f` 7 of 7, `E-15aa5fe9` Q7/Q8 4 of 4 (noted in `eval/report_notes.md`; recorded 58 of 69 stands).
- `cached_input` price for `gpt-6-luna`; `cost_usd(..., cached_input_tokens)` used by `spend`, the answer footer and the eval runner. Eval report notes say E-07443f38's costs predate it (about 2.4x billed).
- `halyard build` calls `runtime.up` (starts Neo4j if needed; compose project name is fixed, so any folder reuses `halyard-neo4j`). `.env.example` sets `AGENT_MODEL=gpt-6-luna`.

**Known limits stated in the docs:** agents and eval need an OpenAI key (no Anthropic tool calling, no Gemini adapter); keep `LLM_PROVIDER=openai` and `LABEL_MODEL=gpt-6-luna` for a no-key build, or every text is re-labelled.

P6 done-check passed 15 Oct; `p6-outputs` merged to `main` and pushed (`e433b9b`); worktree removed.

**P6 follow-ups (15 Oct, branch `p6-followups`)**, from checking the README against the brief's "Evaluated on" lines:
- `docs/eval-answers.md`: expected (oracle) vs the agent's actual answer per question, with pass counts; `halyard eval --answers E-07443f38,E-db750b64,E-954d0a95` (`src/halyard/eval/answers.py`; a later eval's runs replace an earlier one's; needs the run transcripts in `outputs/runs/`). Linked from the README and the eval report header.
- `docs/failure-story.md`: one page in business language. The story is Q5 (22 Sep: 0 -> 2 -> 0 -> 1 -> 3 of 3 across five evals, including a regression from our own fix); Abhinav chose it over Q12 because Q12 passed only 1 of 3 in the recorded eval. Then a table of the other fixes, each labelled skill, tool, graph or eval definition. The full `failure-log.md` stays as it is.
- Monday pulse regenerated and linked from the README. Three `gpt-6-luna` runs each slipped one figure (a sign, a label, a mixed brand/brand-level series), so the pulse runs on `gpt-6.1-sol` (`PULSE_MODEL`, about $0.12 a pulse; `A-3fead7f7`, checked figure by figure). `pulse.md`: share of voice lists every brand as a table; the noise check runs from when the competitor activity began; a week-on-week change is described in plain words (the D-45 label only for a whole series, with its weeks); every figure names its week and what it measures. `pulse.py` no longer prints the claims list (result IDs mean nothing to the brief's readers); mention IDs stay inline and the claims stay in the transcript. Not logged in the failure log (Abhinav).
- Not done, by decision: a command to rebuild `docs/readout.pdf` (made once with headless Chrome); a numeric check of answers against tool results in the another-week note.
- **For Abhinav before submitting:** the GitHub repo is private; make it public or share it with the reviewers.

Next: P7 (clean-clone rehearsal and recording; add the recording link to the README). The `gpt-6.1-sol` agent comparison is deferred (Abhinav).
