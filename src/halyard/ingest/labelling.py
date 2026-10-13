"""Labelling: sentiment and complaint codes, model first, client rules last (PLAN §5a).

The label model labels each distinct normalised text once; answers are cached in a committed,
append-only file, so a rebuild makes no calls. Deterministic client rules then validate and
override. Prompts live in skills/labelling/, rules in config/<client>/labels.yaml.
Rule IDs refer to docs/definitions.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from halyard.ingest.records import TaxonomyRecord
from halyard.llm.base import LLMClient
from halyard.settings import PROJECT_ROOT, ClientConfig, HalyardError

SKILL_DIR = PROJECT_ROOT / "skills" / "labelling"
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "labels.jsonl"
UNLABELLED = "unlabelled"  # D-35: never defaulted to neutral
_SLOT = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True)
class CodeLabel:
    code: str
    owner_team: str  # D-34: always from the taxonomy
    source: str  # model:<name> or override:<rule id> (D-35)


@dataclass(frozen=True)
class TextLabel:
    """The label of one normalised text."""

    sentiment: str  # a configured class, or `unlabelled`
    sentiment_source: str | None = None  # model:<name>
    sentiment_prompt: str | None = None  # hash of the prompt that produced it
    sentiment_reason: str | None = None
    codes: tuple[CodeLabel, ...] = ()
    codes_status: str = "not_applicable"  # labelled, unlabelled or not_applicable
    codes_prompt: str | None = None
    codes_reason: str | None = None
    overrides: tuple[str, ...] = ()  # e.g. "D-32: added TST, removed PKG"


@dataclass
class LabelRun:
    """What each layer decided, for the build log (PLAN §5a, point 4)."""

    cache_hits: int = 0
    model_calls: int = 0
    unlabelled: int = 0
    overridden: int = 0


def render(template: str, slots: dict[str, str]) -> str:
    """Fill every `{{slot}}` of a skill prompt; a slot with no value is an error."""

    def fill(m: re.Match[str]) -> str:
        if m[1] not in slots:
            raise HalyardError(f"Labelling prompt has an unknown slot {{{{{m[1]}}}}}.")
        return slots[m[1]]

    return _SLOT.sub(fill, template).strip()


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Task:
    """One labelling call type: its prompt, its output schema and its cache identity."""

    def __init__(self, name: str, system: str, schema: dict[str, Any]):
        self.name = name
        self.system = system
        self.schema = schema
        # The schema is part of what the model is asked, so it is part of the hash too.
        self.prompt_hash = _hash(system + json.dumps(schema, sort_keys=True))


def sentiment_task(config: dict[str, Any]) -> Task:  # D-30
    classes = config["sentiment"]["classes"]
    system = render(
        (SKILL_DIR / "sentiment.md").read_text(encoding="utf-8"),
        {"classes": ", ".join(classes), "rules": _bullets(config["sentiment"]["rules"])},
    )
    schema = {
        "type": "object",
        "properties": {
            "sentiment": {"type": "string", "enum": classes},
            "reason": {"type": "string"},
        },
        "required": ["sentiment", "reason"],
        "additionalProperties": False,
    }
    return Task("sentiment", system, schema)


def codes_task(config: dict[str, Any], client: ClientConfig, taxonomy: tuple[TaxonomyRecord, ...]) -> Task:
    # D-31: the taxonomy is quoted verbatim from the client's file, never paraphrased here.
    lines = [
        f"- {t.code} ({t.name}). Owner: {t.owner_team}. Includes: {t.includes}."
        + (f" Client rule: {t.client_rule}" if t.client_rule else "")
        for t in taxonomy
    ]
    system = render(
        (SKILL_DIR / "complaint_codes.md").read_text(encoding="utf-8"),
        {
            "client_name": client.name,
            "taxonomy": "\n".join(lines),
            "rules": _bullets(config["codes"]["rules"]),
        },
    )
    schema = {
        "type": "object",
        "properties": {
            "codes": {"type": "array", "items": {"type": "string", "enum": [t.code for t in taxonomy]}},
            "reason": {"type": "string"},
        },
        "required": ["codes", "reason"],
        "additionalProperties": False,
    }
    return Task("codes", system, schema)


class LabelCache:
    """Append-only JSONL of model answers, keyed on text, provider, model and prompt hash."""

    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self._rows: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._rows[self._key(row)] = row

    @staticmethod
    def _key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (row["task"], row["text"], row["provider"], row["model"], row["prompt_hash"])

    def get(self, task: Task, text: str, provider: str, model: str) -> dict[str, Any] | None:
        return self._rows.get((task.name, text, provider, model, task.prompt_hash))

    def put(self, row: dict[str, Any]) -> None:
        self._rows[self._key(row)] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


class Labeller:
    def __init__(
        self,
        client: ClientConfig,
        taxonomy: tuple[TaxonomyRecord, ...],
        provider: str,
        model: str | None,
        llm: LLMClient | None,
        cache: LabelCache | None = None,
        workers: int = 8,
    ):
        path = client.config_dir / "labels.yaml"
        if not path.exists():
            raise HalyardError(f"No labelling config at {path}.")
        self.config = yaml.safe_load(path.read_text())
        self.owners = {t.code: t.owner_team for t in taxonomy}
        self.sentiment = sentiment_task(self.config)
        self.codes = codes_task(self.config, client, taxonomy)
        self.negative = self.config["sentiment"]["classes"][-1]
        self.provider, self.model, self.llm = provider, model, llm
        self.cache = cache or LabelCache()
        self.workers = workers
        self.run = LabelRun()
        self._overrides = [
            (
                o,
                [
                    re.compile(
                        "|".join(rf"(?<!\w){re.escape(t)}(?!\w)" for t in group), re.IGNORECASE
                    )
                    for group in o["when_all"]
                ],
            )
            for o in self.config.get("overrides", [])
        ]

    def label(self, texts: dict[str, bool]) -> dict[str, TextLabel]:
        """Label each normalised text. The value says whether the text is about the client,
        which decides whether a negative text also gets complaint codes (D-31)."""
        ordered = sorted(texts)
        sentiments = self._answers(self.sentiment, ordered)
        coded = [
            t for t in ordered
            if texts[t] and sentiments[t] and sentiments[t]["output"]["sentiment"] == self.negative
        ]  # fmt: skip
        codes = self._answers(self.codes, coded)
        labels = {}
        for text in ordered:
            s = sentiments[text]
            if s is None:
                labels[text] = TextLabel(UNLABELLED)
                continue
            label = TextLabel(
                sentiment=s["output"]["sentiment"],
                sentiment_source=f"model:{s['model']}",
                sentiment_prompt=s["prompt_hash"],
                sentiment_reason=s["output"]["reason"],
            )
            if text in codes:
                label = self._with_codes(label, text, codes[text])
            labels[text] = label
        return labels

    def _answers(self, task: Task, texts: list[str]) -> dict[str, dict[str, Any] | None]:
        """Cached answers, then model calls for the misses; None where neither is possible."""
        out: dict[str, dict[str, Any] | None] = {}
        misses = []
        for text in texts:
            row = self.cache.get(task, text, self.provider, self.model) if self.model else None
            if row:
                out[text] = row
                self.run.cache_hits += 1
            elif self.llm is None:
                out[text] = None  # D-35: no key and no cached answer
                self.run.unlabelled += 1
            else:
                misses.append(text)
        if misses:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                for text, row in zip(misses, pool.map(lambda t: self._call(task, t), misses)):
                    self.cache.put(row)
                    out[text] = row
                    self.run.model_calls += 1
        return out

    def _call(self, task: Task, text: str) -> dict[str, Any]:
        # D-64: the text travels as a JSON string inside tags, apart from the instructions.
        # "<" is escaped so the text cannot contain a closing tag of its own.
        body = json.dumps(text, ensure_ascii=False).replace("<", "\\u003c")
        user = f"<post>\n{body}\n</post>"
        result = self.llm.complete_json(task.system, user, task.schema, task.name)
        return {
            "task": task.name,
            "text": text,
            "provider": self.provider,
            "model": self.model,
            "prompt_hash": task.prompt_hash,
            "output": result.data,
        }

    def _with_codes(self, label: TextLabel, text: str, row: dict[str, Any] | None) -> TextLabel:
        if row is None:
            return replace(label, codes_status=UNLABELLED)
        source = f"model:{row['model']}"
        # D-31: only the client's codes survive, whatever came back.
        chosen = {c: source for c in dict.fromkeys(row["output"]["codes"]) if c in self.owners}
        notes = []
        for override, groups in self._overrides:
            if not all(g.search(text) for g in groups):
                continue
            added = [c for c in override.get("add", []) if c not in chosen]
            removed = [c for c in override.get("remove", []) if c in chosen]
            for c in added:
                chosen[c] = f"override:{override['rule']}"
            for c in removed:
                del chosen[c]
            if added or removed:
                parts = [f"added {', '.join(added)}"] if added else []
                parts += [f"removed {', '.join(removed)}"] if removed else []
                notes.append(f"{override['rule']}: {'; '.join(parts)}")
                self.run.overridden += 1
        return replace(
            label,
            codes=tuple(CodeLabel(c, self.owners[c], src) for c, src in sorted(chosen.items())),
            codes_status="labelled",
            codes_prompt=row["prompt_hash"],
            codes_reason=row["output"]["reason"],
            overrides=tuple(notes),
        )


def summarise(labels: dict[str, TextLabel]) -> dict[str, Counter[str]]:
    return {
        "sentiment": Counter(label.sentiment for label in labels.values()),
        "codes": Counter(c.code for label in labels.values() for c in label.codes),
    }
