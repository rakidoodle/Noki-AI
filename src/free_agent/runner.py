"""A bounded, inspectable model/tool loop."""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .agent import Agent
from .config import Settings
from .errors import BudgetExceeded
from .messages import trim_history
from .tools.registry import Approval, ToolRegistry

log = logging.getLogger(__name__)


@dataclass
class RunBudget:
    model_calls: int = 0
    tool_calls: int = 0
    max_model_calls: int = 8
    max_tool_calls: int = 12

    def snapshot(self) -> dict[str, int]:
        return {"model_calls": self.model_calls, "tool_calls": self.tool_calls,
                "max_model_calls": self.max_model_calls, "max_tool_calls": self.max_tool_calls}


@dataclass
class RunResult:
    final_text: str
    messages: list[dict[str, Any]]
    usage: dict[str, int]
    stop_reason: str
    tool_notices: list[str] = field(default_factory=list)


class AgentRunner:
    def __init__(self, settings: Settings, client: Any, registry: ToolRegistry) -> None:
        self.settings = settings
        self.client = client
        self.registry = registry

    def run(self, agent: Agent, user_input: str, *, history: list[dict] | None = None,
            approval: Approval | None = None, budget: RunBudget | None = None) -> RunResult:
        budget = budget or RunBudget(max_model_calls=self.settings.max_model_calls,
                                     max_tool_calls=self.settings.max_tool_calls)
        run_id = uuid.uuid4().hex[:8]
        started = time.monotonic()
        messages: list[dict] = [{"role": "system", "content": agent.instructions}]
        messages.extend(trim_history(history or []))
        messages.append({"role": "user", "content": user_input})
        notices: list[str] = []
        schemas = self.registry.schemas_for(agent.tools)
        steps = min(agent.max_steps or self.settings.max_steps, self.settings.max_steps)
        log.info("run=%s agent=%s model=%s", run_id, agent.name, agent.model or self.settings.model)

        def stop(reason: str, message: str) -> RunResult:
            log.info("run=%s stop=%s model_calls=%d tool_calls=%d elapsed=%.2fs",
                     run_id, reason, budget.model_calls, budget.tool_calls, time.monotonic() - started)
            return RunResult(message, messages, budget.snapshot(), reason, notices)

        for _ in range(steps):
            if budget.model_calls >= budget.max_model_calls:
                return stop("model_budget", "Model-call budget reached; this run stopped.")
            before = getattr(self.client, "request_count", None)
            exhausted_during_retry = False
            try:
                reply = self.client.complete(messages=messages, tools=schemas or None,
                                             model=agent.model or self.settings.model,
                                             max_requests=budget.max_model_calls - budget.model_calls)
            except BudgetExceeded:
                exhausted_during_retry = True
            finally:
                after = getattr(self.client, "request_count", None)
                if before is not None and after is not None:
                    budget.model_calls += after - before
                else:
                    budget.model_calls += 1
            if exhausted_during_retry:
                return stop("model_budget", "Model-call budget reached during retries; this run stopped.")
            messages.append(reply.as_assistant_message())
            if not reply.tool_calls:
                return stop("final_answer", reply.content or "")
            if len(reply.tool_calls) > budget.max_tool_calls - budget.tool_calls:
                return stop("tool_budget", "Tool-call budget reached; this run stopped before the tool batch.")
            for call in reply.tool_calls:
                budget.tool_calls += 1
                result = self.registry.execute(call.name, call.arguments, allowed=agent.tools, approval=approval)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                notices.append(f"{call.name}: {'ok' if json.loads(result)['ok'] else 'error'}")
        return stop("max_steps", "Maximum agent steps reached; this run stopped.")
