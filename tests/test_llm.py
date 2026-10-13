import json

import pytest

from halyard.llm import LLMError, get_client
from halyard.llm.base import JsonResult, LLMClient
from halyard.settings import HalyardError, Settings, load_client

SCHEMA = {
    "type": "object",
    "properties": {"sentiment": {"type": "string"}},
    "required": ["sentiment"],
    "additionalProperties": False,
}


class FakeClient(LLMClient):
    provider = "fake"

    def __init__(self, data, **kw):
        super().__init__("fake-model", "label", **kw)
        self.data = data

    def _complete_json(self, system, user, schema, name, max_tokens):
        return JsonResult(self.data, self.provider, self.model, 10, 3)


def test_usage_is_logged_per_call(tmp_path):
    log = tmp_path / "usage.jsonl"
    FakeClient({"sentiment": "negative"}, usage_log=log).complete_json("s", "u", SCHEMA, "label")
    row = json.loads(log.read_text())
    assert (row["model"], row["purpose"], row["input_tokens"]) == ("fake-model", "label", 10)


def test_output_missing_required_field_is_rejected(tmp_path):
    client = FakeClient({}, usage_log=tmp_path / "u.jsonl")
    with pytest.raises(LLMError, match="missing"):
        client.complete_json("s", "u", SCHEMA, "label")


def _settings(**over):
    base = {
        "neo4j_uri": "",
        "neo4j_user": "",
        "neo4j_password": "",
        "neo4j_http_port": "",
        "llm_provider": "openai",
        "llm_api_key": "k",
        "label_model": "m",
        "agent_model": "m2",
        "client": load_client("brewbird"),
    }
    return Settings(**{**base, **over})


def test_get_client_picks_provider_and_model():
    c = get_client(_settings(), "agent")
    assert (c.provider, c.model) == ("openai", "m2")
    assert get_client(_settings(llm_provider="anthropic"), "label").provider == "anthropic"


def test_missing_model_or_key_is_a_clear_error():
    with pytest.raises(HalyardError, match="LABEL_MODEL"):
        get_client(_settings(label_model=None), "label")
    with pytest.raises(HalyardError, match="OPENAI_API_KEY"):
        get_client(_settings(llm_api_key=None), "label")
