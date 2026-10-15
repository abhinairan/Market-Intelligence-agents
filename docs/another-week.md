# Another week, and model spend

## What I would do with another week

In order of what it is worth to Brewbird:

1. **Daily can-defect alert to QA.** The readout's action, made automatic: a scheduled run
   each morning on a fresh export that lists new Nitro TST posts and sends them to QA, with
   their IDs. This is the step that moves the "same-day routing" metric. The scheduling and
   the connector to QA's tracker are Halyard product work; the query already exists.
2. **The reply queue.** One draft reply per negative post, grouped by complaint code, written
   to a review file that a person approves or edits. The agent already drafts a single reply
   on request; the queue is the batch version Ishita asked for, with a person still sending
   each one.
3. **Run it on the next export.** Load 5 to 18 October, rebuild and check the figures against
   a hand count, as was done for this pack. This tests that a new week needs no code change and
   gives the first reading of the metric.
4. **Competitor claim watch, for Kunal.** Each week, check every new competitor ad claim and
   price change like for like, as was done for Saltmarsh's "half the price", and flag any that
   are false or have newly become true. The price check exists; the new parts are reading
   the claims out of new ads and running it on a schedule over each new export.
5. **A weekly scorecard for each owner team.** QA, Logistics, Category, Growth and CX each get
   their own complaint codes, the trend and example posts every Monday. Today only QA's
   problem leads the readout, yet Logistics has 16 delivery complaints and Category 23 price
   complaints in the last three weeks. This reuses the Monday pulse with a section per team.
6. **Harden the agents.** Add more adversarial questions, in wording the skills have not seen,
   and keep tuning the agents and tools against them. Run the eval with a scripted model on
   every change and live once a night.
7. **Benchmark the models.** Everything ran on `gpt-6-luna`. Run the labeller, the agents and
   the eval judge on a more capable model and on models from other providers, and compare
   labels, eval results and cost, to see whether a different model changes any answer.
   (Agents on Anthropic models first need tool calling added to the Anthropic adapter, which
   today covers labelling only.)

**What I would not do in that week:** connect subscription data. Dev's cancellation question needs
the client's order system and a consented way to match customers to posts; that is a scoping
conversation with Brewbird and Halyard's product team, not a week of building.

## Model spend

**Total: $0.51, as billed by OpenAI** for the whole build. Our own usage log
(`outputs/llm_usage.jsonl`, reported by `halyard spend`) gives $0.45 at the prices in
`config/llm_prices.yaml`: `gpt-6-luna` $0.10 per million input tokens, $0.01 per million
cached input tokens and $0.50 per million output tokens; `gpt-6.1-sol` $2.00 in and $10.00 out.
The $0.06 gap is the part the log cannot see: OpenAI counts about 5% more tokens than we
logged, and charges cache writes slightly above the input rate.

| Use | Model | Calls | Cost (our log) |
|---|---|---|---|
| Labelling the mentions | `gpt-6-luna` | 194 | $0.011 |
| Agents: building, tuning and the eval runs | `gpt-6-luna` | 887 | $0.347 |
| Eval judge | `gpt-6-luna` | 199 | $0.067 |
| Judge spot check | `gpt-6.1-sol` | 5 | $0.020 |
| Model check | `gpt-6.1-sol` | 1 | under $0.001 |

Most of it went on running the evaluation repeatedly, which is where it should go.

**Why it is low:**

- **Labels are made once.** The label model sees each distinct text once (83 here, after
  normalisation folds repeats and reposts together), and every answer is cached in
  `data/cache/labels.jsonl`. Rebuilding the graph makes no model calls and costs nothing.
- **Agents get only what they need.** Each agent gets only its own tools; results send at most
  20 mention IDs to the model, with the full list kept in the log; each question is capped at
  8 turns and 80,000 tokens.
- **Prompt caching.** The skill and tool definitions form a fixed prefix, so 78% of agent input
  tokens were read from the cache, at a tenth of the input price.

**Running it for Brewbird:** an agent question costs about $0.001 (at most $0.003), the Monday
pulse under a cent, a full eval (23 questions, three times each, with the judge) about $0.09,
and labelling a new week's texts a fraction of a cent. At this volume, daily use costs well
under a dollar a month.
