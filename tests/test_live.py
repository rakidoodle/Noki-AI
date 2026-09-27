import pytest

from free_agent.client import OpenRouterClient
from free_agent.config import load_settings


@pytest.mark.live
def test_one_tiny_completion():
    settings = load_settings()
    if not settings.api_key:
        pytest.skip("OPENROUTER_API_KEY is not configured")
    reply = OpenRouterClient(settings).complete(
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_requests=1,
    )
    assert reply.content and reply.content.strip()
