# Market intelligence agents

Knowledge graph and two agents for the Brewbird take-home. See `docs/PLAN.md`.

## Prerequisites

- A Docker runtime: Docker Desktop, OrbStack, Colima, or Docker Engine on Linux
- Python 3.11+
- An OpenAI API key (copy `.env.example` to `.env` and set `OPENAI_API_KEY`). The agents' tool
  calling is implemented for OpenAI only; the Anthropic adapter covers labelling. Building the
  graph needs no key: every label is in the committed cache.
- `make` (optional). On Windows, use WSL2, or run the `halyard` commands directly.

## Quick start

```
make demo        # or: halyard demo
```

This installs the package, starts Neo4j, builds the graph, asks one golden question of each
agent (Q4 and Q8), writes the Monday pulse to `outputs/pulse-2026-09-28.md` and prints the
model spend.

```
halyard build                                # wipe and rebuild the graph; prints counts
halyard ask consumer "<question>"            # consumer agent; add --json for the raw answer
halyard ask competitor "<question>"          # competitor agent
halyard pulse --week 2026-09-28              # the Monday pulse for a reporting week
halyard trace M10149 R-xxxxxxxx              # any ID in an answer back to its file and row
halyard spend                                # tokens and cost from outputs/llm_usage.jsonl
```
