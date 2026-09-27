"""The API boundary keeps tool-call IDs and assistant tool requests intact."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str

    def as_api_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": "function", "function": {"name": self.name, "arguments": self.arguments}}


@dataclass(frozen=True)
class ModelReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    response_id: str | None = None
    usage: dict[str, Any] | None = None

    def as_assistant_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [call.as_api_dict() for call in self.tool_calls]
        return message


def trim_history(history: list[dict[str, Any]], max_chars: int = 30000) -> list[dict[str, Any]]:
    """Keep newest complete user turns, including their tool-call/result pairs."""
    turns: list[list[dict[str, Any]]] = []
    for message in history:
        if message["role"] == "user":
            turns.append([message])
        elif turns:
            turns[-1].append(message)
    kept: list[list[dict[str, Any]]] = []
    size = 0
    for turn in reversed(turns):
        turn_size = sum(len(str(message)) for message in turn)
        if size + turn_size > max_chars:
            break
        kept.append(turn)
        size += turn_size
    return [message for turn in reversed(kept) for message in turn]
