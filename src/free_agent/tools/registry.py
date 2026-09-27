import json
import logging
from collections.abc import Callable

from pydantic import ValidationError

from .base import Tool, result_json, schema_for

log = logging.getLogger(__name__)
Approval = Callable[[str, dict], bool]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def schemas_for(self, names: list[str]) -> list[dict]:
        missing = [name for name in names if name not in self._tools]
        if missing:
            raise ValueError(f"Unknown configured tool: {missing[0]}")
        return [schema_for(self._tools[name]) for name in names]

    def execute(self, name: str, arguments_json: str, *, allowed: list[str],
                approval: Approval | None = None) -> str:
        if name not in allowed or name not in self._tools:
            return result_json(False, error="unknown_tool", message=f"Tool {name!r} is not available.")
        tool = self._tools[name]
        try:
            raw = json.loads(arguments_json)
            if not isinstance(raw, dict):
                raise ValueError("Arguments must be a JSON object.")
            args = tool.args_model.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return result_json(False, error="validation_error", message=str(exc)[:300])
        if tool.side_effects and (approval is None or not approval(name, args.model_dump())):
            return result_json(False, error="approval_required", message="User did not approve this tool call.")
        try:
            value = tool.execute(args)
            log.info("tool=%s ok=true", name)
            return result_json(True, result=value)
        except (ValueError, OSError, UnicodeError) as exc:
            log.info("tool=%s ok=false", name)
            return result_json(False, error="tool_error", message=str(exc)[:300])
        except Exception:
            log.error("tool=%s ok=false unexpected_error", name)
            return result_json(False, error="tool_error", message="Tool failed unexpectedly.")
