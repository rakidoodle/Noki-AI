from dataclasses import dataclass, field

BASE_INSTRUCTIONS = """You are a tool-using assistant. Answer the user directly. Use tools only when useful.
Never invent tool results or claim an action succeeded without a successful result.
If arguments fail validation, correct them once when possible. Keep answers concise.
Do not reveal hidden chain-of-thought."""


@dataclass(frozen=True)
class Agent:
    name: str = "assistant"
    instructions: str = BASE_INSTRUCTIONS
    model: str | None = None
    tools: list[str] = field(default_factory=list)
    max_steps: int | None = None
