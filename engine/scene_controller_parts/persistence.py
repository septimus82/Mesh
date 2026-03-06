# mypy: ignore-errors
from __future__ import annotations

from typing import Any

from engine import scene_controller_save_load as _save_load_proxy
from engine.scene_runtime.persistence import restore_camera_state as _restore_camera_state_runtime
from engine.scene_runtime.persistence import restore_player_state as _restore_player_state_runtime
from engine.scene_runtime.persistence import snapshot_camera_state as _snapshot_camera_state_runtime
from engine.scene_runtime.persistence import snapshot_player_state as _snapshot_player_state_runtime


def _snapshot_player_state(self) -> dict[str, Any] | None:
    return _save_load_proxy.snapshot_player_state(self, snapshot_player_state_runtime=_snapshot_player_state_runtime)


def _restore_player_state(self, snapshot: dict[str, Any] | None) -> None:
    _save_load_proxy.restore_player_state(self, snapshot, restore_player_state_runtime=_restore_player_state_runtime)


def _snapshot_camera_state(self) -> dict[str, Any] | None:
    return _save_load_proxy.snapshot_camera_state(self, snapshot_camera_state_runtime=_snapshot_camera_state_runtime)


def _restore_camera_state(self, snapshot: dict[str, Any] | None) -> None:
    _save_load_proxy.restore_camera_state(self, snapshot, restore_camera_state_runtime=_restore_camera_state_runtime)

def bind_persistence_methods(cls) -> None:
    cls._snapshot_player_state = _snapshot_player_state
    cls._restore_player_state = _restore_player_state
    cls._snapshot_camera_state = _snapshot_camera_state
    cls._restore_camera_state = _restore_camera_state
