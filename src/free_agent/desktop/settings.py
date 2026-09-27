"""App-local preferences. The desktop app never reads the repository .env."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QStandardPaths

DEFAULT_MODEL = "openrouter/free"


class SettingsError(Exception):
    pass


def default_workspace() -> Path:
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(documents or Path.home() / "Documents") / "Noki AI Workspace"


def default_settings_path() -> Path:
    directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not directory:
        directory = str(Path.home() / "Library" / "Application Support" / "Noki AI")
    return Path(directory) / "settings.json"


def clean_model(value: str) -> str:
    model = value.strip()
    if not model or len(model) > 200 or any(ord(char) < 32 for char in model):
        raise ValueError("Enter a model ID between 1 and 200 characters.")
    return model


@dataclass
class AppPreferences:
    api_key: str = ""
    models: list[str] = field(default_factory=lambda: [DEFAULT_MODEL])
    selected_model: str = DEFAULT_MODEL
    workspace_path: str = field(default_factory=lambda: str(default_workspace()))

    def add_model(self, value: str) -> None:
        model = clean_model(value)
        if model not in self.models:
            if len(self.models) >= 50:
                raise ValueError("You can save up to 50 models.")
            self.models.append(model)
        self.selected_model = model

    def remove_model(self, value: str) -> None:
        if value == DEFAULT_MODEL:
            raise ValueError("The default model cannot be removed.")
        self.models.remove(value)
        if self.selected_model == value:
            self.selected_model = DEFAULT_MODEL

    def validate(self) -> None:
        if len(self.api_key) > 512:
            raise ValueError("The API key is too long.")
        if not isinstance(self.models, list) or not self.models or len(self.models) > 50:
            raise ValueError("The saved model list is invalid.")
        if any(not isinstance(model, str) for model in self.models):
            raise ValueError("The saved model list is invalid.")
        self.models = list(dict.fromkeys(clean_model(model) for model in self.models))
        if DEFAULT_MODEL not in self.models:
            self.models.insert(0, DEFAULT_MODEL)
        if self.selected_model not in self.models:
            self.selected_model = DEFAULT_MODEL
        if not self.workspace_path.strip():
            raise ValueError("Choose a workspace folder.")
        self.workspace_path = str(Path(self.workspace_path).expanduser().resolve())


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> AppPreferences:
        if not self.path.exists():
            return AppPreferences()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Settings must be a JSON object.")
            preferences = AppPreferences(
                api_key=str(data.get("api_key", "")),
                models=data.get("models", [DEFAULT_MODEL]),
                selected_model=str(data.get("selected_model", DEFAULT_MODEL)),
                workspace_path=str(data.get("workspace_path", default_workspace())),
            )
            preferences.validate()
            os.chmod(self.path, 0o600)
            return preferences
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SettingsError("Noki AI could not read its saved settings.") from exc

    def save(self, preferences: AppPreferences) -> None:
        preferences.validate()
        root = self.path.parent
        temporary: str | None = None
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(root, 0o700)
            descriptor, temporary = tempfile.mkstemp(prefix=".noki-settings-", dir=root)
            os.chmod(temporary, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({
                    "api_key": preferences.api_key.strip(),
                    "models": preferences.models,
                    "selected_model": preferences.selected_model,
                    "workspace_path": preferences.workspace_path,
                }, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            os.chmod(self.path, 0o600)
        except OSError as exc:
            raise SettingsError("Noki AI could not save its settings.") from exc
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
