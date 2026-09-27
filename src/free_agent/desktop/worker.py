"""Run the synchronous agent away from Qt's UI thread."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QObject, Signal, Slot

from free_agent.agent import Agent
from free_agent.cli import DEFAULT_TOOLS, registry_for
from free_agent.client import OpenRouterClient
from free_agent.config import Settings
from free_agent.errors import AgentError
from free_agent.runner import AgentRunner, RunResult


@dataclass
class ApprovalRequest:
    name: str
    arguments: dict
    event: threading.Event = field(default_factory=threading.Event)
    approved: bool = False

    def answer(self, approved: bool) -> None:
        self.approved = approved
        self.event.set()


class ChatWorker(QObject):
    approval_requested = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    done = Signal()

    def __init__(self, *, api_key: str, model: str, workspace: str,
                 prompt: str, history: list[dict]) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.workspace = workspace
        self.prompt = prompt
        self.history = history
        self.pending_approval: ApprovalRequest | None = None

    def approve_tool(self, name: str, arguments: dict) -> bool:
        request = ApprovalRequest(name, arguments)
        self.pending_approval = request
        self.approval_requested.emit(request)
        request.event.wait()
        self.pending_approval = None
        return request.approved

    @Slot()
    def run(self) -> None:
        try:
            settings = Settings(
                api_key=self.api_key,
                model=self.model,
                app_name="Noki AI",
                workspace=Path(self.workspace),
            )
            settings.require_api_key()
            settings.prepare_workspace()
            runner = AgentRunner(settings, OpenRouterClient(settings), registry_for(settings))
            result: RunResult = runner.run(
                Agent(tools=DEFAULT_TOOLS), self.prompt,
                history=self.history, approval=self.approve_tool,
            )
            self.completed.emit(result)
        except (AgentError, ValidationError, OSError, ValueError) as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("The request failed unexpectedly. Please try again.")
        finally:
            self.done.emit()
