# Skills

Everything a model is told lives here, apart from the code and apart from the client config.

| Folder | What it is |
|---|---|
| `labelling/` | The label model's prompts (see its README). |
| `consumer/SKILL.md` | The consumer intelligence agent's instructions and tool list. |
| `consumer/tools.json` | Its tool schemas, generated from the registry. |
| `shared/grounding.md` | Grounding rules every agent follows (D-60 to D-64). |
| `shared/answer_format.md` | The output format every agent uses. |

An agent skill is one `SKILL.md`: front matter with the agent's `name`, `description` and
the `tools` it may call, then its instructions. `{{name}}` marks a slot filled when the
agent starts (`src/halyard/agents/skills.py`): `client`, `brand`, `window_start`,
`window_end` and `as_of` come from the client config and the graph; `grounding` and
`answer_format` are the shared files. Skills name no brand, product or date themselves, so
a new client needs no change here.

Each agent folder also has a `tools.json`: the schemas of the tools that agent is offered,
exactly as the model is sent them, with the `answer` tool last. It is generated from the tool
registry (`src/halyard/tools/registry.py`) by `halyard skills`; never edit it by hand. A test
fails if it differs from the registry. The descriptions in it are what the model uses to pick
a tool for a question; the skill's instructions add the order to work in.

The answer's schema is in `src/halyard/agents/answer.py`. The grounding rules on citations
are also enforced in code (`src/halyard/agents/citations.py`): an answer citing an ID that
no tool returned in that run is rejected.
