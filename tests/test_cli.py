from collections import deque
from copy import deepcopy

from free_agent import cli
from free_agent.config import Settings
from free_agent.messages import ModelReply


class FakeClient:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.request_count = 0
        self.requests = []

    def complete(self, **kwargs):
        self.request_count += 1
        self.requests.append(deepcopy(kwargs))
        return self.replies.popleft()


def test_one_shot_cli_without_live_api(monkeypatch, tmp_path, capsys):
    settings = Settings(api_key="test-only", workspace=tmp_path)
    client = FakeClient([ModelReply("Hello from fake model")])
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "OpenRouterClient", lambda _settings: client)
    assert cli.main(["run", "Say hello"]) == 0
    output = capsys.readouterr().out
    assert "Hello from fake model" in output
    assert "Model calls: 1/8" in output
    assert client.requests[0]["messages"][-1]["content"] == "Say hello"


def test_chat_keeps_history_and_quits(monkeypatch, tmp_path, capsys):
    settings = Settings(api_key="test-only", workspace=tmp_path)
    client = FakeClient([ModelReply("First answer"), ModelReply("Second answer")])
    lines = iter(["first", "/usage", "second", "/quit"])
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "OpenRouterClient", lambda _settings: client)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(lines))
    assert cli.main(["chat"]) == 0
    output = capsys.readouterr().out
    assert "First answer" in output and "Second answer" in output
    second_messages = client.requests[1]["messages"]
    assert [m["content"] for m in second_messages if m["role"] == "user"] == ["first", "second"]


def test_write_approval_shows_preview_and_denies_on_eof(monkeypatch, capsys):
    def no_input(*_args, **_kwargs):
        raise EOFError

    monkeypatch.setattr(cli.Confirm, "ask", no_input)
    approved = cli.approval_for(False)("write_workspace_text", {
        "path": "out.txt", "content": "hello", "overwrite": True,
    })
    assert approved is False
    output = capsys.readouterr().out
    assert "out.txt" in output and "overwrite=True" in output and "hello" in output
