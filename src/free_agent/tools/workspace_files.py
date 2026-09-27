"""Symlink-aware, size-capped text tools scoped to one workspace."""
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictBool

MAX_TEXT_BYTES = 64 * 1024
MAX_LIST_ENTRIES = 200
MAX_LIST_SCAN_ENTRIES = 5000
BLOCKED_NAMES = {".env", ".env.local", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
BLOCKED_FRAGMENTS = ("secret", "credential", "token", "api_key", "apikey", "private_key", "service_account")


def _blocked_name(name: str) -> bool:
    lower = name.lower()
    return (name.startswith(".") or lower in BLOCKED_NAMES or
            any(fragment in lower for fragment in BLOCKED_FRAGMENTS) or
            lower.endswith((".pem", ".key")))


class PathArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)


class WriteArgs(PathArgs):
    content: str = Field(max_length=MAX_TEXT_BYTES)
    overwrite: StrictBool = False


class ListArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass


class WorkspaceTool:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def _path(self, requested: str) -> Path:
        relative = Path(requested)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Path must be relative to the workspace.")
        candidate = self.workspace / relative
        current = self.workspace
        for part in relative.parts:
            if _blocked_name(part):
                raise ValueError("Hidden or credential paths are not available.")
            current /= part
            if current.is_symlink():
                raise ValueError("Symlink paths are not available.")
        path = candidate.resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError("Path escapes the workspace.")
        if path.is_file() and path.stat().st_nlink > 1:
            raise ValueError("Hard-linked files are not available.")
        return path


class ListWorkspaceFiles(WorkspaceTool):
    name = "list_workspace_files"
    description = "List visible files under the configured workspace."
    side_effects = False
    args_model = ListArgs

    def execute(self, arguments: ListArgs) -> list[str]:
        files: list[str] = []
        directories = [self.workspace]
        scanned = 0
        while directories:
            directory = directories.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > MAX_LIST_SCAN_ENTRIES:
                        raise ValueError("Workspace has too many entries to list safely.")
                    if _blocked_name(entry.name) or entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        path = Path(entry.path)
                        try:
                            self._path(str(path.relative_to(self.workspace)))
                        except ValueError:
                            continue
                        files.append(str(path.relative_to(self.workspace)))
                        if len(files) >= MAX_LIST_ENTRIES:
                            return sorted(files)
        return sorted(files)


class ReadWorkspaceText(WorkspaceTool):
    name = "read_workspace_text"
    description = "Read a small UTF-8 text file from the workspace."
    side_effects = False
    args_model = PathArgs

    def execute(self, arguments: PathArgs) -> str:
        path = self._path(arguments.path)
        if not path.is_file():
            raise ValueError("File does not exist.")
        with path.open("rb") as stream:
            data = stream.read(MAX_TEXT_BYTES + 1)
        if len(data) > MAX_TEXT_BYTES:
            raise ValueError("File exceeds the text size limit.")
        if b"\x00" in data:
            raise ValueError("Only UTF-8 text files are supported.")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Only UTF-8 text files are supported.") from exc


class WriteWorkspaceText(WorkspaceTool):
    name = "write_workspace_text"
    description = "Write a small UTF-8 text file inside the workspace. Requires approval."
    side_effects = True
    args_model = WriteArgs

    def execute(self, arguments: WriteArgs) -> str:
        path = self._path(arguments.path)
        if len(arguments.content.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("Content exceeds the text size limit.")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Check again after directory creation in case a path changed.
        path = self._path(arguments.path)
        if path.exists() and not arguments.overwrite:
            raise ValueError("File already exists; set overwrite=true to replace it.")
        with path.open("w" if arguments.overwrite else "x", encoding="utf-8") as stream:
            stream.write(arguments.content)
        return str(path.relative_to(self.workspace))
