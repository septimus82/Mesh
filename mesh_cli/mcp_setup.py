from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MESH_SERVER_NAME = "mesh"
MCP_INSTALL_NOTE = "Run: pip install -e .[mcp]"


def build_mesh_server_entry(project_root: Path, python_exe: str) -> dict[str, Any]:
    root = Path(project_root).resolve()
    return {
        "command": str(python_exe),
        "args": ["-m", "engine.mcp_server.server"],
        "cwd": str(root),
    }


def claude_desktop_config_path(platform: str, env: Mapping[str, str]) -> Path:
    if platform == "win32":
        appdata = env.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    if platform == "darwin":
        home = env.get("HOME")
        base = Path(home) if home else Path.home()
        return base / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    home = env.get("HOME")
    base = Path(home) if home else Path.home()
    return base / ".config" / "Claude" / "claude_desktop_config.json"


def merge_mcp_server(existing_config: dict[str, Any], name: str, entry: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing_config)
    existing_servers = merged.get("mcpServers")
    servers = dict(existing_servers) if isinstance(existing_servers, dict) else {}
    servers[str(name)] = dict(entry)
    merged["mcpServers"] = servers
    return merged


def build_mesh_mcp_config(project_root: Path, python_exe: str) -> dict[str, Any]:
    entry = build_mesh_server_entry(project_root, python_exe)
    return {"mcpServers": {MESH_SERVER_NAME: entry}}


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _mcp_sdk_available() -> bool:
    try:
        importlib.import_module("mcp")
    except Exception:
        return False
    return True


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in MCP client config: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"MCP client config root must be an object: {path}")
    return payload


def _write_config(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(payload), encoding="utf-8")


def _backup_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_path = Path(f"{path}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def _resolve_client_config_path(client: str) -> Path:
    if client != "claude-desktop":
        raise ValueError(f"Unsupported MCP client: {client}")
    return claude_desktop_config_path(sys.platform, os.environ)


def handle_mcp_config(args: argparse.Namespace, *, project_root: Path | None = None, python_exe: str | None = None) -> int:
    root = Path.cwd() if project_root is None else Path(project_root)
    exe = sys.executable if python_exe is None else python_exe
    sys.stdout.write(_json_dumps(build_mesh_mcp_config(root, exe)))
    return 0


def install_mcp_config(
    *,
    client: str = "claude-desktop",
    project_root: Path | None = None,
    python_exe: str | None = None,
    config_path: Path | None = None,
) -> tuple[Path, Path | None, dict[str, Any], bool]:
    target_path = Path(config_path) if config_path is not None else _resolve_client_config_path(client)
    root = Path.cwd() if project_root is None else Path(project_root)
    exe = sys.executable if python_exe is None else python_exe
    entry = build_mesh_server_entry(root, exe)
    existing = _read_config(target_path)
    merged = merge_mcp_server(existing, MESH_SERVER_NAME, entry)
    backup_path = _backup_existing(target_path)
    _write_config(target_path, merged)
    return target_path, backup_path, merged, _mcp_sdk_available()


def handle_mcp_install(args: argparse.Namespace, *, project_root: Path | None = None, python_exe: str | None = None) -> int:
    client = str(getattr(args, "client", "claude-desktop") or "claude-desktop")
    config_path_arg = getattr(args, "config_path", None)
    config_path = Path(config_path_arg) if config_path_arg else None
    try:
        path, backup_path, _merged, mcp_available = install_mcp_config(
            client=client,
            project_root=project_root,
            python_exe=python_exe,
            config_path=config_path,
        )
    except ValueError as exc:
        print(f"[Mesh][MCP] ERROR: {exc}")
        return 2

    print(f"[Mesh][MCP] Installed '{MESH_SERVER_NAME}' server in {path}")
    if backup_path is not None:
        print(f"[Mesh][MCP] Backup written to {backup_path}")
    if not mcp_available:
        print(f"[Mesh][MCP] Optional MCP SDK is not installed. {MCP_INSTALL_NOTE}")
    print("[Mesh][MCP] Next steps: fully restart Claude Desktop, then enable the Mesh server.")
    return 0


def handle(args: argparse.Namespace) -> int:
    mcp_command = str(getattr(args, "mcp_command", "") or "")
    if mcp_command == "config":
        return handle_mcp_config(args)
    if mcp_command == "install":
        return handle_mcp_install(args)
    print("[Mesh][CLI] Error: missing mcp subcommand")
    return 2
