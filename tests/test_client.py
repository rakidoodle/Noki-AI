from types import SimpleNamespace

import pytest
import httpx2
from openai import APIConnectionError, AuthenticationError as SDKAuthenticationError

from free_agent.client import OpenRouterClient
from free_agent.config import Settings
from free_agent.errors import AuthenticationError, BudgetExceeded


class FakeSDK:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **_kwargs):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def response(text):
    return SimpleNamespace(id="r1", usage=None, choices=[SimpleNamespace(
        message=SimpleNamespace(content=text, tool_calls=[]))])


def test_transient_retry_bounded(tmp_path):
    sdk = FakeSDK([APIConnectionError(request=None), response("ok")])
    client = OpenRouterClient(Settings(workspace=tmp_path), sdk=sdk, sleep=lambda _: None)
    assert client.complete(messages=[], max_requests=2).content == "ok"
    assert sdk.calls == 2
    sdk = FakeSDK([APIConnectionError(request=None), response("unused")])
    client = OpenRouterClient(Settings(workspace=tmp_path), sdk=sdk, sleep=lambda _: None)
    with pytest.raises(BudgetExceeded):
        client.complete(messages=[], max_requests=1)
    assert sdk.calls == 1


def test_auth_never_retried(tmp_path):
    exc = SDKAuthenticationError("bad", response=httpx2.Response(401, request=httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")), body=None)
    sdk = FakeSDK([exc])
    client = OpenRouterClient(Settings(workspace=tmp_path), sdk=sdk)
    with pytest.raises(AuthenticationError):
        client.complete(messages=[])
    assert sdk.calls == 1


def test_rate_limit_never_retried(tmp_path):
    from openai import RateLimitError as SDKRateLimitError
    from free_agent.errors import RateLimitError

    response_429 = httpx2.Response(429, request=httpx2.Request(
        "POST", "https://openrouter.ai/api/v1/chat/completions"))
    sdk = FakeSDK([SDKRateLimitError("quota", response=response_429, body=None)])
    client = OpenRouterClient(Settings(workspace=tmp_path), sdk=sdk)
    with pytest.raises(RateLimitError):
        client.complete(messages=[])
    assert sdk.calls == 1


def test_server_retry_hint_is_respected(tmp_path):
    from openai import APIStatusError

    response_503 = httpx2.Response(503, headers={"retry-after": "4"},
                                   request=httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    sdk = FakeSDK([APIStatusError("busy", response=response_503, body=None), response("ok")])
    delays = []
    client = OpenRouterClient(Settings(workspace=tmp_path), sdk=sdk, sleep=delays.append)
    assert client.complete(messages=[]).content == "ok"
    assert delays == [4]


def test_runner_budget_counts_failed_request_before_retry(tmp_path):
    from free_agent.agent import Agent
    from free_agent.runner import AgentRunner
    from free_agent.tools.registry import ToolRegistry

    sdk = FakeSDK([APIConnectionError(request=None), response("would exceed budget")])
    settings = Settings(workspace=tmp_path, max_model_calls=1, retry_attempts=2)
    client = OpenRouterClient(settings, sdk=sdk, sleep=lambda _: None)
    result = AgentRunner(settings, client, ToolRegistry()).run(Agent(), "hello")
    assert result.stop_reason == "model_budget"
    assert result.usage["model_calls"] == 1
    assert sdk.calls == 1
    assert result.messages[-1] == {"role": "user", "content": "hello"}
