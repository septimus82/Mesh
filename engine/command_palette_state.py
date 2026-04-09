from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from engine import json_io
from engine.logging_tools import get_logger
from engine.repo_root import get_repo_root

_LOG = get_logger(__name__)

_STATE_SCHEMA_VERSION = 1
_DEFAULT_STATE_DIRNAME = ".mesh"
_DEFAULT_STATE_FILENAME = "command_palette_state.json"
_STATE_PATH_ENV = "MESH_COMMAND_PALETTE_STATE_PATH"

_DEFAULT_MAX_RECENTS = 12
_DEFAULT_MAX_ENTRIES_PER_COMMAND = 32
_DEFAULT_MAX_COMMANDS = 128


def resolve_command_palette_state_path(
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
) -> Path:
    if path is not None:
        return Path(path)
    env_path = str(os.environ.get(_STATE_PATH_ENV, "") or "").strip()
    if env_path:
        return Path(env_path)
    root = repo_root if repo_root is not None else get_repo_root()
    return root / _DEFAULT_STATE_DIRNAME / _DEFAULT_STATE_FILENAME


def _normalize_recent_commands(raw: Any, *, max_entries: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        text = str(value or "").strip()
        if not text:
            continue
        if text in out:
            continue
        out.append(text)
        if len(out) >= max_entries:
            break
    return out


def _normalize_prompt_history(
    raw: Any,
    *,
    max_commands: int,
    max_entries_per_command: int,
) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    command_ids = sorted(str(key or "").strip() for key in raw.keys())
    for command_id in command_ids:
        if not command_id:
            continue
        values = raw.get(command_id)
        if not isinstance(values, list):
            continue
        entries: list[str] = []
        for item in values:
            text = str(item or "")
            if not text.strip():
                continue
            entries.append(text)
        if max_entries_per_command > 0 and len(entries) > max_entries_per_command:
            entries = entries[-max_entries_per_command:]
        if entries:
            out[command_id] = entries
        if len(out) >= max_commands:
            break
    return out


def dump_palette_state(
    recents: Sequence[str],
    history: Mapping[str, Sequence[str]],
    *,
    max_recents: int = _DEFAULT_MAX_RECENTS,
    max_entries_per_command: int = _DEFAULT_MAX_ENTRIES_PER_COMMAND,
    max_commands: int = _DEFAULT_MAX_COMMANDS,
) -> dict[str, Any]:
    normalized_recents = _normalize_recent_commands(
        list(recents),
        max_entries=max(0, int(max_recents)),
    )
    normalized_history = _normalize_prompt_history(
        {str(k): list(v) for k, v in history.items()},
        max_commands=max(0, int(max_commands)),
        max_entries_per_command=max(0, int(max_entries_per_command)),
    )
    return {
        "schema_version": _STATE_SCHEMA_VERSION,
        "recents": normalized_recents,
        "history": normalized_history,
    }


def load_palette_state(
    payload: Any,
    *,
    max_recents: int = _DEFAULT_MAX_RECENTS,
    max_entries_per_command: int = _DEFAULT_MAX_ENTRIES_PER_COMMAND,
    max_commands: int = _DEFAULT_MAX_COMMANDS,
) -> tuple[list[str], dict[str, list[str]]]:
    if not isinstance(payload, dict):
        return [], {}
    try:
        schema_version = int(payload.get("schema_version", 0))
    except Exception:
        schema_version = 0
    if schema_version != _STATE_SCHEMA_VERSION:
        return [], {}
    recents = _normalize_recent_commands(
        payload.get("recents"),
        max_entries=max(0, int(max_recents)),
    )
    history = _normalize_prompt_history(
        payload.get("history"),
        max_commands=max(0, int(max_commands)),
        max_entries_per_command=max(0, int(max_entries_per_command)),
    )
    return recents, history


def load_command_palette_state(
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
    max_recents: int = _DEFAULT_MAX_RECENTS,
    max_entries_per_command: int = _DEFAULT_MAX_ENTRIES_PER_COMMAND,
    max_commands: int = _DEFAULT_MAX_COMMANDS,
) -> tuple[list[str], dict[str, list[str]]]:
    state_path = resolve_command_palette_state_path(path, repo_root=repo_root)
    try:
        payload = json_io.read_json(state_path)
    except FileNotFoundError:
        return [], {}
    except Exception as exc:  # noqa: BLE001  # REASON: unreadable palette state files should fall back to empty state without breaking startup
        _LOG.warning("Failed to load command palette state from %s: %s", state_path, exc)
        return [], {}
    return load_palette_state(
        payload,
        max_recents=max_recents,
        max_entries_per_command=max_entries_per_command,
        max_commands=max_commands,
    )


def save_command_palette_state(
    recents: Sequence[str],
    history: Mapping[str, Sequence[str]],
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
    max_recents: int = _DEFAULT_MAX_RECENTS,
    max_entries_per_command: int = _DEFAULT_MAX_ENTRIES_PER_COMMAND,
    max_commands: int = _DEFAULT_MAX_COMMANDS,
) -> None:
    state_path = resolve_command_palette_state_path(path, repo_root=repo_root)
    payload = dump_palette_state(
        recents,
        history,
        max_recents=max_recents,
        max_entries_per_command=max_entries_per_command,
        max_commands=max_commands,
    )
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        json_io.write_json_atomic(state_path, payload)
    except Exception as exc:  # noqa: BLE001  # REASON: state file write failures should log and preserve in-memory palette state
        _LOG.warning("Failed to save command palette state to %s: %s", state_path, exc)
