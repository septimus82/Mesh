from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .persistence_io import SAVE_FORMAT_VERSION
from .persistence_io import read_json, write_json_atomic
from .save_runtime import constants as save_constants
from .save_runtime import io as save_io
from .save_runtime import payloads as save_payloads
from .save_runtime.restore_policy import SNAPSHOT_POLICY
from .save_runtime.save_diagnostics import SaveDiagnosticsAggregator

SNAPSHOT_VERSION = save_constants.SNAPSHOT_VERSION
QUICK_SNAPSHOT_PATH = save_constants.QUICK_SNAPSHOT_PATH

SAVEGAME_V1_VERSION = 1
DEFAULT_SAVEGAME_PATH = Path("saves") / "save_1.json"


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


@dataclass(frozen=True, slots=True)
class SaveGameV1:
    scene_path: str
    player_x: float
    player_y: float
    flags: dict[str, bool]
    quests: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        quests: dict[str, Any] = {}
        if isinstance(self.quests, dict):
            for key, value in self.quests.items():
                label = str(key or "").strip()
                if not label:
                    continue
                quests[label] = value
        return {
            "save_format_version": SAVE_FORMAT_VERSION,
            "version": SAVEGAME_V1_VERSION,
            "scene_path": str(self.scene_path),
            "scene_id": str(self.scene_path),
            "player_x": float(self.player_x),
            "player_y": float(self.player_y),
            "player": {"x": float(self.player_x), "y": float(self.player_y)},
            "flags": {str(k): bool(v) for k, v in sorted(self.flags.items(), key=lambda kv: str(kv[0]))},
            "quests": quests,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SaveGameV1 | None":
        if not isinstance(payload, dict):
            return None

        try:
            version = int(payload.get("version", 0))
        except (TypeError, ValueError):
            version = 0
        if version != SAVEGAME_V1_VERSION:
            return None

        scene_path = str(payload.get("scene_path") or payload.get("scene_id") or "").strip()
        if not scene_path:
            return None

        player_x = None
        player_y = None
        player = payload.get("player")
        if isinstance(player, dict):
            try:
                player_x = float(player.get("x", 0.0))
                player_y = float(player.get("y", 0.0))
            except (TypeError, ValueError):
                player_x = None
                player_y = None
        if player_x is None or player_y is None:
            try:
                player_x = float(payload.get("player_x", 0.0))
                player_y = float(payload.get("player_y", 0.0))
            except (TypeError, ValueError):
                return None

        flags_raw = payload.get("flags", {})
        flags: dict[str, bool] = {}
        if isinstance(flags_raw, dict):
            for k, v in flags_raw.items():
                key = str(k or "").strip()
                if not key:
                    continue
                flags[key] = bool(v)

        quests_raw = payload.get("quests", {})
        quests: dict[str, Any] = {}
        if isinstance(quests_raw, dict):
            for key, value in quests_raw.items():
                label = str(key or "").strip()
                if not label:
                    continue
                quests[label] = value

        return cls(
            scene_path=scene_path,
            player_x=player_x,
            player_y=player_y,
            flags=flags,
            quests=quests,
        )


def resolve_savegame_path(path: str | None = None) -> Path:
    raw = str(path or "").strip()
    if not raw:
        raw = str(os.environ.get("MESH_SAVEGAME_PATH") or os.environ.get("MESH_SAVE_PATH") or "").strip()
    if not raw:
        return DEFAULT_SAVEGAME_PATH
    return Path(raw)


def _resolve_quest_manager(window: Any) -> Any | None:
    manager = getattr(window, "quest_manager", None)
    if manager is not None and callable(getattr(manager, "to_dict", None)):
        return manager
    controller = getattr(window, "game_state_controller", None)
    manager = getattr(controller, "quests", None) if controller is not None else None
    if manager is not None and callable(getattr(manager, "to_dict", None)):
        return manager
    return None


def capture_savegame_from_window(window: Any) -> SaveGameV1 | None:
    scene = getattr(window, "scene_controller", None)
    scene_path = getattr(scene, "current_scene_path", None)
    scene_path = str(scene_path or "").strip()
    if not scene_path:
        return None

    player_x = 0.0
    player_y = 0.0
    player_sprite = None
    finder = getattr(scene, "_find_player_sprite", None) if scene is not None else None
    if callable(finder):
        try:
            player_sprite = finder()
        except Exception:  # noqa: BLE001
            player_sprite = None
    if player_sprite is None:
        player_sprite = getattr(window, "player_sprite", None)

    if player_sprite is not None:
        try:
            player_x = float(getattr(player_sprite, "center_x", 0.0))
            player_y = float(getattr(player_sprite, "center_y", 0.0))
        except Exception:  # noqa: BLE001
            player_x = 0.0
            player_y = 0.0

    gs = getattr(window, "game_state_controller", None)
    state = getattr(gs, "state", None) if gs is not None else None
    flags_raw = getattr(state, "flags", {}) if state is not None else {}
    flags: dict[str, bool] = {}
    if isinstance(flags_raw, dict):
        for k, v in flags_raw.items():
            key = str(k or "").strip()
            if not key:
                continue
            flags[key] = bool(v)

    quests: dict[str, Any] = {}
    manager = _resolve_quest_manager(window)
    if manager is not None and callable(getattr(manager, "to_dict", None)):
        try:
            payload = manager.to_dict()
            if isinstance(payload, dict):
                quests = payload
        except Exception:  # noqa: BLE001
            quests = {}

    return SaveGameV1(
        scene_path=scene_path,
        player_x=player_x,
        player_y=player_y,
        flags=flags,
        quests=quests,
    )


def save_savegame(path: str | Path | None, save: SaveGameV1) -> None:
    if _is_web_runtime():
        return
    out_path = Path(path) if path is not None else resolve_savegame_path()
    write_json_atomic(out_path, save.to_payload(), indent=2, sort_keys=True, trailing_newline=True)


def load_savegame(path: str | Path | None) -> SaveGameV1 | None:
    if _is_web_runtime():
        return None
    in_path = Path(path) if path is not None else resolve_savegame_path()
    if not in_path.exists():
        return None
    try:
        raw = read_json(in_path)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict):
        return None
    return SaveGameV1.from_payload(raw)


def apply_savegame_to_window(window: Any, save: SaveGameV1) -> None:
    gs = getattr(window, "game_state_controller", None)
    state = getattr(gs, "state", None) if gs is not None else None
    if state is not None and hasattr(state, "flags"):
        try:
            state.flags = dict(save.flags)
        except Exception:  # noqa: BLE001
            pass

    manager = _resolve_quest_manager(window)
    if manager is not None and callable(getattr(manager, "load_from_dict", None)):
        if isinstance(save.quests, dict):
            try:
                manager.load_from_dict(save.quests)
            except Exception:  # noqa: BLE001
                pass

    # Teleport after scene load (SceneController will consume this if wired).
    setattr(window, "_mesh_pending_savegame_scene_path", str(save.scene_path))
    setattr(window, "_mesh_pending_savegame_player_pos", (float(save.player_x), float(save.player_y)))

    # If already in the desired scene, apply immediately as well.
    scene = getattr(window, "scene_controller", None)
    current_scene = getattr(scene, "current_scene_path", None)
    if str(current_scene or "").strip() == str(save.scene_path):
        _apply_pending_savegame_player_pos(window)

    requester = getattr(window, "request_scene_change", None)
    if callable(requester):
        requester(str(save.scene_path))


def _apply_pending_savegame_player_pos(window: Any) -> bool:
    pos = getattr(window, "_mesh_pending_savegame_player_pos", None)
    if not isinstance(pos, (tuple, list)) or len(pos) != 2:
        return False

    try:
        x = float(pos[0])
        y = float(pos[1])
    except (TypeError, ValueError):
        return False

    scene = getattr(window, "scene_controller", None)
    finder = getattr(scene, "_find_player_sprite", None) if scene is not None else None
    if not callable(finder):
        return False
    try:
        player_sprite = finder()
    except Exception:  # noqa: BLE001
        return False
    if player_sprite is None:
        return False

    try:
        player_sprite.center_x = float(x)
        player_sprite.center_y = float(y)
    except Exception:  # noqa: BLE001
        return False

    entity_data = getattr(player_sprite, "mesh_entity_data", None)
    if isinstance(entity_data, dict):
        entity_data["x"] = float(x)
        entity_data["y"] = float(y)

    setattr(window, "_mesh_pending_savegame_player_pos", None)
    setattr(window, "_mesh_pending_savegame_scene_path", None)
    return True


def build_savegame(window: Any) -> dict[str, Any] | None:
    save = capture_savegame_from_window(window)
    if save is None:
        return None
    return save.to_payload()


def apply_savegame(window: Any, payload: dict[str, Any]) -> bool:
    save = SaveGameV1.from_payload(payload)
    if save is None:
        return False
    apply_savegame_to_window(window, save)
    return True


def dump_snapshot(game_state: object) -> dict[str, Any]:
    """Return a minimal deterministic snapshot for resuming a run.

    The expected input is a GameStateController-like object with a `.window` and `.state`.
    """
    payload = save_payloads.build_snapshot_payload_from_controller(game_state)
    payload["save_format_version"] = SAVE_FORMAT_VERSION
    payload["version"] = SNAPSHOT_VERSION
    return payload


def load_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize snapshot payload into a minimal game-state update.

    Returns a dict compatible with a subset of GameState.restore():
    {"flags": {...}, "counters": {"gold": ...}}
    """
    return save_payloads.load_snapshot(payload)


def apply_snapshot_to_game_state(game_state: object, payload: dict[str, Any]) -> None:
    """Apply a minimal snapshot update onto a GameStateController-like object."""
    save_payloads.apply_snapshot_to_game_state(game_state, payload)


def _json_dumps_deterministic(payload: dict[str, Any]) -> str:
    # Backwards-compatible wrapper for older callers/tests.
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_snapshot_file(path: Path, payload: dict[str, Any]) -> None:
    """Write snapshot atomically (temp + replace)."""
    save_io.write_snapshot_atomic(path, payload)


def read_snapshot_file(path: Path) -> dict[str, Any] | None:
    ok, payload_or_error = save_io.load_snapshot_payload(path, policy=SNAPSHOT_POLICY)
    if ok:
        return payload_or_error  # type: ignore[return-value]
    msg = str(payload_or_error or "")
    if msg:
        sys.stderr.write(msg + "\n")
    return None


def save_quick_snapshot(window: object, path: Path = QUICK_SNAPSHOT_PATH) -> bool:
    controller = getattr(window, "game_state_controller", None)
    if controller is None:
        return False

    payload = dump_snapshot(controller)
    try:
        write_snapshot_file(path, payload)
        sys.stderr.write(f"[Mesh][Snapshot] Saved quick snapshot to '{path}'\n")
        return True
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[Mesh][Snapshot] ERROR: Failed to save snapshot: {exc}\n")
        return False


def load_quick_snapshot(window: object, path: Path = QUICK_SNAPSHOT_PATH) -> bool:
    payload = read_snapshot_file(path)
    if payload is None:
        return False

    controller = getattr(window, "game_state_controller", None)
    if controller is None:
        return False

    scene_id = payload.get("scene_id")
    apply_diags = SaveDiagnosticsAggregator()
    applied = save_payloads.apply_loaded_payload(
        window,
        payload,
        mode="snapshot",
        policy=SNAPSHOT_POLICY,
        diagnostics=apply_diags,
        source=path.as_posix(),
    )
    save_io.record_load_attempt(
        kind="snapshot_apply",
        path=path,
        ok=bool(applied),
        aggregator=apply_diags,
    )
    counts = apply_diags.counts()
    should_write_sidecars = (
        SNAPSHOT_POLICY.write_sidecars_on_failure and (
            (not applied) or int(counts.get("warnings", 0)) > 0 or int(counts.get("errors", 0)) > 0
        )
    )
    if should_write_sidecars:
        save_io.write_diagnostics_sidecars(path, apply_diags)
    if not applied:
        sys.stderr.write(save_io.format_load_error("[Mesh][Snapshot]", apply_diags) + "\n")
        return False

    # Request scene change last.
    requester = getattr(window, "request_scene_change", None)
    if callable(requester) and scene_id:
        requester(str(scene_id))

    return True
