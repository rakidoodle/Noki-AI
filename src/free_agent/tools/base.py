import json
from typing import Any, Protocol

from pydantic import BaseModel


class Tool(Protocol):
    name: str
    description: str
    side_effects: bool
    args_model: type[BaseModel]

    def execute(self, arguments: BaseModel) -> Any: ...


def schema_for(tool: Tool) -> dict:
    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description,
        "parameters": tool.args_model.model_json_schema(),
    }}


def result_json(ok: bool, **fields: Any) -> str:
    return json.dumps({"ok": ok, **fields}, ensure_ascii=False, default=str)
