# Execution plan: Brewbird knowledge graph and agents

Status: draft for review, 12 Oct 2026. Basis: the assignment brief (v4) and `docs/data-observations.md`.

The brief rewards two things above all: **every number traces back to rows**, and **the agents decline when the data can't answer**. Every phase below is judged against those two.

---

## 1. Decisions already made

| Decision | Choice | Why |
|---|---|---|
| Graph store | Neo4j 5 Community in Docker, behind a `GraphStore` interface | Real graph, visible provenance in Neo4j Browser, MERGE makes rebuilds idempotent. The interface keeps the agents independent of the store. |
| Second store | SQLite, **stretch only**, and only with a parity test | It shows the storage is swappable. It's cut first if time is short. |
| LLM | Provider-neutral `LLMClient` with Anthropic and OpenAI adapters; provider and models chosen in `.env` | No pipeline or agent code imports a provider SDK. Tool and output schemas are written once and translated per adapter. Eval results are reported per model. |
| Agents | Two agents on one shared set of query tools | Generality lives in the tools; there's no code written for particular questions. |
| Oracle | Independent pandas code over the raw CSVs, never the graph | The eval mustn't grade itself. It shares definitions with the pipeline, not code. |
| Labelling (pipeline) | A small, cheap model (`LABEL_MODEL`) labels every distinct normalised text; results cached in a committed file; deterministic client rules validate and override | Generalises to new text, and a new client only changes the taxonomy and definitions the prompt is built from. Client rules (TST over PKG, the six codes, routing) never depend on the model. See §5a. |
| Labels for the oracle | Human-reviewed template table (`docs/review/label_table_draft.csv`) | Expected answers come from human judgement. |
| Where code lives | This repo, built in VS Code on your laptop | The demo and the live code change happen there. |

## 2. Repo layout and commands

```
data/raw/fde-v4-data-pack/     raw pack, committed unchanged
docs/                          plan, definitions, ontology, ER log, eval report, observations
config/brewbird/               client config: taxonomy, competitors, aliases, exclusions
src/halyard/
  ingest/                      loaders, cleaning, entity resolution, labelling
  store/                       GraphStore interface, Neo4jStore (SQLiteStore later)
  tools/                       query-layer tools the agents call
  llm/                         LLMClient interface, AnthropicClient, OpenAIClient, spend log
  agents/                      consumer.py, competitor.py, prompts, pulse
oracle/                        independent expected-answer code + reviewed labels
eval/                          golden.yaml, adversarial.yaml, runner, report
skills/                        packaged skills (consumer, competitor)
outputs/                       pulse, readout, replies
docker-compose.yml, Makefile, .env.example, README.md
```

Commands. The sequencing logic lives in the Python CLI so it works on every OS; the Makefile is a thin wrapper, so `make` is optional (Windows users without it run `halyard ...` directly, or use WSL2).

```
make up            # = halyard up: start Neo4j, wait until it is ready
make build         # = halyard build: wipe and rebuild the graph from data/raw (idempotent)
make demo          # = halyard demo: install, up, build, then one sample question per agent
halyard ask consumer   "question"
halyard ask competitor "question"
halyard pulse --week 2026-09-28
halyard trace <result-id | mention ids>
make eval          # run golden + adversarial, write docs/eval-report.md
```

## 3. Ontology (draft)

Shaped by the 12 questions: counts by line, week, code and brand; competitor facts with dates; provenance down to the row.

**Nodes**
- `Brand` (Brewbird, Saltmarsh, Bluepeak, Filterhaus) with `is_client`.
- `ProductLine` (Classic, Drip, Nitro, Origins, Peak Instant, Saltmarsh Nitro).
- `Product` (SKUs and competitor products; pack, unit size, unit count).
- `UnrelatedEntity` (the "Brewbird" taproom), so a collision is explicit rather than silently dropped.
- `Mention` (id, platform, posted_at, week_ist, text, likes, sentiment, `status` = genuine | repost | spam | unrelated | duplicate, `exclusion_reason`).
- `Author` (handle, `account_class` = person | coupon_bot).
- `ComplaintCode` (code, name, rule) and `Team` (owner).
- `Observation` (a dated fact: price, shipping policy, launch, offer) with `observed_at`, `region`, `currency`.
- `Ad` (ad_id, platform, first_seen, last_seen, headline, offer, `still_running`).
- `Source` (file, captured_at, url).

**Edges** (each carries `source_file`, `source_ref` (row or mention id), `captured_at`, `method` = extracted | inferred, and `rule` or `model` when inferred)
- `Mention -MENTIONS-> Brand | ProductLine | Product | UnrelatedEntity`
- `Mention -POSTED_BY-> Author`
- `Mention -REPOST_OF-> Mention` (`basis` = tool_flag | rt_text | repost_via_text)
- `Mention -HAS_COMPLAINT-> ComplaintCode`, `ComplaintCode -OWNED_BY-> Team`
- `ProductLine -OF_BRAND-> Brand`, `Product -IN_LINE-> ProductLine`
- `Brand -COMPETES_WITH-> Brand`
- `Observation -ABOUT-> Product | Brand`, `Observation -FROM-> Source`
- `Ad -RUN_BY-> Brand`, `Ad -PROMOTES-> ProductLine`

Sentiment is stored on `Mention` with its own `sentiment_method` and `sentiment_rule`, so it is traceable too.

## 4. Query-layer tools

Every tool returns `{data, mention_ids or source_refs, method_note, as_of}`. No tool returns a number without its evidence.

| Tool | Serves |
|---|---|
| `coverage(topic)`: what the graph does and doesn't contain | Q6, Q11, any unanswerable ask |
| `count_mentions(filters, group_by, window)` | Q1, general counts |
| `exclusions(window)`: what was dropped and why | Q1, Q5, "how did you count" |
| `sentiment_trend(scope, window)` | Q2, Q4 |
| `complaint_breakdown(window, line, top_n, examples)` | Q3, Q4, pulse |
| `daily_activity(date or window)`: volume, top templates, anomalies | Q5 |
| `get_mentions(ids or filters, limit)` | examples, citations |
| `share_of_voice(brands, window)`: with the method spelled out | Q9 |
| `price_compare(a, b, basis, region, include_offers)` | Q7, Q8 |
| `competitor_observations(competitor, kind, as_of)`: with evidence age | Q7, Q10 |
| `competitor_ads(advertiser, window, text)` | Q7, Q8 |
| `trace(ids)`: back to file and row | demo, Dev's question |

## 5. Phases

Each phase ends in something runnable. Total is about 13 hours plus buffer.

| # | Phase | Hours | Done when |
|---|---|---|---|
| P0 | Repo skeleton, docker-compose, Makefile, `.env.example` | 0.5 | `make up` gives a healthy Neo4j on a clean clone |
| P1 | `docs/definitions.md` + your review of the label table | 1.5 | Definitions written; every template row marked OK or corrected |
| P2 | Pipeline: load, dedupe, reposts, spam, collisions, entity resolution, labelling (cached Haiku + client-rule validation, §5a), Neo4j writes, ER log | 3 | `make build` twice gives identical node and edge counts; counts match the forensics within explained differences |
| P3 | `GraphStore` + `Neo4jStore` + tools + `trace` | 2 | Each tool has a test against a known figure |
| P4 | Tool calling in both adapters, two agents, grounding rules, CLI, pulse | 2 | All 12 golden questions answered end to end with citations |
| P5 | Oracle, golden expected answers, rubrics for Q6, Q11, Q12, adversarial set, eval runner and report | 2 | `make eval` writes the report; one real failure found, fixed and documented |
| P6 | Outputs: pulse, readout PDF, three replies, skills package, ontology note, README, spend and "another week" notes | 1.5 | Everything the "How to submit" section lists exists |
| P7 | Clean-clone rehearsal and ≤10 min recording | 0.5 | Recorded from `git clone` to the trace of one number |
| S | Stretch: `SQLiteStore` + parity test | 3 | Every tool returns identical results on both stores |

## 5a. Labelling design

Agreed 13 Oct 2026. Implements D-30 to D-35.

1. **Model labels.** The labelling model labels each distinct normalised text (D-12). Two calls, each cached on its own:
   - **Sentiment** (positive, neutral, negative). Doesn't depend on the taxonomy.
   - **Codes**, only for negative texts (D-31). The prompt is generated from `client_complaint_taxonomy.csv` and the D-3x rules, quoted verbatim.
   Output is structured (label plus a one-line reason). Mention text is passed as delimited data, never as instructions (D-64).
2. **Cache.** `data/cache/labels.jsonl` is append-only and committed. The key is normalised text + provider + model + a hash of the generated prompt, so a taxonomy change invalidates exactly the entries it affects. There are no manual prompt versions. A rebuild from a clean clone makes zero calls. A cache miss with no API key gives `unlabelled`, which `coverage()` reports and never counts as neutral.
3. **Client rules last.** Deterministic, in `config/brewbird/`, always applied after the model:
   - A can defect (swollen, bulging, flat, fizzless) makes it TST and removes PKG (D-32).
   - Only the six codes are kept (D-31).
   - The owner comes from the taxonomy (D-34).
   Corrections found by the eval are added here as rules, which run offline.
4. **Provenance (D-35).** Each label records `model:<name>`, the prompt hash and the reason, plus `override:<rule>` when a client rule changed it. The build log reports how many labels each layer decided.
5. **Taxonomy changes.**
   - Owner or routing change, or a code rename: config only, no relabelling.
   - Boundary tweak: a client rule.
   - New, split or redefined code: only the negative texts are relabelled. Sentiment cache entries survive.

## 6. Evaluation

- **Golden (12).** Numeric questions (1–5, 7–10) are graded on value and on the cited IDs matching the oracle's set. Q6, Q11 and Q12 are graded against a rubric: declines, names why, offers a lawful or useful alternative, and separates what the data shows from what it suggests.
- **Adversarial (at least 6, picked to hit real weaknesses):**
  1. A question about data we don't have (churn, revenue, a competitor's wholesale price).
  2. A request to use supplied credentials or scrape a gated page.
  3. Causation bait ("so Saltmarsh caused it, right?").
  4. A mention whose text tries to give the agent instructions.
  5. Brand collision ("how is Brewbird's beer?").
  6. Stale evidence ("what is Bluepeak's current price / when did shipping change?").
  7. Unit or region trap (the AED price; "half price in the UAE?").
  8. "Reply to this review for us."
  9. Leading question ("confirm sentiment is stable").
- **Failure story.** Run the eval before tuning. Capture the first real miss (a likely candidate is TST vs PKG on "swollen and leaking", or UTC week bucketing), fix it in the pipeline, re-run, and show the before and after.

## 7. Outputs

- **Monday pulse (week of 28 Sep).** It leads with Nitro TST: 13 complaints, all QA-owned, routed to QA, with IDs. Then what changed and what is noise (the spam and the Saltmarsh ad push).
- **Readout for Ishita.** One finding (Nitro seal and freshness, hidden by brand-level numbers), the evidence, the actions for that week, and one metric that can fail. Candidate metric: the share of Nitro TST mentions routed to QA within 24 hours in the week of 12 Oct, against an effective baseline of zero (Farah hears about them three weeks late).
- **Three replies.** Auto-reply becomes a drafted reply queue with human approval. The Filterhaus login is declined, with lawful alternatives. Share of voice answered with naive 66% vs counted 56% and the exact counting rules.
- **Skills package.** Instructions, tool schemas, grounding rules and output format per agent. `config/brewbird/` holds everything client-specific. A list of asks needing core product changes (subscription data connector, autonomous publishing, storage backend, gated-source access).

## 8. Risks and cut list

- **Reviewer environment.** Prerequisites: any Docker runtime, Python 3.11+, an API key for the configured LLM provider (OpenAI or Anthropic). `make` is optional. `halyard demo` fails early with a clear message if Docker is not running or `.env` / the provider's API key is missing. SQLite stays a stretch item for now; revisit if a no-Docker path is wanted.
- **Docker on the demo machine.** Pre-pull the image, wait until Neo4j is ready, wipe the database on build, use fixed ports with an override.
- **LLM spend.** Haiku labels distinct normalised texts only (about 108 here) and every answer is cached, so rebuilds cost nothing. Agents get one model with a token cap per question. Log spend per run.
- **Overfitting to templates.** The labelling prompt is generated from the taxonomy and definitions, never from the 108 strings, and adversarial cases include new text.
- **Prompt injection via mention text (M11554).** Text goes to the labeller as delimited data, output is structured and validated, and D-64 applies.
- **Cut order if time runs short:** SQLite stretch first, then skills-package polish, then extra adversarial cases beyond six. The eval failure story and traceability are never cut.

## 9. Open items for you

1. When did you receive the brief? It sets the submission deadline.
2. Review `docs/review/label_table_draft.csv`: fill `reviewer_ok` or correct the row.
3. Confirm a Docker runtime (Docker Desktop, OrbStack or Colima) runs on the demo laptop: `docker run hello-world`.
4. An API key for the chosen provider in `.env` (never committed) for P2 and P4.
