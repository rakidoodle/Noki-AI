"""Environment-backed settings; a key is needed only for live runs."""
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from .errors import ConfigurationError


class Settings(BaseModel):
    api_key: str = ""
    model: str = "openrouter/free"
    base_url: str = "https://openrouter.ai/api/v1"
    http_referer: str | None = None
    app_name: str = "OpenRouter Free Agent Starter"
    max_model_calls: int = Field(default=8, gt=0)
    max_tool_calls: int = Field(default=12, gt=0)
    max_steps: int = Field(default=12, gt=0)
    request_timeout_seconds: float = Field(default=90, gt=0)
    retry_attempts: int = Field(default=2, ge=0, le=5)
    workspace: Path = Path("workspace")
    log_level: str = "INFO"

    @field_validator("model")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def secure_base_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
                parsed.password or parsed.query or parsed.fragment):
            raise ValueError("base URL must be an HTTPS URL without credentials or a query")
        return value.strip().rstrip("/")

    @field_validator("workspace")
    @classmethod
    def resolved_workspace(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    def prepare_workspace(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)

    def require_api_key(self) -> None:
        if not self.api_key.strip():
            raise ConfigurationError("Set OPENROUTER_API_KEY in the environment or .env before a live run.")


def load_settings(*, env_file: bool = True) -> Settings:
    if env_file:
        load_dotenv()
    env = os.environ
    return Settings(
        api_key=env.get("OPENROUTER_API_KEY", "").strip(),
        model=env.get("OPENROUTER_MODEL", "openrouter/free"),
        base_url=env.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        http_referer=env.get("OPENROUTER_HTTP_REFERER") or None,
        app_name=env.get("OPENROUTER_APP_NAME", "OpenRouter Free Agent Starter"),
        max_model_calls=env.get("AGENT_MAX_MODEL_CALLS", 8),
        max_tool_calls=env.get("AGENT_MAX_TOOL_CALLS", 12),
        max_steps=env.get("AGENT_MAX_STEPS", 12),
        request_timeout_seconds=env.get("AGENT_REQUEST_TIMEOUT_SECONDS", 90),
        retry_attempts=env.get("AGENT_RETRY_ATTEMPTS", 2),
        workspace=Path(env.get("AGENT_WORKSPACE", "./workspace")),
        log_level=env.get("LOG_LEVEL", "INFO"),
    )
