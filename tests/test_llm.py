import json
from types import SimpleNamespace

import pytest

from halyard.llm import LLMError, Message, ToolCall, ToolSpec, ToolTurn, get_client
from halyard.llm.base import JsonResult, LLMClient
from halyard.llm.openai_client import to_call, to_input, to_tool
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


# Tool calling (P4 step 1)

COUNT = ToolSpec(
    "count_mentions",
    "Count mentions.",
    {
        "type": "object",
        "properties": {"line": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    },
)


class ScriptedClient(LLMClient):
    """Plays back a list of turns and keeps the messages it was sent each time."""

    provider = "fake"

    def __init__(self, turns, **kw):
        super().__init__("fake-model", "agent", **kw)
        self.turns = list(turns)
        self.seen = []

    def _complete_json(self, system, user, schema, name, max_tokens):
        raise NotImplementedError

    def _run_with_tools(self, system, messages, tools, max_tokens, require_tool):
        self.seen.append(list(messages))
        text, calls = self.turns.pop(0)
        return ToolTurn(text, tuple(calls), self.provider, self.model, 100, 20, 60)


def test_tool_loop_contract(tmp_path):
    """Call, run the tools, append the turn and one result per call, call again."""
    log = tmp_path / "usage.jsonl"
    call = ToolCall("call_1", "count_mentions", {"line": "Nitro"})
    client = ScriptedClient([("", [call]), ("Nitro has 211.", [])], usage_log=log)
    messages = [Message("user", "How many Nitro conversations?")]

    turn = client.run_with_tools("s", messages, [COUNT], run_id="run-1")
    assert turn.tool_calls == (call,)
    messages += [turn.message, Message("tool", '{"total": 211}', tool_call_id=call.id)]
    final = client.run_with_tools("s", messages, [COUNT], run_id="run-1")

    assert (final.text, final.tool_calls) == ("Nitro has 211.", ())
    assert [m.role for m in client.seen[1]] == ["user", "assistant", "tool"]
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(r["purpose"], r["run_id"], r["cached_input_tokens"]) for r in rows] == [
        ("agent", "run-1", 60),
        ("agent", "run-1", 60),
    ]


def test_unknown_tool_and_missing_required_call_are_rejected(tmp_path):
    log = tmp_path / "u.jsonl"
    invented = ScriptedClient([("", [ToolCall("c", "delete_everything", {})])], usage_log=log)
    with pytest.raises(LLMError, match="unknown tools"):
        invented.run_with_tools("s", [Message("user", "q")], [COUNT])
    silent = ScriptedClient([("An answer.", [])], usage_log=log)
    with pytest.raises(LLMError, match="without calling a tool"):
        silent.run_with_tools("s", [Message("user", "q")], [COUNT], require_tool=True)
    assert not log.exists()  # a rejected turn is not logged as a usable one


def test_adapter_without_tool_calling_says_so(tmp_path):
    client = FakeClient({}, usage_log=tmp_path / "u.jsonl")
    with pytest.raises(LLMError, match="not implemented for the fake adapter"):
        client.run_with_tools("s", [Message("user", "q")], [COUNT])
    anthropic = get_client(_settings(llm_provider="anthropic"), "agent")
    with pytest.raises(LLMError, match="not implemented for the anthropic adapter"):
        anthropic.run_with_tools("s", [Message("user", "q")], [COUNT])


def test_openai_translation():
    assert to_tool(COUNT) == {
        "type": "function",
        "name": "count_mentions",
        "description": "Count mentions.",
        "parameters": COUNT.parameters,
        "strict": False,
    }
    call = ToolCall("call_1", "count_mentions", {"line": "Nitro"})
    messages = [
        Message("user", "How many?"),
        Message("assistant", "Checking.", (call,)),
        Message("tool", '{"total": 211}', tool_call_id="call_1"),
    ]
    assert to_input(messages) == [
        {"role": "user", "content": "How many?"},
        {"role": "assistant", "content": "Checking."},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "count_mentions",
            "arguments": '{"line": "Nitro"}',
        },
        {"type": "function_call_output", "call_id": "call_1", "output": '{"total": 211}'},
    ]
    item = SimpleNamespace(call_id="call_1", name="count_mentions", arguments='{"line": "Nitro"}')
    assert to_call(item, "m") == call
    with pytest.raises(LLMError, match="not JSON"):
        to_call(SimpleNamespace(call_id="c", name="count_mentions", arguments="{line"), "m")
