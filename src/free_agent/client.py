"""Thin OpenAI-compatible OpenRouter adapter with bounded retries."""
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, AuthenticationError as SDKAuthenticationError
from openai import BadRequestError, NotFoundError, OpenAI, PermissionDeniedError, RateLimitError as SDKRateLimitError
from openai import APIStatusError

from .config import Settings
from .errors import AuthenticationError, BudgetExceeded, ModelCapabilityError, ProviderUnavailableError, RateLimitError
from .messages import ModelReply, ToolCall

log = logging.getLogger(__name__)


def _retry_after_seconds(error: APIStatusError) -> float | None:
    value = error.response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


class OpenRouterClient:
    def __init__(self, settings: Settings, sdk: Any | None = None, sleep=time.sleep) -> None:
        self.settings = settings
        self.sleep = sleep
        self.request_count = 0
        if sdk is None:
            settings.require_api_key()
            headers = {"X-Title": settings.app_name}
            if settings.http_referer:
                headers["HTTP-Referer"] = settings.http_referer
            sdk = OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                         timeout=settings.request_timeout_seconds, max_retries=0,
                         default_headers=headers)
        self.sdk = sdk

    def complete(self, *, messages: list[dict], tools: list[dict] | None = None,
                 model: str | None = None, tool_choice: str | dict | None = None,
                 temperature: float | None = None, max_requests: int | None = None) -> ModelReply:
        kwargs: dict[str, Any] = {"model": model or self.settings.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if temperature is not None:
            kwargs["temperature"] = temperature
        for attempt in range(self.settings.retry_attempts + 1):
            if max_requests is not None and attempt >= max_requests:
                raise BudgetExceeded("Model-call budget reached during retries.")
            self.request_count += 1
            log.info("model request count=%d model=%s", self.request_count, kwargs["model"])
            try:
                response = self.sdk.chat.completions.create(**kwargs)
                choice = response.choices[0].message
                calls = [ToolCall(id=call.id, name=call.function.name,
                                  arguments=call.function.arguments)
                         for call in (choice.tool_calls or [])]
                raw_usage = getattr(response, "usage", None)
                usage = raw_usage.model_dump() if hasattr(raw_usage, "model_dump") else (
                    raw_usage if isinstance(raw_usage, dict) else None)
                return ModelReply(content=choice.content, tool_calls=calls,
                                  response_id=response.id, usage=usage)
            except (SDKAuthenticationError, PermissionDeniedError) as exc:
                raise AuthenticationError("OpenRouter rejected the API key or account permissions (401/403).") from exc
            except (BadRequestError, NotFoundError) as exc:
                if tools:
                    raise ModelCapabilityError("The model or request may not support these tools. Try openrouter/free or a tool-capable model.") from exc
                raise ModelCapabilityError("The model or request was rejected. Check OPENROUTER_MODEL and request settings.") from exc
            except SDKRateLimitError as exc:
                # A quota limit is not helped by immediate repeated requests.
                raise RateLimitError("OpenRouter rate limit reached (429). Retry later or reduce agent steps.") from exc
            except (APIConnectionError, APITimeoutError, APIStatusError) as exc:
                transient = isinstance(exc, (APIConnectionError, APITimeoutError)) or (
                    isinstance(exc, APIStatusError) and exc.status_code >= 500)
                if isinstance(exc, APIStatusError) and exc.status_code in (400, 404, 422):
                    raise ModelCapabilityError("The model or request was rejected. Check model ID and tool support.") from exc
                if not transient or attempt >= self.settings.retry_attempts:
                    raise ProviderUnavailableError("OpenRouter request failed; check service availability and connection.") from exc
                delay = (2 ** attempt) + random.uniform(0, 1)
                if isinstance(exc, APIStatusError):
                    hint = _retry_after_seconds(exc)
                    if hint is not None:
                        delay = max(delay, hint)
                if delay > 10:
                    raise ProviderUnavailableError("OpenRouter asked to retry later; this run stopped.") from exc
                self.sleep(delay)
        raise AssertionError("retry loop exhausted")
