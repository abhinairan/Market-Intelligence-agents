# CLAUDE.md

Brewbird take-home for Zocket (FDE assignment v4): a brand knowledge graph (Neo4j) and two agents (consumer, competitor) over it. The brief PDF is in `docs/` (git-ignored, not ours to publish).

## Read first
- `docs/PLAN.md`: execution plan, phases P0 to P7, ontology, tools, eval. **§5a is the agreed labelling design.**
- `docs/definitions.md`: the rulebook (D-xx rule IDs). **Implement the D-rules from this file, never from `oracle/`.** The pipeline and the oracle must stay independent: they share definitions, not code. Cite rule IDs in code comments.
- `docs/data-observations.md`: forensics pass with the reference figures to check against.
- `docs/er-log.md`: entity-resolution log (ER-xx), to be kept in step with the pipeline.
- `docs/review/label_table_draft.csv`: human-reviewed labels for the oracle only (P5). The pipeline never reads it. Abhinav checked it but left `reviewer_ok` blank; treat it as reviewed.

## Working agreements
- One branch per phase, merged to `main` when the phase's "Done when" passes. `main` must always run from a clean clone. Commit only when asked or at the end of an agreed step. Never commit `.env`.
- After each P2 step, stop and give Abhinav a short walkthrough of the changes before moving on.
- Keep answers concise. Abhinav prefers a recommendation over a survey of options.
- Client facts come from the data pack via loaders; our judgement calls and parameters go in `config/brewbird/*.yaml`; code holds only generic logic (a new brand = new config + data, no code change).

## Decisions made in chat (not all obvious from the docs)
- **Docker runtime:** OrbStack on this Mac. Neo4j `5.26-community` via `docker-compose.yml`.
- **LLM:** provider-neutral `LLMClient` (`src/halyard/llm/`). `.env` sets `LLM_PROVIDER=openai`, `LABEL_MODEL=gpt-6-luna`, `AGENT_MODEL=gpt-6.1-sol`. Anthropic adapter exists too. No pipeline/agent code imports an SDK directly; use `get_client(settings, "label" | "agent")`.
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
```
`halyard demo | ask | pulse | trace | eval` exist as stubs that fail with the phase they belong to.

## Progress (as of 13 Oct 2026)
- **P0 done**, merged and pushed to `main` (`a9a5089`): skeleton, compose, Makefile, CLI, `config/brewbird/client.yaml`.
- **P2 done**, merged to `main` (not pushed). Branch `p2-pipeline`:
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

## Next steps: P3 on branch `p3-tools` (created from `main`, nothing built yet)
`main` with P2 is pushed. Stop after each step with a short walkthrough, as in P2.

**Approach (proposed 13 Oct, awaiting Abhinav's go-ahead on the three choices below)**
- Every tool returns `{data, mention_ids or source_refs, method_note, as_of}`.
- `GraphStore` (`src/halyard/store/`) has a few read methods (mentions, observations, ads, sources, one node with its edges); `Neo4jStore` implements them in Cypher. Counting is done in Python in the tools (`src/halyard/tools/`), so a second store only needs the read methods.
- Tools count `status = genuine` unless `include_excluded` is set (D-16). Shared helpers for windows (D-03, IST) and filters (brand, line, platform, city, sentiment, code). Tools take parameters; none is written for a particular golden question.

**P3 step 1 done (13 Oct, not committed):** `src/halyard/store/graph_store.py` (`GraphStore` protocol with five reads: `mentions`, `observations`, `ads`, `nodes(label)`, `node(label, key)`; row types; `MemoryStore` over the in-memory graph, so tool tests need no database), `src/halyard/store/neo4j_store.py` (`Neo4jStore`, the only Cypher in the query layer), `src/halyard/tools/base.py` (`ToolContext`, `ToolResult`, `ToolError`), `tools/windows.py` (`resolve_window`, `weeks_in`), `tools/filters.py` (`Names`, `MentionFilter`, `select_mentions`, `brand-level` as a line filter), `tests/test_store.py`. 76 tests pass; the Neo4j store returns exactly what the memory store returns.

**P3 step 2 done (13 Oct, not committed):** `src/halyard/tools/mentions.py` (`count_mentions`, `get_mentions`, `exclusions`, `daily_activity`; each takes a `MentionFilter` and a `Window`), `tools/context.py` (`ToolContext`, reads mentions and names once per run), `tools/registry.py` (`TOOLS` with name, description and JSON Schema per tool; `run_tool(ctx, name, args)` is the only way a tool is called, and logs to `outputs/tool_calls.jsonl` with a deterministic `R-xxxxxxxx` result ID), `anomaly_median_multiple` in `client.yaml` (D-43), `tests/test_tools_mentions.py`. 84 tests pass. No tool defaults to the client brand: brand is always explicit and echoed in `data.filters`. 22 Sep is 132 mentions = 84 spam + 41 genuine + 4 reposts + 3 unrelated (the forensics' "48 organic" is everything but spam).

**Steps and the figures each is tested against**
1. `GraphStore`, `Neo4jStore`, result shape, window and filter helpers (last 3 weeks = 14 Sep to 4 Oct).
2. `count_mentions`, `get_mentions`, `exclusions`, `daily_activity` (987 by line; 84 spam, 70 reposts, 42 taproom, 22 pop-up; 22 Sep = 84 spam + 48 organic).
3. `sentiment_trend`, `complaint_breakdown` (Nitro net -.27 and 63% negative in the last week; TST 36, 29 on Nitro; week of 21 Sep flagged for negative like share, D-40).
4. `share_of_voice` with reach (counted 56/20/19/5; naive 66% only when `compare_naive` is set, D-41, D-44).
5. `price_compare`, `competitor_observations`, `competitor_ads` (Rs 90 vs Rs 110 a can, ratio 0.82; match on region first, then currency, and refuse the AED row, D-53; Bluepeak 499 to 799 as a date range, D-51; 14 Saltmarsh Nitro ads still running, D-54).
6. `coverage`, `trace`, `halyard trace` (M10149 traces to rows 158 and 159; coverage reports no subscription or wholesale data).
7. Done-check (a passing test per tool), merge to `main`.

**Choices (1 decided by Abhinav 13 Oct; 2 and 3 built in step 2 as proposed, on his go-ahead)**
1. Decided: naive SOV (name matching over all 1,922 raw rows) is computed inside `share_of_voice` but shown only on request (`compare_naive`, default off). The brief asks for the counted figure and how it was counted (Q9, Dev), not for the comparison. D-41 updated.
2. Each tool call is logged to `outputs/tool_calls.jsonl` with a short result ID; `halyard trace` accepts mention IDs, ad IDs, observation keys and result IDs.
3. Each tool's name, description and parameter schema is written now in a registry next to the tools, for P4 to plug into both LLM adapters.

**Decided by Abhinav 13 Oct, to carry into P4**
- Tools keep the brand explicit (no default inside a tool). The agent skill says: when a question names no brand, use the client brand, and say so in the answer.
- The full list of mention IDs stays in the tool-call log under the result ID; the agent is sent a capped list plus the result ID. A follow-up question must be able to get the IDs back from a result ID (e.g. `get_mentions` or `trace` taking a result ID).

After P3: P4 (tool calling in both adapters, two agents, CLI, pulse), P5 (oracle, eval).
