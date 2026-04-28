from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from .diagnostics import add_exception as diag_add_exception
from .diagnostics import error as diag_error
from .diagnostics import info as diag_info
from .diagnostics import warn as diag_warn
from .persistence_io import SAVE_FORMAT_VERSION
from .persistence_io import read_json, write_json_atomic
from .save_runtime import constants as save_constants
from .save_runtime import io as save_io
from .save_runtime import payloads as save_payloads
from .save_runtime.restore_policy import SNAPSHOT_POLICY
from .save_runtime.save_diagnostics import SaveDiagnosticsAggregator
from .save_runtime.ux_codes import (
    LOAD_APPLY_FAILED,
    LOAD_FALLBACK_TO_START_SCENE,
    LOAD_NOT_FOUND,
    LOAD_PARSE_FAILED,
    LOAD_SCHEMA_INVALID,
    SAVE_IO_PERMISSION,
    SAVE_SERIALIZE_FAILED,
    SAVE_WRITE_FAILED,
)
from engine.swallowed_exceptions import _log_swallow

_DIAG_SOURCE = "engine.savegame"
_SLOT_RE = re.compile(r"(\d+)")

def _classify_save_exception(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, PermissionError):
        return SAVE_IO_PERMISSION, "Check write permissions for the target save location."
    if isinstance(exc, (TypeError, ValueError)):
        return SAVE_SERIALIZE_FAILED, "The save payload is invalid and could not be serialized."
    return SAVE_WRITE_FAILED, "Retry after checking disk space and permissions."


def _slot_index_from_path(path: str | Path | None) -> int | None:
    raw = str(path or "").strip()
    if not raw:
        return None
    stem = Path(raw).stem
    match = _SLOT_RE.search(stem)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _diag_context(
    *,
    operation: str,
    save_path: str | Path | None,
    pointer: str = "$",
    slot: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(save_path, Path):
        normalized_path = save_path.as_posix()
    else:
        normalized_path = str(save_path or "").replace("\\", "/")
    context: dict[str, Any] = {
        "operation": str(operation),
        "pointer": str(pointer),
        "save_path": normalized_path,
    }
    slot_value = _slot_index_from_path(save_path) if slot is None else slot
    if slot_value is not None:
        context["slot"] = int(slot_value)
    if extra:
        for key in sorted(extra.keys()):
            context[str(key)] = extra[key]
    return context


def _fallback_to_start_scene(
    window: Any,
    *,
    reason_code: str,
    failed_path: str,
    slot: int | None = None,
) -> None:
    cfg = getattr(window, "engine_config", None)
    target_scene = str(getattr(cfg, "start_scene", "") or "").strip()
    requester = getattr(window, "request_scene_change", None)
    if not target_scene or not callable(requester):
        return
    try:
        requester(target_scene)
        diag_info(
            LOAD_FALLBACK_TO_START_SCENE,
            "Load failed. Falling back to start scene.",
            _DIAG_SOURCE,
            location=target_scene,
            context=_diag_context(
                operation="load",
                save_path=failed_path,
                pointer="$",
                slot=slot,
                extra={
                    "reason_code": str(reason_code or ""),
                    "target_scene": target_scene,
                },
            ),
            hint="Try a different slot or delete the corrupt save.",
        )
    except Exception as exc:  # noqa: BLE001  # REASON: savegame resilience fallback
        _log_swallow("SAVE-003", "load_fallback_start_scene diag", once=True)
        diag_add_exception(
            LOAD_FALLBACK_TO_START_SCENE,
            exc,
            _DIAG_SOURCE,
            location=target_scene,
            context=_diag_context(
                operation="load",
                save_path=failed_path,
                pointer="$",
                slot=slot,
                extra={"target_scene": target_scene},
            ),
            severity="warning",
            hint="Try selecting Start Game manually.",
        )

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
        except Exception:  # noqa: BLE001  # REASON: savegame resilience fallback
            player_sprite = None
    if player_sprite is None:
        player_sprite = getattr(window, "player_sprite", None)

    if player_sprite is not None:
        try:
            player_x = float(getattr(player_sprite, "center_x", 0.0))
            player_y = float(getattr(player_sprite, "center_y", 0.0))
        except Exception:  # noqa: BLE001  # REASON: savegame resilience fallback
            _log_swallow("SAVE-005", "player position parse", once=True)
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
        except Exception:  # noqa: BLE001  # REASON: savegame resilience fallback
            _log_swallow("SAVE-006", "quests to_dict", once=True)
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
    try:
        write_json_atomic(out_path, save.to_payload(), indent=2, sort_keys=True, trailing_newline=True)
    except Exception as exc:  # noqa: BLE001  # REASON: savegame resilience fallback
        code, hint = _classify_save_exception(exc)
        diag_add_exception(
            code,
            exc,
            _DIAG_SOURCE,
            location=out_path.as_posix(),
            context=_diag_context(
                operation="save",
                save_path=out_path,
                pointer="$",
            ),
            severity="error",
            hint=hint,
        )
        raise


def load_savegame(path: str | Path | None) -> SaveGameV1 | None:
    if _is_web_runtime():
        return None
    in_path = Path(path) if path is not None else resolve_savegame_path()
    if not in_path.exists():
        diag_warn(
            LOAD_NOT_FOUND,
            "Save file not found.",
            _DIAG_SOURCE,
            location=in_path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=in_path,
                pointer="$",
            ),
            hint="Start a new game and create a save before using Continue.",
        )
        return None
    try:
        raw = read_json(in_path)
    except Exception as exc:  # noqa: BLE001  # REASON: savegame resilience fallback
        _log_swallow("SAVE-007", "read_json parse", once=True)
        diag_add_exception(
            LOAD_PARSE_FAILED,
            exc,
            _DIAG_SOURCE,
            location=in_path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=in_path,
                pointer="$",
            ),
            severity="error",
            hint="The save file is not valid JSON. Restore from backup or create a new save.",
        )
        return None
    if not isinstance(raw, dict):
        diag_error(
            LOAD_PARSE_FAILED,
            "Save payload root must be a JSON object.",
            _DIAG_SOURCE,
            location=in_path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=in_path,
                pointer="$",
            ),
            hint="Replace the save with a valid save file.",
        )
        return None
    parsed = SaveGameV1.from_payload(raw)
    if parsed is None:
        diag_error(
            LOAD_SCHEMA_INVALID,
            "Save payload schema is invalid or unsupported.",
            _DIAG_SOURCE,
            location=in_path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=in_path,
                pointer="$/version",
            ),
            hint="Create a new save with this game version.",
        )
        return None
    return parsed


def apply_savegame_to_window(window: Any, save: SaveGameV1) -> None:
    gs = getattr(window, "game_state_controller", None)
    state = getattr(gs, "state", None) if gs is not None else None
    if state is not None and hasattr(state, "flags"):
        try:
            state.flags = dict(save.flags)
        except Exception as exc:  # noqa: BLE001  # REASON: savegame resilience fallback
            _log_swallow("SAVE-001", "engine/savegame.py pass-only blanket swallow")
            diag_add_exception(
                LOAD_APPLY_FAILED,
                exc,
                _DIAG_SOURCE,
                location=str(save.scene_path or ""),
                context=_diag_context(
                    operation="load",
                    save_path=str(save.scene_path or ""),
                    pointer="$/flags",
                ),
                severity="warning",
                hint="Start a new game if this save cannot be applied cleanly.",
            )
            pass

    manager = _resolve_quest_manager(window)
    if manager is not None and callable(getattr(manager, "load_from_dict", None)):
        if isinstance(save.quests, dict):
            try:
                manager.load_from_dict(save.quests)
            except Exception as exc:  # noqa: BLE001  # REASON: savegame resilience fallback
                _log_swallow("SAVE-002", "engine/savegame.py pass-only blanket swallow")
                diag_add_exception(
                    LOAD_APPLY_FAILED,
                    exc,
                    _DIAG_SOURCE,
                    location=str(save.scene_path or ""),
                    context=_diag_context(
                        operation="load",
                        save_path=str(save.scene_path or ""),
                        pointer="$/quests",
                    ),
                    severity="warning",
                    hint="Start a new game if this save cannot be applied cleanly.",
                )
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
    except Exception:  # noqa: BLE001  # REASON: savegame resilience fallback
        _log_swallow("SAVE-008", "player_sprite find for teleport", once=True)
        return False
    if player_sprite is None:
        return False

    # Cast needed: finder callable returns untyped object
    # Type is optional_arcade.arcade.Sprite at runtime but using Any to avoid import
    sprite = cast(Any, player_sprite)
    try:
        sprite.center_x = float(x)
        sprite.center_y = float(y)
    except Exception:  # noqa: BLE001  # REASON: savegame resilience fallback
        _log_swallow("SAVE-009", "player_sprite position set", once=True)
        return False

    entity_data = getattr(sprite, "mesh_entity_data", None)
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
        diag_error(
            LOAD_SCHEMA_INVALID,
            "Cannot apply savegame payload because schema validation failed.",
            _DIAG_SOURCE,
            context=_diag_context(
                operation="load",
                save_path="<memory>",
                pointer="$",
            ),
            hint="Start a new game and create a fresh save file.",
        )
        _fallback_to_start_scene(
            window,
            reason_code=LOAD_SCHEMA_INVALID,
            failed_path="<memory>",
        )
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
        return cast(dict[str, Any], payload_or_error)
    msg = str(payload_or_error or "")
    code = LOAD_NOT_FOUND if not path.exists() else LOAD_PARSE_FAILED
    if path.exists():
        snapshot = save_io.get_save_runtime_diagnostics_snapshot()
        attempt = snapshot.get("last_load_attempt", {})
        if isinstance(attempt, dict):
            diagnostics = attempt.get("diagnostics", {})
            if isinstance(diagnostics, dict):
                rows = diagnostics.get("diagnostics", [])
                if isinstance(rows, list):
                    codes = [str(item.get("code", "") or "").strip().lower() for item in rows if isinstance(item, dict)]
                    if any(row_code == "save.load.schema_validation_error" for row_code in codes):
                        code = LOAD_SCHEMA_INVALID
                    elif any(row_code == "save.load.schema_migration_error" for row_code in codes):
                        code = LOAD_SCHEMA_INVALID
                    elif any(row_code == "save.load.read_error" for row_code in codes):
                        code = LOAD_PARSE_FAILED
    hint = (
        "Start a new game and create a new snapshot."
        if code == LOAD_NOT_FOUND
        else "Snapshot data is invalid. Create a fresh snapshot in this game version."
    )
    if code == LOAD_NOT_FOUND:
        diag_warn(
            code,
            "Snapshot file not found.",
            _DIAG_SOURCE,
            location=path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=path,
                pointer="$",
            ),
            hint=hint,
        )
    else:
        diag_error(
            code,
            "Snapshot load failed.",
            _DIAG_SOURCE,
            location=path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=path,
                pointer="$",
                extra={"error": msg},
            ),
            hint=hint,
        )
    if msg:
        sys.stderr.write(msg + "\n")
    return None


def save_quick_snapshot(window: object, path: Path = QUICK_SNAPSHOT_PATH) -> bool:
    controller = getattr(window, "game_state_controller", None)
    if controller is None:
        diag_error(
            SAVE_WRITE_FAILED,
            "Quick snapshot failed because game_state_controller is missing.",
            _DIAG_SOURCE,
            location=path.as_posix(),
            context=_diag_context(
                operation="save",
                save_path=path,
                pointer="$",
            ),
            hint="Retry after loading into gameplay.",
        )
        return False

    payload = dump_snapshot(controller)
    try:
        write_snapshot_file(path, payload)
        sys.stderr.write(f"[Mesh][Snapshot] Saved quick snapshot to '{path}'\n")
        return True
    except Exception as exc:  # noqa: BLE001  # REASON: savegame resilience fallback
        code, hint = _classify_save_exception(exc)
        diag_add_exception(
            code,
            exc,
            _DIAG_SOURCE,
            location=path.as_posix(),
            context=_diag_context(
                operation="save",
                save_path=path,
                pointer="$",
            ),
            severity="error",
            hint=hint,
        )
        sys.stderr.write(f"[Mesh][Snapshot] ERROR: Failed to save snapshot: {exc}\n")
        return False


def load_quick_snapshot(window: object, path: Path = QUICK_SNAPSHOT_PATH) -> bool:
    payload = read_snapshot_file(path)
    if payload is None:
        _fallback_to_start_scene(
            window,
            reason_code=LOAD_PARSE_FAILED,
            failed_path=path.as_posix(),
        )
        return False

    controller = getattr(window, "game_state_controller", None)
    if controller is None:
        diag_error(
            LOAD_APPLY_FAILED,
            "Quick snapshot load failed because game_state_controller is missing.",
            _DIAG_SOURCE,
            location=path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=path,
                pointer="$",
            ),
            hint="Retry after entering gameplay.",
        )
        _fallback_to_start_scene(window, reason_code=LOAD_APPLY_FAILED, failed_path=path.as_posix())
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
        primary = apply_diags.primary()
        pointer = "$"
        inner_code = ""
        if primary is not None:
            context = primary.context if isinstance(primary.context, dict) else {}
            pointer = str(context.get("pointer", "$") or "$")
            inner_code = str(primary.code or "")
        diag_error(
            LOAD_APPLY_FAILED,
            "Quick snapshot apply failed.",
            _DIAG_SOURCE,
            location=path.as_posix(),
            context=_diag_context(
                operation="load",
                save_path=path,
                pointer=pointer,
                extra={"apply_code": inner_code},
            ),
            hint="Start a new game and create a fresh snapshot.",
        )
        sys.stderr.write(save_io.format_load_error("[Mesh][Snapshot]", apply_diags) + "\n")
        _fallback_to_start_scene(window, reason_code=LOAD_APPLY_FAILED, failed_path=path.as_posix())
        return False

    # Request scene change last.
    requester = getattr(window, "request_scene_change", None)
    if callable(requester) and scene_id:
        requester(str(scene_id))

    return True
