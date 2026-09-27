from collections import deque

from free_agent.cli import registry_for
from free_agent.config import Settings
from free_agent.messages import ModelReply
from free_agent.multi_agent.orchestrator import Orchestrator
from free_agent.runner import AgentRunner


class FakeClient:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.request_count = 0
        self.requests = []

    def complete(self, **kwargs):
        self.request_count += 1
        self.requests.append(kwargs)
        return self.replies.popleft()


def test_planner_worker_reviewer_share_budget(tmp_path):
    settings = Settings(workspace=tmp_path)
    client = FakeClient([ModelReply("Plan"), ModelReply("Done"), ModelReply("OK")])
    result = Orchestrator(AgentRunner(settings, client, registry_for(settings))).run("task")
    assert result.final_text == "Done"
    assert result.review == "OK"
    assert result.revision is None
    assert client.request_count == 3
    assert client.requests[0]["tools"] is None
    assert client.requests[1]["tools"]
    assert client.requests[2]["tools"] is None


def test_single_revision_and_global_budget(tmp_path):
    settings = Settings(workspace=tmp_path, max_model_calls=4)
    client = FakeClient([ModelReply("Plan"), ModelReply("First"),
                         ModelReply("Fix detail"), ModelReply("Revised")])
    result = Orchestrator(AgentRunner(settings, client, registry_for(settings))).run("task")
    assert result.final_text == "Revised"
    assert result.revision.usage["model_calls"] == 4
    assert client.request_count == 4

    settings = Settings(workspace=tmp_path, max_model_calls=3)
    client = FakeClient([ModelReply("Plan"), ModelReply("First"), ModelReply("Fix detail")])
    result = Orchestrator(AgentRunner(settings, client, registry_for(settings))).run("task")
    assert result.revision.stop_reason == "model_budget"
    assert "First" in result.final_text
    assert "Review: Fix detail" in result.final_text
    assert "Revision stopped:" in result.final_text
    assert client.request_count == 3


def test_planner_budget_stop_skips_worker(tmp_path):
    settings = Settings(workspace=tmp_path, max_model_calls=1, retry_attempts=0)
    client = FakeClient([ModelReply("Plan")])
    result = Orchestrator(AgentRunner(settings, client, registry_for(settings))).run("task")
    assert result.worker is not None
    assert result.worker.stop_reason == "model_budget"
    assert client.request_count == 1
