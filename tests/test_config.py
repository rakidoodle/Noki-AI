from pathlib import Path

import pytest
from pydantic import ValidationError

from free_agent.config import Settings
from free_agent.errors import ConfigurationError


def test_defaults_and_workspace(tmp_path):
    settings = Settings(workspace=tmp_path / "a" / ".." / "work")
    assert settings.model == "openrouter/free"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.workspace == (tmp_path / "work").resolve()
    settings.prepare_workspace()
    assert settings.workspace.is_dir()


@pytest.mark.parametrize("field,value", [("max_steps", 0), ("max_model_calls", -1),
                                         ("max_tool_calls", 0), ("model", " "),
                                         ("base_url", "http://example.com/api/v1"),
                                         ("base_url", "https://user:pass@example.com/api/v1")])
def test_invalid_settings(field, value, tmp_path):
    with pytest.raises(ValidationError):
        Settings(workspace=tmp_path, **{field: value})


def test_key_required_only_for_live(tmp_path):
    with pytest.raises(ConfigurationError):
        Settings(workspace=tmp_path).require_api_key()
