"""Optional deterministic orchestration sharing one global call budget."""
from dataclasses import dataclass

from ..runner import AgentRunner, RunBudget, RunResult
from ..tools.registry import Approval
from .definitions import PLANNER, REVIEWER, WORKER


@dataclass
class OrchestrationResult:
    plan: str
    worker: RunResult | None
    review: str
    revision: RunResult | None = None

    @property
    def final_text(self) -> str:
        if self.revision and self.revision.stop_reason == "final_answer":
            return self.revision.final_text
        if self.revision and self.worker:
            return (f"{self.worker.final_text}\n\nReview: {self.review}\n"
                    f"Revision stopped: {self.revision.final_text}")
        if self.worker and self.worker.stop_reason == "final_answer":
            return self.worker.final_text
        return self.worker.final_text if self.worker else self.plan


class Orchestrator:
    def __init__(self, runner: AgentRunner) -> None:
        self.runner = runner

    def run(self, task: str, approval: Approval | None = None) -> OrchestrationResult:
        settings = self.runner.settings
        budget = RunBudget(max_model_calls=settings.max_model_calls,
                           max_tool_calls=settings.max_tool_calls)
        plan = self.runner.run(PLANNER, task, budget=budget)
        if plan.stop_reason != "final_answer":
            return OrchestrationResult(plan.final_text, None, "Review skipped: budget reached.")
        worker = self.runner.run(WORKER, f"Task: {task}\nPlan: {plan.final_text}",
                                 budget=budget, approval=approval)
        if worker.stop_reason != "final_answer":
            return OrchestrationResult(plan.final_text, worker, "Review skipped: worker stopped.")
        review = self.runner.run(REVIEWER, f"Task: {task}\nWorker result: {worker.final_text}",
                                 budget=budget)
        if review.stop_reason != "final_answer" or review.final_text.strip().upper() == "OK":
            return OrchestrationResult(plan.final_text, worker, review.final_text)
        revision = self.runner.run(WORKER, f"Task: {task}\nPrevious result: {worker.final_text}\nFix: {review.final_text}",
                                   budget=budget, approval=approval)
        return OrchestrationResult(plan.final_text, worker, review.final_text, revision)
