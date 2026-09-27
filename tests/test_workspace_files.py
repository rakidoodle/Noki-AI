import json
import os

from free_agent.tools.registry import ToolRegistry
from free_agent.tools.workspace_files import ListWorkspaceFiles, ReadWorkspaceText, WriteWorkspaceText


def test_workspace_files_and_overwrite(tmp_path):
    registry = ToolRegistry()
    for tool in (ListWorkspaceFiles(tmp_path), ReadWorkspaceText(tmp_path), WriteWorkspaceText(tmp_path)):
        registry.register(tool)
    allowed = list(registry._tools)
    approve = lambda _n, _a: True
    write = lambda args: json.loads(registry.execute("write_workspace_text", json.dumps(args),
                                                  allowed=allowed, approval=approve))
    assert write({"path": "notes/a.txt", "content": "hi"})["ok"]
    assert write({"path": "notes/a.txt", "content": "bye"})["ok"] is False
    assert write({"path": "notes/a.txt", "content": "bye", "overwrite": True})["ok"]
    read = json.loads(registry.execute("read_workspace_text", '{"path":"notes/a.txt"}', allowed=allowed))
    assert read["result"] == "bye"
    listing = json.loads(registry.execute("list_workspace_files", "{}", allowed=allowed))
    assert listing["result"] == ["notes/a.txt"]


def test_traversal_secrets_and_symlink(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    (tmp_path / "link.txt").symlink_to(outside)
    registry = ToolRegistry()
    registry.register(ReadWorkspaceText(tmp_path))
    for path in ("../outside.txt", "link.txt", ".env", "credentials.json"):
        result = json.loads(registry.execute("read_workspace_text", json.dumps({"path": path}),
                                             allowed=["read_workspace_text"]))
        assert result["ok"] is False


def test_internal_symlink_cannot_expose_or_overwrite_env(tmp_path):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=private")
    (tmp_path / "alias.txt").symlink_to(tmp_path / ".env")
    registry = ToolRegistry()
    for tool in (ListWorkspaceFiles(tmp_path), ReadWorkspaceText(tmp_path), WriteWorkspaceText(tmp_path)):
        registry.register(tool)
    allowed = list(registry._tools)
    read = json.loads(registry.execute("read_workspace_text", '{"path":"alias.txt"}', allowed=allowed))
    assert read["ok"] is False
    write = json.loads(registry.execute("write_workspace_text",
                                        '{"path":"alias.txt","content":"changed","overwrite":true}',
                                        allowed=allowed, approval=lambda _n, _a: True))
    assert write["ok"] is False
    listing = json.loads(registry.execute("list_workspace_files", "{}", allowed=allowed))
    assert listing["result"] == []
    assert (tmp_path / ".env").read_text() == "OPENROUTER_API_KEY=private"


def test_read_rejects_oversized_and_binary_files(tmp_path):
    (tmp_path / "large.txt").write_bytes(b"a" * (64 * 1024 + 1))
    (tmp_path / "binary.txt").write_bytes(b"hello\x00world")
    registry = ToolRegistry()
    registry.register(ReadWorkspaceText(tmp_path))
    for name in ("large.txt", "binary.txt"):
        result = json.loads(registry.execute("read_workspace_text", json.dumps({"path": name}),
                                             allowed=["read_workspace_text"]))
        assert result["ok"] is False


def test_hardlink_cannot_expose_env(tmp_path):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=private")
    os.link(tmp_path / ".env", tmp_path / "alias.txt")
    registry = ToolRegistry()
    for tool in (ListWorkspaceFiles(tmp_path), ReadWorkspaceText(tmp_path), WriteWorkspaceText(tmp_path)):
        registry.register(tool)
    allowed = list(registry._tools)
    read = json.loads(registry.execute("read_workspace_text", '{"path":"alias.txt"}', allowed=allowed))
    assert read["ok"] is False
    write = json.loads(registry.execute("write_workspace_text",
                                        '{"path":"alias.txt","content":"changed","overwrite":true}',
                                        allowed=allowed, approval=lambda _n, _a: True))
    assert write["ok"] is False
    listing = json.loads(registry.execute("list_workspace_files", "{}", allowed=allowed))
    assert listing["result"] == []
    assert (tmp_path / ".env").read_text() == "OPENROUTER_API_KEY=private"


def test_list_scan_and_strict_write_arguments(monkeypatch, tmp_path):
    from free_agent.tools import workspace_files

    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    monkeypatch.setattr(workspace_files, "MAX_LIST_SCAN_ENTRIES", 1)
    registry = ToolRegistry()
    registry.register(ListWorkspaceFiles(tmp_path))
    registry.register(WriteWorkspaceText(tmp_path))
    listing = json.loads(registry.execute("list_workspace_files", "{}", allowed=["list_workspace_files"]))
    assert listing["error"] == "tool_error"
    write = json.loads(registry.execute("write_workspace_text",
                                        '{"path":"new.txt","content":"hello","overwrite":"yes"}',
                                        allowed=["write_workspace_text"], approval=lambda _n, _a: True))
    assert write["error"] == "validation_error"
    assert not (tmp_path / "new.txt").exists()
