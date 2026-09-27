"""Command-line interface for one-shot and interactive agent use."""
import argparse
import sys
import tempfile
import traceback

from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.prompt import Confirm

from .agent import Agent
from .client import OpenRouterClient
from .config import Settings, load_settings
from .errors import AgentError
from .logging_utils import configure_logging
from .runner import AgentRunner
from .tools.calculator import Calculator
from .tools.datetime_tool import CurrentDateTime
from .tools.registry import ToolRegistry
from .tools.workspace_files import ListWorkspaceFiles, ReadWorkspaceText, WriteWorkspaceText

console = Console()
DEFAULT_TOOLS = ["calculator", "current_datetime", "list_workspace_files",
                 "read_workspace_text", "write_workspace_text"]


def registry_for(settings: Settings) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (Calculator(), CurrentDateTime(), ListWorkspaceFiles(settings.workspace),
                 ReadWorkspaceText(settings.workspace), WriteWorkspaceText(settings.workspace)):
        registry.register(tool)
    return registry


def approval_for(yes: bool):
    if yes:
        return lambda _name, _args: True
    def ask(name: str, args: dict) -> bool:
        path = args.get("path", "")
        content = args.get("content", "")
        preview = repr(content[:160]) + ("…" if len(content) > 160 else "")
        console.print(f"Write {escape(str(path))} · {len(content.encode('utf-8'))} bytes · "
                      f"overwrite={args.get('overwrite', False)}")
        console.print(f"Preview: {escape(preview)}")
        try:
            return Confirm.ask(f"Approve {escape(name)} for {escape(str(path))}?", default=False)
        except EOFError:
            return False
    return ask


def show_result(result) -> None:
    for notice in result.tool_notices:
        console.print(f"[dim]Tool {notice}[/dim]")
    console.print(result.final_text)
    console.print(f"[dim]Model calls: {result.usage['model_calls']}/{result.usage['max_model_calls']} · "
                  f"Tool calls: {result.usage['tool_calls']}/{result.usage['max_tool_calls']}[/dim]")


def doctor(settings: Settings, live: bool) -> int:
    checks = [
        ("Python", f"{sys.version_info.major}.{sys.version_info.minor}"),
        ("Model", settings.model), ("Base URL", settings.base_url),
        ("API key", "present" if settings.api_key else "missing"),
        ("Workspace", str(settings.workspace)),
    ]
    try:
        settings.prepare_workspace()
        with tempfile.TemporaryFile(dir=settings.workspace):
            writable = True
    except OSError:
        writable = False
    checks.append(("Workspace writable", "yes" if writable else "no"))
    for name, value in checks:
        console.print(f"{name}: {value}")
    if live:
        settings.require_api_key()
        reply = OpenRouterClient(settings).complete(messages=[
            {"role": "user", "content": "Reply with OK."}], max_requests=1)
        console.print(f"Live response: {reply.content or '(empty)'}")
        return 0 if reply.content else 1
    return 0 if writable and settings.api_key else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="free-agent")
    parser.add_argument("--debug", action="store_true", help="Show full tracebacks")
    parser.add_argument("--model", help="Override OPENROUTER_MODEL")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run a single task")
    run.add_argument("task")
    run.add_argument("--yes", action="store_true", help="Approve file writes")
    chat = sub.add_parser("chat", help="Start interactive chat")
    chat.add_argument("--yes", action="store_true", help="Approve file writes")
    sub.add_parser("models", help="Show model selection guidance")
    doc = sub.add_parser("doctor", help="Check local configuration")
    doc.add_argument("--live", action="store_true", help="Make exactly one live request")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.model:
            settings.model = args.model
        configure_logging("DEBUG" if args.debug else settings.log_level)
        if args.command == "models":
            console.print(f"Current model: {settings.model}\nopenrouter/free routes among available free models.\n"
                          "https://openrouter.ai/collections/free-models")
            return 0
        if args.command == "doctor":
            return doctor(settings, args.live)
        settings.require_api_key()
        settings.prepare_workspace()
        runner = AgentRunner(settings, OpenRouterClient(settings), registry_for(settings))
        agent = Agent(tools=DEFAULT_TOOLS)
        approval = approval_for(args.yes)
        console.print(f"Model: {settings.model} · per-turn model-call budget: {settings.max_model_calls}")
        if args.command == "run":
            result = runner.run(agent, args.task, approval=approval)
            show_result(result)
            return 0 if result.stop_reason == "final_answer" else 1
        history: list[dict] = []
        last_usage: dict | None = None
        console.print("Type /help for commands.")
        while True:
            try:
                line = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                return 0
            if not line:
                continue
            if line == "/quit":
                return 0
            if line == "/help":
                console.print("/help /model /clear /usage /quit")
                continue
            if line == "/model":
                console.print(settings.model)
                continue
            if line == "/clear":
                history.clear()
                console.print("History cleared.")
                continue
            if line == "/usage":
                console.print(last_usage or "No runs yet.")
                continue
            result = runner.run(agent, line, history=history, approval=approval)
            show_result(result)
            last_usage = result.usage
            if result.stop_reason == "final_answer":
                history = result.messages[1:]
    except (AgentError, ValidationError, OSError, ValueError) as exc:
        if args.debug:
            traceback.print_exc()
        else:
            console.print(f"[red]Error:[/red] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
