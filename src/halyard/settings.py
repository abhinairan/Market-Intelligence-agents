"""Runtime settings: secrets and ports from .env, client rules from config/<client>/."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class HalyardError(Exception):
    """An error with a message meant for the person running the CLI."""


@dataclass(frozen=True)
class ClientConfig:
    name: str
    config_dir: Path
    data_pack: Path
    timezone: str
    week_starts_on: str
    window_start: date
    window_end: date
    as_of: date
    stale_after_days: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_http_port: str
    anthropic_api_key: str | None
    client: ClientConfig


def load_client(name: str) -> ClientConfig:
    config_dir = PROJECT_ROOT / "config" / name
    path = config_dir / "client.yaml"
    if not path.exists():
        raise HalyardError(f"No client config at {path}. Set HALYARD_CLIENT to a folder under config/.")
    raw = yaml.safe_load(path.read_text())
    return ClientConfig(
        name=raw["client"],
        config_dir=config_dir,
        data_pack=PROJECT_ROOT / raw["data_pack"],
        timezone=raw["timezone"],
        week_starts_on=raw["week_starts_on"],
        window_start=raw["window"]["start"],
        window_end=raw["window"]["end"],
        as_of=raw["as_of"],
        stale_after_days=raw["stale_after_days"],
        raw=raw,
    )


def env_file() -> Path:
    return PROJECT_ROOT / ".env"


def load_settings() -> Settings:
    load_dotenv(env_file())
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise HalyardError("NEO4J_PASSWORD is not set. Copy .env.example to .env and fill it in.")
    bolt_port = os.environ.get("NEO4J_BOLT_PORT", "7687")
    return Settings(
        neo4j_uri=os.environ.get("NEO4J_URI", f"bolt://localhost:{bolt_port}"),
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=password,
        neo4j_http_port=os.environ.get("NEO4J_HTTP_PORT", "7474"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        client=load_client(os.environ.get("HALYARD_CLIENT", "brewbird")),
    )
