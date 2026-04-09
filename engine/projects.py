from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from . import json_io
from .repo_root import get_repo_root

MAX_RECENTS = 8
_PROJECTS_ENV = "MESH_PROJECTS_PATH"


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def _normalize_root(root: str) -> str:
    text = str(root or "").strip()
    if not text:
        return ""
    try:
        path = Path(text).expanduser()
        if path.exists():
            path = path.resolve()
        return str(path)
    except Exception:  # noqa: BLE001  # REASON: invalid project-root path strings should fall back to the original text for later resolution
        return text


def _resolve_projects_path(path: str | Path | None = None) -> Path | None:
    if _is_web_runtime():
        return None
    if path is not None:
        return Path(path)
    env = (os.environ.get(_PROJECTS_ENV) or "").strip()
    if env:
        return Path(env)
    root = get_repo_root()
    return root / "projects.json"


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        raw = json_io.read_json(path)
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001  # REASON: malformed project metadata payloads should fall back to no persisted projects payload
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _load_payload(path: Path) -> dict[str, Any]:
    payload = _read_payload(path)
    if payload is None:
        return {"version": 1, "recent_roots": [], "last_root": None}
    if not isinstance(payload.get("recent_roots"), list):
        payload["recent_roots"] = []
    return payload


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    json_io.write_json_atomic(path, payload)


def is_valid_project_root(path: Path) -> bool:
    """Check if the path looks like a valid Mesh project root."""
    if not path.exists() or not path.is_dir():
        return False
    # Must have config.json OR packs/ directory
    if (path / "config.json").exists():
        return True
    if (path / "packs").exists() and (path / "packs").is_dir():
        return True
    return False


def remove_recent_project(root: str) -> None:
    resolved = _resolve_projects_path()
    if resolved is None:
        return
    normalized = _normalize_root(root)
    if not normalized:
        return
    payload = _load_payload(resolved)
    recent = payload.get("recent_roots", [])
    if not isinstance(recent, list):
        recent = []
    
    # Filter out matches
    new_recent = [r for r in recent if _normalize_root(r) != normalized]
    
    # If change occurred, save
    if len(new_recent) != len(recent):
        payload["recent_roots"] = new_recent
        _write_payload(resolved, payload)


def get_recent_projects() -> list[str]:
    resolved = _resolve_projects_path()
    if resolved is None:
        return []
    payload = _load_payload(resolved)
    roots = payload.get("recent_roots", [])
    if not isinstance(roots, list):
        return []
    recent: list[str] = []
    seen: set[str] = set()
    for root in roots:
        normalized = _normalize_root(root)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        recent.append(normalized)
        if len(recent) >= MAX_RECENTS:
            break
    return recent


def add_recent_project(root: str) -> None:
    resolved = _resolve_projects_path()
    if resolved is None:
        return
    normalized = _normalize_root(root)
    if not normalized:
        return
    payload = _load_payload(resolved)
    recent = payload.get("recent_roots", [])
    if not isinstance(recent, list):
        recent = []
    recent = [normalized] + [item for item in recent if _normalize_root(item) != normalized]
    recent = recent[:MAX_RECENTS]
    payload["recent_roots"] = recent
    payload["last_root"] = normalized
    payload["version"] = 1
    _write_payload(resolved, payload)


def set_last_project(root: str | None) -> None:
    resolved = _resolve_projects_path()
    if resolved is None:
        return
    payload = _load_payload(resolved)
    normalized = _normalize_root(root or "")
    payload["last_root"] = normalized or None
    payload["version"] = 1
    _write_payload(resolved, payload)
