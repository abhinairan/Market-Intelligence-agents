# Market intelligence agents

Knowledge graph and two agents for the Brewbird take-home. See `docs/PLAN.md`.

## Prerequisites

- A Docker runtime: Docker Desktop, OrbStack, Colima, or Docker Engine on Linux
- Python 3.11+
- An Anthropic API key (copy `.env.example` to `.env` and fill it in)
- `make` (optional). On Windows, use WSL2, or run the `halyard` commands directly.

## Quick start

```
make demo        # or: halyard demo
```

This installs the package, starts Neo4j, builds the graph and runs a sample question per agent.
