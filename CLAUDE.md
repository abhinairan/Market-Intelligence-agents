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
`halyard build | demo | ask | pulse | trace | eval` exist as stubs that fail with the phase they belong to.

## Progress (as of 13 Oct 2026)
- **P0 done**, merged and pushed to `main` (`a9a5089`): skeleton, compose, Makefile, CLI, `config/brewbird/client.yaml`.
- **Branch `p2-pipeline`** (not pushed), on top of `main`:
  - `a272030` PLAN §5a + D-35 rewrite (model-first labelling)
  - `3ea1759` provider-neutral LLM settings; exact brief filename in `.gitignore`
  - `6753896` **P2 step 1 done**: `LLMClient` + OpenAI/Anthropic adapters, usage log `outputs/llm_usage.jsonl`, `halyard llm-check` (live check passed)
  - plus this CLAUDE.md
  - **P2 step 2 done**: loaders in `src/halyard/ingest/` (`records.py`, `loaders.py`, `load_pack(client)`), pack file names and `city_tags` in `client.yaml`, `tests/test_loaders.py`
  - **P2 step 3 done**: `src/halyard/ingest/hygiene.py` (`run_hygiene(mentions, client)`: normalised text, reposts, spam bursts, double posts), `config/brewbird/hygiene.yaml`, `tests/test_hygiene.py`. Normalisation gives 93 distinct texts; the forensics' 108 counted the 15 `RT @` variants separately.
  - **P2 step 4 done**: `src/halyard/ingest/entities.py` (`resolve_entities`, `mention_status`), `config/brewbird/entities.yaml`, `tests/test_entities.py`, counts added to `docs/er-log.md`. 987 genuine and the SOV counts match the forensics. Decided: the 34 "Brewbird beans" mentions stay brand-level (ER-18), so Classic is 246 and brand-level 152; the reviewed table row was changed to match.
  - **P2 step 5 done**: `src/halyard/ingest/labelling.py` (`Labeller`, `LabelCache`), `src/halyard/ingest/pipeline.py` (`prepare(settings)` runs steps 2 to 5), `halyard label`, prompts in `skills/labelling/` (Abhinav asked for prompts in skill files, not code), rules in `config/brewbird/labels.yaml`, cache `data/cache/labels.jsonl` (109 answers for 83 texts, openai/gpt-6-luna). Codes only for negative texts about the client; competitor complaints get sentiment only (decided by Abhinav). Nitro TST by week and last-3-weeks codes match the forensics exactly. D-30 gained a rule at Abhinav's request (regular use, rebuying or stocking up is positive), which moved one text ("stocked the fridge...", 30 mentions) from neutral to positive; nothing else changed.

## Next steps (P2, on `p2-pipeline`)
2. **Loaders** (`src/halyard/ingest/`): typed records for every file in the pack (mentions, products, taxonomy, pricing, ads, snapshots, brand site) with source file + row number provenance. Keep `posted_at` as exported; add `date_ist`, `week_ist` (Monday-named), `city`. Record row numbers of every byte-identical duplicate (D-10).
3. **Mention hygiene:** dedupe (D-10), reposts by tool flag / `RT @` / `#repost via`, linked to the quoted handle's earlier mention with the same normalised text (D-11, D-12), spam bursts (D-13), double posts (D-17). Config in `config/brewbird/hygiene.yaml`.
4. **Entity resolution:** Brewbird reference (D-20; plain "BB"/"BB50" is not one), competitors incl. Peak Instant → Bluepeak (D-21), taproom as `UnrelatedEntity` (D-22), Bandra pop-up ambiguous (D-23), product lines (D-24), two-brand mentions (D-25). Config in `config/brewbird/entities.yaml`. Keep `docs/er-log.md` in step.
5. **Labelling** per PLAN §5a; client rules in `config/brewbird/labels.yaml`. First run fills and commits the cache.
6. **Graph write:** Neo4j MERGE writes with provenance on every edge (`source_file`, `source_ref`, `captured_at`, `method` extracted|inferred, `rule`/`model`); `halyard build` wipes and rebuilds.
7. **Done-check:** two builds give identical node/edge counts; counts match the forensics (987 genuine conversations: Classic 246, Nitro 211, Origins 203, Drip 175, brand-level 152 (forensics had 280 / 118 before ER-18); Nitro TST by week 0,0,0,0,7,9,13; SOV last 4 weeks 56% counted vs 66% naive) or differences are explained. Then merge to `main`.

After P2: P3 (GraphStore, Neo4jStore, query tools, `trace`, a test per tool against a known figure), P4 (tool calling in both adapters, two agents, CLI, pulse), P5 (oracle, eval).
