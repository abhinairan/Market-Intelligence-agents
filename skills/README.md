# Skills

Everything a model is told lives here, apart from the code and apart from the client config.
This folder is the reusable part of the agents. A new brand gets a new `config/<client>/`
folder and its own data pack; nothing here changes.

| Folder | What it is |
|---|---|
| `labelling/` | The label model's prompts (see its README). |
| `consumer/SKILL.md` | The consumer intelligence agent's instructions and tool list. |
| `consumer/tools.json` | Its tool schemas, generated from the registry. |
| `competitor/SKILL.md` | The competitor intelligence agent's instructions and tool list. |
| `competitor/tools.json` | Its tool schemas, generated from the registry. |
| `consumer/pulse.md` | The consumer agent's second skill: the Monday pulse, a one-page weekly brief (`halyard pulse --week`). |
| `consumer/pulse.tools.json` | Its tool schemas, generated from the registry. |
| `shared/grounding.md` | Grounding rules every agent follows (D-60 to D-64). |
| `shared/answer_format.md` | The output format every agent uses. |
| `eval/judge.md` | The eval judge's prompt: marks each rubric item met or not, quoting the answer (`halyard eval`). Not an agent. |

## The package for each agent

Each agent is one skill in four parts. The consumer agent and the competitor agent differ
only in their instructions and their tool list; the agent loop is the same code.

| Part | Consumer agent | Competitor agent | Monday pulse |
|---|---|---|---|
| Instructions | `consumer/SKILL.md` | `competitor/SKILL.md` | `consumer/pulse.md` |
| Tool definitions | `consumer/tools.json` | `competitor/tools.json` | `consumer/pulse.tools.json` |
| Grounding rules | `shared/grounding.md` | `shared/grounding.md` | `shared/grounding.md` |
| Output format | `shared/answer_format.md` and the `answer` tool | the same | `shared/answer_format.md` and the brief layout in `pulse.md` |

An agent's main skill is its `SKILL.md`: front matter with the agent's `name`,
`description` and the `tools` it may call, then its instructions. An agent can have more
skills in the same folder, one file each, in the same form (the consumer agent's
`pulse.md`). `{{name}}` marks a slot filled when the
agent starts (`src/halyard/agents/skills.py`): `client`, `brand`, `window_start`,
`window_end` and `as_of` come from the client config and the graph; `grounding` and
`answer_format` are the shared files. Skills name no brand, product or date themselves, so
a new client needs no change here. A test enforces this.

Each agent folder also has a `tools.json`: the schemas of the tools that agent is offered,
exactly as the model is sent them, with the `answer` tool last. It is generated from the tool
registry (`src/halyard/tools/registry.py`) by `halyard skills`; never edit it by hand. A test
fails if it differs from the registry. The descriptions in it are what the model uses to pick
a tool for a question; the skill's instructions add the order to work in.

The answer's schema is in `src/halyard/agents/answer.py`. The grounding rules on citations
are also enforced in code (`src/halyard/agents/citations.py`): an answer citing an ID that
no tool returned in that run is rejected.

## What is reusable and what is Brewbird's

| Reusable (Halyard) | Brewbird configuration | Brewbird data |
|---|---|---|
| `src/halyard/`: loaders, hygiene, entity resolution, labelling, graph builder, the twelve query tools, agent loop, citation check, eval runner and graders | `config/brewbird/*.yaml` (below) | `data/raw/fde-v4-data-pack/`: the client's export, as it arrived |
| `skills/`: agent instructions, grounding rules, output format, labelling prompts | | `data/cache/labels.jsonl`: model labels for this pack's texts |
| `docs/definitions.md`: the D-rules (the parameters they use are in config) | | `eval/`, `oracle/`: questions and expected answers for this client |

What each Brewbird config file holds:

| File | What it holds | Example from Brewbird |
|---|---|---|
| `client.yaml` | Client name, data pack, timezone, reporting week, window and as-of date, thresholds (staleness, spikes, sentiment, price-claim tolerance), agent limits, file names, city tags, catalogue currency and market | `timezone: "+05:30"`, `stale_after_days: 90`, `claim_tolerance: 0.05` |
| `entities.yaml` | The competitor set and how each brand is recognised: names, handles, sub-brands, line terms, name collisions, ambiguous cases, implied references | Peak Instant counts for Bluepeak (ER-01); the Pune taproom is unrelated (ER-09) |
| `labels.yaml` | Sentiment classes and rules, complaint-code rules, and client rules applied after the model | Swollen or flat cans are TST, never PKG (Farah's rule, D-32) |
| `hygiene.yaml` | Normalisation, repost markers, spam-burst thresholds, double posts | 5 handles posting the same promo within 6 hours is spam (D-13) |
| `observations.yaml` | Patterns that read dated facts (prices, shipping thresholds, launches, offers) from saved pages | "Free shipping above Rs `<n>`" gives a shipping threshold |
| `coverage.yaml` | What the data pack does not contain, what would answer it, and the nearest thing it can show | No subscription or order data; no trade prices |

The complaint taxonomy, owner teams, routing rules, product catalogue and aliases are not in
config: they come from the client's own files in the data pack and are used as they are.

## Redeploying for a new brand

1. Put the new client's export in `data/raw/<pack>/` in the same files and columns as this
   pack (see the limits below).
2. Copy `config/brewbird/` to `config/<client>/` and go through each file in the table above.
   Most of the work is `entities.yaml` (who the competitors are and how people name them)
   and `coverage.yaml` (what this client's data cannot answer).
3. Set `HALYARD_CLIENT=<client>` in `.env`.
4. `halyard label`: labels the new texts. This needs the API key; each distinct text is
   labelled once and cached.
5. `halyard build`: builds the graph and prints counts. Read the exclusions and the
   unresolved mentions before trusting any number.
6. `halyard ask consumer "..."` and `halyard ask competitor "..."`. No skill changes.
7. Write `eval/` questions and expected answers for the new client, then `halyard eval`.
   The eval runner, graders and judge are reusable; the oracle in `oracle/` was built for
   this pack and is not.

## Limits of "configuration only"

What a new brand would hit today, stated plainly:

- **The input format is fixed.** The loaders expect this pack's files and column names,
  including `price_inr` in the catalogue. A client whose export uses other columns, or a
  catalogue priced in another currency, needs a column mapping. That is a small core change
  (a mapping in config read by the loaders), not configuration.
- **Tool descriptions use Brewbird examples.** Some parameter descriptions in the registry
  say "e.g. `Saltmarsh`" or "e.g. `TST`". They change nothing in how a tool works, but the
  model sees them. They should be made generic, or filled from config like the skills' slots.
- **Tests check Brewbird's figures.** The unit tests run on this pack. A new client needs its
  own checks of the counts, as `docs/data-observations.md` did here.
- **Labels are re-made, not re-used.** The cache key includes the prompt, and the prompt
  includes the client's rules, so a new client's texts are labelled afresh.

## What the client asked for that needs a change to Halyard's core product

Configuration can't deliver these. Each needs product work, and each is said to the client
as such.

| Ask (who) | Why config can't do it | What the product would need |
|---|---|---|
| Whether the people complaining about Nitro are cancelling (Dev) | The pack has no subscription or order data, and nothing links a social handle to a customer account | A connector for the client's subscription and order system, and a consented way to match customers to posts. Until then, the agents say they cannot answer and show what they can (D-60). |
| Reply to bad reviews automatically (Ishita) | Halyard does not publish on its own: a person approves anything that reaches a customer (D-63) | A reply queue: the agent drafts, a person approves, and the product posts through each platform's API. The drafting is already in the consumer skill (rule 10, grounding rule 7); the queue, approvals and posting are product. |
| Tell QA about swollen cans the day they appear (Farah) | The agents answer when asked and the pulse runs weekly; nothing pushes an alert | A scheduled run and a connector to QA's tracker or messaging, so TST complaints reach QA the same day. |
| Ask questions herself (Ishita) | Today the agents run from a command line | A chat interface over the same agents, with the citations clickable back to posts. |
| Monday pulse without six hours of spreadsheet work (Dev) | The pulse is one command, but someone has to run it | A scheduler that runs `halyard pulse` each Monday and delivers the brief. |

Not a product change, and not something Halyard will do: using a friend's login to pull
Filterhaus's trade-portal prices (Kunal). Credentials are personal to the account holder and
the portal is gated (D-62). If Filterhaus shares a price list with Brewbird, or a café gives
consent to share theirs, it loads like any other competitor price: that is data, not product.

Delivered by configuration, as asked: Brewbird's own complaint codes and owner teams, used as
they are (Dev, Farah); TST over PKG for cans (Farah); share of voice with the counting shown
(Dev); the Saltmarsh "half the price" check (Kunal).

Internal product work, not asked for by the client: a second storage backend (SQLite, so
the build needs no Docker), and tool calling through the Anthropic adapter (today the agents
call tools through OpenAI only; Anthropic covers labelling).
