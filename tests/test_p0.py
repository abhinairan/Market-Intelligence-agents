from datetime import date

import pytest

from halyard import runtime
from halyard.cli import main
from halyard.settings import HalyardError, load_client


def test_client_config_matches_definitions():
    client = load_client("brewbird")
    assert client.timezone == "+05:30"  # D-01
    assert (client.window_start, client.window_end) == (date(2026, 8, 17), date(2026, 10, 4))  # D-03
    assert client.as_of == date(2026, 10, 4)  # D-03
    assert client.data_pack.joinpath("mentions.csv").exists()


def test_unknown_client_is_a_clear_error():
    with pytest.raises(HalyardError, match="No client config"):
        load_client("nobody")


def test_missing_docker_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda _: None)
    with pytest.raises(HalyardError, match="Docker is not installed"):
        runtime.check_docker()


def test_missing_saved_eval_is_a_clear_error(capsys):
    assert main(["eval", "--report", "E-nothere"]) == 1
    assert "No saved eval E-nothere" in capsys.readouterr().err


@pytest.mark.integration
def test_neo4j_answers_a_query():
    from neo4j import GraphDatabase

    from halyard.settings import load_settings

    s = load_settings()
    try:
        runtime.wait_for_neo4j(s, timeout_s=5)
    except HalyardError:
        pytest.skip("Neo4j is not running (make up)")
    with GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)) as driver:
        records, _, _ = driver.execute_query("RETURN 1 AS ok")
    assert records[0]["ok"] == 1
