# Market intelligence agents

A brand knowledge graph and two agents over it, built for Brewbird Coffee Co. (FDE take-home
v4). A pipeline turns the client's raw data pack into a Neo4j graph where every node and edge
records its source. A consumer agent and a competitor agent answer questions through query
tools, and every figure in an answer cites the posts or rows behind it.

## Prerequisites

- A Docker runtime: Docker Desktop, OrbStack, Colima, or Docker Engine on Linux.
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- An OpenAI API key, for the agents and the eval. Building the graph needs no key: every label
  is in the committed cache. The agents' tool calling is implemented for OpenAI only; the
  Anthropic adapter covers labelling.
- `make` is optional. On Windows, use WSL2.

## Setup

```
uv sync
cp .env.example .env          # then set OPENAI_API_KEY in .env
```

**Which key you need.** Building and querying the graph (`build`, `tool`, `trace`) needs no
key, as long as `.env` keeps `LLM_PROVIDER=openai` and `LABEL_MODEL=gpt-6-luna`: every label
is cached under that provider and model. Changing them re-labels every text with the new
model, which can change the counts. The agents, the pulse and the eval (`ask`, `pulse`,
`demo`, `eval`) need an OpenAI key; tool calling for Anthropic and Gemini models is not built
yet.

## Build the graph (one command)

```
uv run halyard build
```

Starts Neo4j if it is not running, then wipes and rebuilds the graph from
`data/raw/fde-v4-data-pack/` and prints the counts: 1,904 mentions, 3,889 nodes and
5,384 edges, with 0 model calls. Running it twice gives the same graph. Neo4j's browser is at
http://localhost:7474 (user `neo4j`, password from `.env`).

## Run the agents

```
uv run halyard ask consumer "Is anything going wrong that the brand-level numbers are hiding?"
uv run halyard ask competitor "Is Saltmarsh's \"half the price\" claim accurate?"
uv run halyard pulse --week 2026-09-28    # the Monday pulse, written to outputs/
```

Each answer ends with its claims and the IDs they cite. Add `--json` to `ask` for the raw
answer. Any ID in an answer traces back to its file and row:

```
uv run halyard trace M10149 R-xxxxxxxx
```

## Run the evaluation

```
uv run halyard eval                        # 12 golden + 11 adversarial questions, 3 runs each
uv run halyard eval --only Q3,A-login --repeat 1
```

Grades each answer against expected answers computed independently by the oracle in `oracle/`
(pandas over the raw CSVs, never the pipeline's code): key figures, cited IDs, rubric items
marked by an LLM judge, and whether the question was declined when the data cannot answer it.
A full run takes about 25 minutes and costs about $0.09. The recorded result is in
[`docs/eval-report.md`](docs/eval-report.md).

## Everything at once

```
make demo        # or: uv run halyard demo
```

Starts Neo4j, builds the graph, asks one golden question of each agent (Q4 and Q8), writes the
Monday pulse and prints the model spend. Other commands: `halyard spend` (tokens and cost),
`halyard tool` (list or run a query tool), `halyard down [--wipe]`, `uv run pytest`.

## Deliverables

| What the brief asks for | Where |
|---|---|
| Ontology note | [`docs/ontology-note.md`](docs/ontology-note.md), with the generated reference [`docs/ontology.md`](docs/ontology.md) |
| Entity-resolution log | [`docs/er-log.md`](docs/er-log.md) |
| Evaluation report | [`docs/eval-report.md`](docs/eval-report.md); expected and actual answer for each question in [`docs/eval-answers.md`](docs/eval-answers.md); the fixes it led to in [`docs/failure-log.md`](docs/failure-log.md) |
| Monday pulse, week of 28 September | [`outputs/pulse-2026-09-28.md`](outputs/pulse-2026-09-28.md) |
| Readout for Ishita | [`docs/readout.pdf`](docs/readout.pdf) |
| Three written replies | [`docs/replies.md`](docs/replies.md) |
| Another week, and model spend | [`docs/another-week.md`](docs/another-week.md) |
| Skills package | [`skills/`](skills/README.md): each agent's instructions, tool definitions, grounding rules and output format; Brewbird's configuration in [`config/brewbird/`](config/brewbird/) |
| Recording | to follow |

The counting rules every number follows are in [`docs/definitions.md`](docs/definitions.md),
each with an ID (D-xx) that the code and the answers cite.

## How it works

```
data pack (CSVs, saved pages)
  -> pipeline: load, clean (duplicates, reposts, spam), resolve entities, label with a model
  -> Neo4j graph: every node and edge with its source file, row and method
  -> twelve query tools: counts, trends, complaints, share of voice, prices, coverage, trace
  -> agents: consumer and competitor, each with its own skill and tool set
  -> citation check: an answer citing anything a tool did not return is rejected
```

- `src/halyard/ingest/`: the pipeline. `src/halyard/store/`: the graph schema and Neo4j.
  `src/halyard/tools/`: the query tools. `src/halyard/agents/`: the agent loop and citation
  check. `src/halyard/eval/`: the eval runner and graders.
- Labels are made once per distinct text and cached in `data/cache/labels.jsonl`, so rebuilds
  cost nothing.
- Everything specific to Brewbird is in `config/brewbird/` and the data pack; a new brand gets
  its own config folder and data, with no code change (see [`skills/README.md`](skills/README.md)).

The agents keep Halyard's boundaries: they draft but never post, use only public or
client-provided data, and decline what the data cannot answer, saying what would be needed.
