from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from mesh_cli import main
from mesh_cli.mcp_setup import (
    build_mesh_server_entry,
    claude_desktop_config_path,
    install_mcp_config,
    merge_mcp_server,
)


def test_build_mesh_server_entry_uses_python_module_and_project_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    entry = build_mesh_server_entry(root, "python-test")

    assert entry == {
        "command": "python-test",
        "args": ["-m", "engine.mcp_server.server"],
        "cwd": str(root.resolve()),
    }


def test_claude_desktop_config_path_resolves_per_platform() -> None:
    win_path = claude_desktop_config_path("win32", {"APPDATA": r"C:\Users\dev\AppData\Roaming"})
    mac_path = claude_desktop_config_path("darwin", {"HOME": "/Users/dev"})
    linux_path = claude_desktop_config_path("linux", {"HOME": "/home/dev"})

    assert str(win_path).replace("\\", "/").endswith(
        "C:/Users/dev/AppData/Roaming/Claude/claude_desktop_config.json",
    )
    assert mac_path == Path("/Users/dev/Library/Application Support/Claude/claude_desktop_config.json")
    assert linux_path == Path("/home/dev/.config/Claude/claude_desktop_config.json")


def test_merge_mcp_server_preserves_other_keys_and_is_idempotent() -> None:
    existing = {
        "global": {"theme": "dark"},
        "mcpServers": {
            "other": {"command": "node", "args": ["server.js"]},
            "mesh": {"command": "old", "args": [], "cwd": "old"},
        },
    }
    entry = {"command": "python", "args": ["-m", "engine.mcp_server.server"], "cwd": "/project"}

    once = merge_mcp_server(existing, "mesh", entry)
    twice = merge_mcp_server(once, "mesh", entry)

    assert once == twice
    assert once["global"] == {"theme": "dark"}
    assert once["mcpServers"]["other"] == {"command": "node", "args": ["server.js"]}
    assert once["mcpServers"]["mesh"] == entry


def test_mesh_mcp_config_prints_valid_json_for_current_project(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["mcp", "config"]) == 0

    payload = json.loads(capsys.readouterr().out)
    entry = payload["mcpServers"]["mesh"]
    assert entry["command"] == sys.executable
    assert entry["args"] == ["-m", "engine.mcp_server.server"]
    assert entry["cwd"] == str(tmp_path.resolve())


def test_mesh_mcp_install_writes_merged_config_and_backup(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir()
    original = {
        "global": {"theme": "dark"},
        "mcpServers": {
            "other": {"command": "node", "args": ["server.js"]},
            "mesh": {"command": "old", "args": [], "cwd": "old"},
        },
    }
    config_path.write_text(json.dumps(original, indent=2), encoding="utf-8")
    monkeypatch.chdir(project_root)

    assert main(["mcp", "install", "--config-path", str(config_path)]) == 0

    backup_path = Path(f"{config_path}.bak")
    assert backup_path.exists()
    assert json.loads(backup_path.read_text(encoding="utf-8")) == original

    installed = cast(dict[str, Any], json.loads(config_path.read_text(encoding="utf-8")))
    installed_servers = cast(dict[str, Any], installed["mcpServers"])
    original_servers = cast(dict[str, Any], original["mcpServers"])
    assert installed["global"] == original["global"]
    assert installed_servers["other"] == original_servers["other"]
    assert installed_servers["mesh"] == {
        "command": sys.executable,
        "args": ["-m", "engine.mcp_server.server"],
        "cwd": str(project_root.resolve()),
    }

    _, _, installed_again, _ = install_mcp_config(config_path=config_path, project_root=project_root)
    assert installed_again == installed
    assert json.loads(config_path.read_text(encoding="utf-8")) == installed
