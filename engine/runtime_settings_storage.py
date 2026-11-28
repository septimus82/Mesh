"""Where a game's runtime settings (volumes, fog, calmer flickering) are kept.

In order: a path given to these functions; ``MESH_RUNTIME_SETTINGS_PATH``; for an exported game (H9.1, #422), the
player's ``user_settings.json`` in that game's per-player folder, beside its saves (engine.save_runtime.storage);
otherwise ``user_settings.json`` in the game's (or Mesh's) folder, as before.

An exported game never writes its installation. One exported before H9.1 kept ``user_settings.json`` there: it is read
when the player has no valid settings of their own, and never changed. A player's own file that can't be read is not
overwritten: the next save first sets it aside as ``user_settings.json.invalid`` (``.invalid.1``, ... when taken).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from . import json_io
from .diagnostics import error as diag_error
from .repo_root import get_repo_root
from .runtime_settings import RuntimeSettings
from .save_runtime import storage as save_storage

_SETTINGS_ENV = "MESH_RUNTIME_SETTINGS_PATH"
SETTINGS_FILE = "user_settings.json"


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def _exported_settings() -> tuple[Path, Path] | None:
    """For an exported game: (the player's settings file, the one an older export kept in its installation)."""
    root = get_repo_root()
    if not save_storage.is_exported_game(root):
        return None
    config = _read_payload(root / "config.json") or {}
    return save_storage.game_data_dir(config) / SETTINGS_FILE, root / SETTINGS_FILE


def resolve_runtime_settings_path(path: str | Path | None = None) -> Path | None:
    if _is_web_runtime():
        return None
    if path is not None:
        return Path(path)
    env = (os.environ.get(_SETTINGS_ENV) or "").strip()
    if env:
        return Path(env)
    exported = _exported_settings()
    if exported is not None:
        return exported[0]
    root = get_repo_root()
    return root / SETTINGS_FILE


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        raw = json_io.read_json(path)
    except FileNotFoundError:
        return None
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _valid_payload(path: Path) -> dict[str, Any] | None:
    """``path``'s settings when it holds settings this version reads (version 1), else None."""
    payload = _read_payload(path)
    if payload is None:
        return None
    try:
        version = int(payload.get("version", 0))
    except Exception:
        version = 0
    return payload if version == 1 else None


def load_runtime_settings(
    path: str | Path | None,
    *,
    base: RuntimeSettings | None = None,
) -> RuntimeSettings:
    if base is None:
        base = RuntimeSettings()
    resolved = resolve_runtime_settings_path(path)
    if resolved is None:
        return base
    candidates = [resolved]
    exported = _exported_settings()
    if exported is not None and resolved == exported[0]:
        candidates.append(exported[1])  # (an older export's, read in place when the player has none of their own)
    for candidate in candidates:
        payload = _valid_payload(candidate)
        if payload is not None:
            return RuntimeSettings.from_payload(payload, base=base)
    return base


def _set_aside_unreadable(path: Path) -> None:
    """Keep a player's settings file this version can't read, instead of writing over it."""
    if not path.exists() or _valid_payload(path) is not None:
        return
    target, n = path.with_name(path.name + ".invalid"), 0
    while target.exists():
        n += 1
        target = path.with_name(f"{path.name}.invalid.{n}")
    os.replace(path, target)


def save_runtime_settings(path: str | Path | None, settings: RuntimeSettings) -> bool:
    """Write ``settings``; False (reported, nothing raised) when they could not be written. The settings stay in
    effect either way; only keeping them for the next start failed."""
    resolved = resolve_runtime_settings_path(path)
    if resolved is None:
        return True
    payload = {
        "version": 1,
        **settings.to_payload(),
    }
    try:
        exported = _exported_settings()
        if exported is not None and resolved == exported[0]:
            _set_aside_unreadable(resolved)
        json_io.write_json_atomic(resolved, payload)
        return True
    except OSError as exc:
        diag_error(
            "settings.save_failed",
            f"Couldn't save settings to '{resolved}': {exc}",
            "engine.runtime_settings_storage",
            location=str(resolved),
            hint="Check that this folder can be written. The settings stay in effect until the game closes.",
        )
        sys.stderr.write(f"[Mesh][Settings] ERROR: couldn't save settings to '{resolved}': {exc}\n")
        return False
