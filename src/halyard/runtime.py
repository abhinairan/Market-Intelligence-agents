"""Docker and Neo4j lifecycle: preflight checks, compose up/down, wait until ready."""

from __future__ import annotations

import shutil
import subprocess
import time

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from halyard.settings import PROJECT_ROOT, HalyardError, Settings, env_file


def check_env_file() -> None:
    if not env_file().exists():
        raise HalyardError("No .env file. Run: cp .env.example .env  (then add your ANTHROPIC_API_KEY)")


def check_docker() -> None:
    if shutil.which("docker") is None:
        raise HalyardError(
            "Docker is not installed. Install a Docker runtime "
            "(OrbStack, Docker Desktop or Colima) and try again."
        )
    result = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise HalyardError("Docker is installed but not running. Start your Docker runtime and retry.")


def compose(*args: str) -> None:
    result = subprocess.run(["docker", "compose", *args], check=False, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise HalyardError(f"`docker compose {' '.join(args)}` failed (exit {result.returncode}).")


def wait_for_neo4j(settings: Settings, timeout_s: float = 120) -> None:
    """Block until Bolt accepts a query, so `up` returning means the graph is usable."""
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with GraphDatabase.driver(
                settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
            ) as driver:
                driver.verify_connectivity()
                return
        except AuthError as exc:
            raise HalyardError(
                "Neo4j rejected the password in .env. If you changed NEO4J_PASSWORD after the "
                "first start, run `halyard down --wipe` and then `halyard up`."
            ) from exc
        except (ServiceUnavailable, OSError) as exc:
            last_error = exc
            time.sleep(2)
    raise HalyardError(f"Neo4j was not ready after {timeout_s:.0f}s: {last_error}")


def up(settings: Settings) -> None:
    check_env_file()
    check_docker()
    compose("up", "-d", "--wait")
    wait_for_neo4j(settings)


def down(wipe: bool = False) -> None:
    check_docker()
    compose("down", *(["-v"] if wipe else []))
