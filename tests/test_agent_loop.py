from collections import deque
from copy import deepcopy

from free_agent.agent import Agent
from free_agent.config import Settings
from free_agent.messages import ModelReply, ToolCall
from free_agent.runner import AgentRunner
from free_agent.tools.calculator import Calculator
from free_agent.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.request_count = 0
        self.requests = []

    def complete(self, **kwargs):
        self.request_count += 1
        self.requests.append(deepcopy(kwargs))
        return self.replies.popleft()


def make_runner(tmp_path, replies, **limits):
    settings = Settings(workspace=tmp_path, **limits)
    client = FakeClient(replies)
    registry = ToolRegistry()
    registry.register(Calculator())
    return AgentRunner(settings, client, registry), client


def test_plain_answer(tmp_path):
    runner, client = make_runner(tmp_path, [ModelReply("Hello")])
    result = runner.run(Agent(), "Hi")
    assert result.final_text == "Hello"
    assert result.usage["model_calls"] == 1
    assert len(client.requests) == 1


def test_one_tool_round_trip(tmp_path):
    runner, client = make_runner(tmp_path, [
        ModelReply(None, [ToolCall("id-123", "calculator", '{"expression":"19*37"}')]),
        ModelReply("703")])
    result = runner.run(Agent(tools=["calculator"]), "19 * 37")
    assert result.final_text == "703"
    assert result.usage["model_calls"] == 2
    assert result.usage["tool_calls"] == 1
    assert client.requests[1]["messages"][-1]["tool_call_id"] == "id-123"


def test_multiple_tools_before_next_model_call(tmp_path):
    runner, client = make_runner(tmp_path, [
        ModelReply(None, [ToolCall("a", "calculator", '{"expression":"2+2"}'),
                          ToolCall("b", "calculator", '{"expression":"3+3"}')]),
        ModelReply("Done")])
    result = runner.run(Agent(tools=["calculator"]), "two sums")
    assert result.usage["tool_calls"] == 2
    assert [x["tool_call_id"] for x in client.requests[1]["messages"][-2:]] == ["a", "b"]


def test_bad_json_and_unknown_tool_are_safe(tmp_path):
    runner, _ = make_runner(tmp_path, [
        ModelReply(None, [ToolCall("a", "calculator", "{"),
                          ToolCall("b", "other", "{}")]), ModelReply("Done")])
    result = runner.run(Agent(tools=["calculator"]), "test")
    assert "validation_error" in result.messages[-3]["content"]
    assert "unknown_tool" in result.messages[-2]["content"]


def test_hard_budgets(tmp_path):
    calls = [ModelReply(None, [ToolCall(str(i), "calculator", '{"expression":"1+1"}')])
             for i in range(5)]
    runner, client = make_runner(tmp_path, calls, max_model_calls=2, max_tool_calls=10)
    result = runner.run(Agent(tools=["calculator"]), "loop")
    assert result.stop_reason == "model_budget"
    assert result.usage["model_calls"] == 2
    assert client.request_count == 2
    runner, _ = make_runner(tmp_path, calls, max_tool_calls=1)
    result = runner.run(Agent(tools=["calculator"]), "loop")
    assert result.stop_reason == "tool_budget"
    assert result.usage["tool_calls"] == 1


def test_max_steps_and_tool_budget(tmp_path):
    replies = [ModelReply(None, [ToolCall("a", "calculator", '{"expression":"1+1"}')]),
               ModelReply("would be too late")]
    runner, client = make_runner(tmp_path, replies, max_steps=1)
    result = runner.run(Agent(tools=["calculator"]), "loop")
    assert result.stop_reason == "max_steps"
    assert client.request_count == 1
    runner, client = make_runner(tmp_path, replies, max_tool_calls=1)
    result = runner.run(Agent(tools=["calculator"]), "loop")
    assert result.stop_reason == "final_answer"


def test_tool_batch_over_budget_executes_none(tmp_path):
    runner, client = make_runner(tmp_path, [ModelReply(None, [
        ToolCall("a", "calculator", '{"expression":"2+2"}'),
        ToolCall("b", "calculator", '{"expression":"3+3"}'),
    ])], max_tool_calls=1)
    result = runner.run(Agent(tools=["calculator"]), "two sums")
    assert result.stop_reason == "tool_budget"
    assert result.usage["tool_calls"] == 0
    assert len(client.requests) == 1
    assert all(message["role"] != "tool" for message in result.messages)
