"""Agent skills: instructions and a tool list read from `skills/<agent>/SKILL.md`.

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
SHARED = {"grounding": "shared/grounding.md", "answer_format": "shared/answer_format.md"}
SLOT = re.compile(r"\{\{(\w+)\}\}")


def agent_names(skills_dir: Path = SKILLS_DIR) -> list[str]:
    return sorted(p.parent.name for p in skills_dir.glob(f"*/{SKILL_FILE}"))


def load_skill(name: str, ctx: ToolContext, skills_dir: Path = SKILLS_DIR) -> AgentSpec:
    path = skills_dir / name / SKILL_FILE
    if not path.exists():
        raise HalyardError(f"There is no agent {name!r}. Agents: {', '.join(agent_names())}.")
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

    return AgentSpec(meta["name"], SLOT.sub(fill, body).strip(), tuple(meta["tools"]))


def _read(path: Path) -> tuple[dict[str, Any], str]:
    """A skill file's front matter and instructions. Its tools must be in the registry."""
    _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
    meta = yaml.safe_load(front)
    unknown = [t for t in meta["tools"] if t not in TOOLS]
    if unknown:
        raise HalyardError(f"{path} lists tools that are not in the registry: {unknown}.")
    return meta, body


def render_tools(name: str, skills_dir: Path = SKILLS_DIR) -> str:
    """The agent's tool schemas as the model is sent them: its tools from the registry, in
    the skill's order, then the answer tool. This is the text of `tools.json`."""
    meta, _ = _read(skills_dir / name / SKILL_FILE)
    specs = [(TOOLS[t].name, TOOLS[t].description, TOOLS[t].parameters) for t in meta["tools"]]
    specs.append((ANSWER.name, ANSWER.description, ANSWER.parameters))
    tools = [{"name": n, "description": d, "parameters": p} for n, d, p in specs]
    return json.dumps(tools, indent=2, ensure_ascii=False) + "\n"


def write_tools(skills_dir: Path = SKILLS_DIR) -> list[Path]:
    """Regenerate every agent's `tools.json` from the registry."""
    paths = []
    for name in agent_names(skills_dir):
        path = skills_dir / name / TOOLS_FILE
        path.write_text(render_tools(name, skills_dir), encoding="utf-8")
        paths.append(path)
    return paths
