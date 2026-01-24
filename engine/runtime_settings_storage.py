from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .repo_root import get_repo_root
from .runtime_settings import RuntimeSettings


_SETTINGS_ENV = "MESH_RUNTIME_SETTINGS_PATH"


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def resolve_runtime_settings_path(path: str | Path | None = None) -> Path | None:
    if _is_web_runtime():
        return None
    if path is not None:
        return Path(path)
    env = (os.environ.get(_SETTINGS_ENV) or "").strip()
    if env:
        return Path(env)
    root = get_repo_root()
    return root / "user_settings.json"


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


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
    payload = _read_payload(resolved)
    if payload is None:
        return base
    try:
        version = int(payload.get("version", 0))
    except Exception:
        version = 0
    if version != 1:
        return base
    return RuntimeSettings.from_payload(payload, base=base)


def save_runtime_settings(path: str | Path | None, settings: RuntimeSettings) -> None:
    resolved = resolve_runtime_settings_path(path)
    if resolved is None:
        return
    payload = {
        "version": 1,
        **settings.to_payload(),
    }
    resolved.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    resolved.write_text(text, encoding="utf-8", newline="\n")
