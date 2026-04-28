from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import engine.optional_arcade as optional_arcade

from . import json_io
from .swallowed_exceptions import _log_swallow

DEFAULT_SETTINGS_PATH = Path("artifacts") / "settings.json"
SETTINGS_PATH_ENV = "MESH_SETTINGS_PATH"


@dataclass(slots=True)
class SettingsV1:
    keybinds: dict[str, int] = field(default_factory=dict)
    sfx_volume: float = 1.0
    music_volume: float = 1.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "keybinds": {str(k): int(v) for k, v in (self.keybinds or {}).items()},
            "sfx_volume": float(self.sfx_volume),
            "music_volume": float(self.music_volume),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "SettingsV1":
        if not isinstance(payload, dict):
            return cls()

        keybinds_raw = payload.get("keybinds")
        keybinds: dict[str, int] = {}
        if isinstance(keybinds_raw, dict):
            for action, code in keybinds_raw.items():
                name = str(action).strip()
                if not name:
                    continue
                try:
                    keybinds[name] = int(code)
                except Exception:
                    _log_swallow("SETT-001", "engine/settings.py blanket swallow", once=True)
                    continue

        def _clamp01(value: Any, default: float) -> float:
            try:
                f = float(value)
            except Exception:
                _log_swallow("SETT-002", "engine/settings.py blanket swallow", once=True)
                f = float(default)
            if f < 0.0:
                return 0.0
            if f > 1.0:
                return 1.0
            return f

        return cls(
            keybinds=keybinds,
            sfx_volume=_clamp01(payload.get("sfx_volume", 1.0), 1.0),
            music_volume=_clamp01(payload.get("music_volume", 1.0), 1.0),
        )


def resolve_settings_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get(SETTINGS_PATH_ENV)
    if env:
        return Path(env)
    return DEFAULT_SETTINGS_PATH


def load_settings(path: str | Path | None = None) -> SettingsV1:
    resolved = resolve_settings_path(path)
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return SettingsV1()
    except Exception:
        _log_swallow("SETT-003", "engine/settings.py blanket swallow", once=True)
        return SettingsV1()
    return SettingsV1.from_payload(raw if isinstance(raw, dict) else {})


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    json_io.write_json_atomic(path, payload)


def save_settings(path: str | Path | None, settings: SettingsV1) -> None:
    resolved = resolve_settings_path(path)
    _write_json_atomic(resolved, settings.to_payload())


def apply_settings(window: Any, settings: SettingsV1) -> None:
    audio = getattr(window, "audio", None)
    if audio is not None:
        setter = getattr(audio, "set_sfx_volume", None)
        if callable(setter):
            setter(float(settings.sfx_volume))
        setter = getattr(audio, "set_music_volume", None)
        if callable(setter):
            setter(float(settings.music_volume))

    cfg = getattr(window, "engine_config", None)
    if cfg is not None:
        try:
            setattr(cfg, "sfx_volume", float(settings.sfx_volume))
        except Exception:
            _log_swallow("SETT-001", "engine/settings.py pass-only blanket swallow")
            pass
        try:
            setattr(cfg, "music_volume", float(settings.music_volume))
        except Exception:
            _log_swallow("SETT-002", "engine/settings.py pass-only blanket swallow")
            pass

    input_controller = getattr(window, "input_controller", None)
    manager = getattr(input_controller, "manager", None) if input_controller is not None else None
    if manager is None:
        return

    get_bindings = getattr(manager, "get_bindings", None)
    unbind = getattr(manager, "unbind", None)
    bind = getattr(manager, "bind", None)
    if not callable(get_bindings) or not callable(unbind) or not callable(bind):
        return

    existing = get_bindings()
    for action, key_code in sorted((settings.keybinds or {}).items()):
        action_name = str(action)
        if not action_name:
            continue
        old_keys = list((existing or {}).get(action_name, []))
        for old_key in old_keys:
            try:
                unbind(action_name, int(old_key))
            except Exception:
                _log_swallow("SETT-004", "engine/settings.py blanket swallow", once=True)
                continue
        try:
            bind(action_name, int(key_code))
        except Exception:
            _log_swallow("SETT-005", "engine/settings.py blanket swallow", once=True)
            continue

    # Keep config bindings in sync (names), but do not auto-save config.json.
    if optional_arcade.arcade is None:
        return
    try:
        from engine.input_bindings import snapshot_bindings

        snapshot = snapshot_bindings(manager, arcade_module=optional_arcade.arcade)
        if cfg is not None:
            setattr(cfg, "input_bindings", snapshot)
    except Exception:
        _log_swallow("SETT-006", "engine/settings.py blanket swallow", once=True)
        return
