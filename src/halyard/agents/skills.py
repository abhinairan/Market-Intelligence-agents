"""Agent skills: instructions and a tool list read from `skills/<agent>/`.

An agent's main skill is `SKILL.md`. An agent can have more, one file each (the consumer
agent's `pulse.md`), each with its own tool list and its own generated tool schemas.

The skill text names no client. Its `{{slots}}` are filled here from the client config, the
graph and the shared skill files, so the same skill serves any client.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from halyard.agents.answer import ANSWER
from halyard.agents.loop import AgentSpec
from halyard.settings import PROJECT_ROOT, HalyardError
from halyard.tools.context import ToolContext
from halyard.tools.registry import TOOLS

SKILLS_DIR = PROJECT_ROOT / "skills"
SKILL_FILE = "SKILL.md"
TOOLS_FILE = "tools.json"
MAIN = "SKILL"  # the main skill's file stem
SHARED = {"grounding": "shared/grounding.md", "answer_format": "shared/answer_format.md"}
SLOT = re.compile(r"\{\{(\w+)\}\}")


def agent_names(skills_dir: Path = SKILLS_DIR) -> list[str]:
    return sorted(p.parent.name for p in skills_dir.glob(f"*/{SKILL_FILE}"))


def skill_files(skills_dir: Path = SKILLS_DIR) -> list[tuple[str, str]]:
    """(agent, skill) for every skill of every agent; the main skill is `MAIN`."""
    return [
        (agent, path.stem)
        for agent in agent_names(skills_dir)
        for path in sorted((skills_dir / agent).glob("*.md"))
    ]


def skill_path(agent: str, skill: str = MAIN, skills_dir: Path = SKILLS_DIR) -> Path:
    return skills_dir / agent / f"{skill}.md"


def tools_path(agent: str, skill: str = MAIN, skills_dir: Path = SKILLS_DIR) -> Path:
    name = TOOLS_FILE if skill == MAIN else f"{skill}.{TOOLS_FILE}"
    return skills_dir / agent / name


def load_skill(
    name: str, ctx: ToolContext, skill: str = MAIN, skills_dir: Path = SKILLS_DIR
) -> AgentSpec:
    """Agent `name` with one of its skills, its slots filled for this client."""
    path = skill_path(name, skill, skills_dir)
    if not (skills_dir / name / SKILL_FILE).exists():
        raise HalyardError(f"There is no agent {name!r}. Agents: {', '.join(agent_names())}.")
    if not path.exists():
        raise HalyardError(f"The {name} agent has no skill {skill!r}.")
    meta, body = _read(path)

    client = ctx.client
    slots = {
        "client": client.name,
        "brand": ctx.names.client_brand,
        "window_start": client.window_start.isoformat(),
        "window_end": client.window_end.isoformat(),
        "as_of": client.as_of.isoformat(),
    } | {k: (skills_dir / f).read_text(encoding="utf-8").strip() for k, f in SHARED.items()}

    def fill(match: re.Match[str]) -> str:
        if match[1] not in slots:
            raise HalyardError(f"{path} has a slot {match[0]} that nothing fills.")
        return slots[match[1]]

    label = name if skill == MAIN else f"{name} ({meta['name']})"
    return AgentSpec(label, SLOT.sub(fill, body).strip(), tuple(meta["tools"]))


def _read(path: Path) -> tuple[dict[str, Any], str]:
    """A skill file's front matter and instructions. Its tools must be in the registry."""
    _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
    meta = yaml.safe_load(front)
    unknown = [t for t in meta["tools"] if t not in TOOLS]
    if unknown:
        raise HalyardError(f"{path} lists tools that are not in the registry: {unknown}.")
    return meta, body


def render_tools(name: str, skill: str = MAIN, skills_dir: Path = SKILLS_DIR) -> str:
    """A skill's tool schemas as the model is sent them: its tools from the registry, in the
    skill's order, then the answer tool. This is the text of its tools file."""
    meta, _ = _read(skill_path(name, skill, skills_dir))
    specs = [(TOOLS[t].name, TOOLS[t].description, TOOLS[t].parameters) for t in meta["tools"]]
    specs.append((ANSWER.name, ANSWER.description, ANSWER.parameters))
    tools = [{"name": n, "description": d, "parameters": p} for n, d, p in specs]
    return json.dumps(tools, indent=2, ensure_ascii=False) + "\n"


def write_tools(skills_dir: Path = SKILLS_DIR) -> list[Path]:
    """Regenerate every skill's tools file from the registry."""
    paths = []
    for agent, skill in skill_files(skills_dir):
        path = tools_path(agent, skill, skills_dir)
        path.write_text(render_tools(agent, skill, skills_dir), encoding="utf-8")
        paths.append(path)
    return paths
