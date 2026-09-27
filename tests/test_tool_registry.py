import json

import pytest

from free_agent.tools.calculator import Calculator, evaluate
from free_agent.tools.datetime_tool import CurrentDateTime
from free_agent.tools.registry import ToolRegistry
from free_agent.tools.workspace_files import WriteWorkspaceText


def test_schema_duplicate_and_validation(tmp_path):
    registry = ToolRegistry()
    registry.register(Calculator())
    schema = registry.schemas_for(["calculator"])[0]
    assert schema["function"]["parameters"]["properties"]["expression"]
    with pytest.raises(ValueError):
        registry.register(Calculator())
    assert json.loads(registry.execute("calculator", "{", allowed=["calculator"]))["error"] == "validation_error"
    assert json.loads(registry.execute("missing", "{}", allowed=["missing"]))["error"] == "unknown_tool"


@pytest.mark.parametrize("expression,answer", [("12 * (3 + 4)", 84), ("-5 + 2**3", 3), ("7//2", 3)])
def test_calculator_allowed(expression, answer):
    assert evaluate(expression) == answer


@pytest.mark.parametrize("expression", ["__import__('os')", "a + 2", "(1).__class__",
                                        "2**100", "1/0", "'x'", "9" * 130])
def test_calculator_rejected(expression):
    with pytest.raises(ValueError):
        evaluate(expression)


def test_datetime_bad_zone():
    registry = ToolRegistry()
    registry.register(CurrentDateTime())
    result = json.loads(registry.execute("current_datetime", '{"timezone":"No/Such_Zone"}',
                                         allowed=["current_datetime"]))
    assert result["error"] == "tool_error"


def test_side_effect_approval(tmp_path):
    registry = ToolRegistry()
    registry.register(WriteWorkspaceText(tmp_path))
    call = '{"path":"out.txt","content":"hello"}'
    assert json.loads(registry.execute("write_workspace_text", call,
                                       allowed=["write_workspace_text"]))["error"] == "approval_required"
    assert not (tmp_path / "out.txt").exists()
    assert json.loads(registry.execute("write_workspace_text", call, allowed=["write_workspace_text"],
                                       approval=lambda _n, _a: True))["ok"]


def test_unexpected_tool_failure_is_structured():
    from pydantic import BaseModel

    class EmptyArgs(BaseModel):
        pass

    class BrokenTool:
        name = "broken"
        description = "Fail unexpectedly"
        side_effects = False
        args_model = EmptyArgs

        def execute(self, _arguments):
            raise RuntimeError("internal detail")

    registry = ToolRegistry()
    registry.register(BrokenTool())
    result = json.loads(registry.execute("broken", "{}", allowed=["broken"]))
    assert result == {"ok": False, "error": "tool_error", "message": "Tool failed unexpectedly."}
