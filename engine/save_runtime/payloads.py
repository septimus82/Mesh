from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal, Protocol

from engine.migrations import migrate_payload
from engine.paths import resolve_path
from engine.persistence_io import SAVE_FORMAT_VERSION
from engine.save_runtime import constants
from engine.world_controller import WorldController


def build_snapshot_payload(window: object) -> dict[str, Any]:
    controller = getattr(window, "game_state_controller", None)
    if controller is None:
        return {
            "save_format_version": SAVE_FORMAT_VERSION,
            "version": constants.SNAPSHOT_VERSION,
            "world_file": None,
            "world_id": None,
            "scene_id": None,
            "spawn_zone_id": None,
            "gold": 0,
            "flags": [],
        }
    return build_snapshot_payload_from_controller(controller)


def build_snapshot_payload_from_controller(game_state: object) -> dict[str, Any]:
    window = getattr(game_state, "window", None)
    state = getattr(game_state, "state", None)

    world_file = None
    world_id = None
    scene_id = None

    engine_cfg = getattr(window, "engine_config", None)
    if engine_cfg is not None:
        world_file = getattr(engine_cfg, "world_file", None)

    world_controller = getattr(window, "world_controller", None)
    if world_controller is not None:
        world_id = getattr(world_controller, "id", None)

    scene_controller = getattr(window, "scene_controller", None)
    if scene_controller is not None:
        scene_id = getattr(scene_controller, "current_scene_path", None)

    flags_dict = getattr(state, "flags", {}) if state is not None else {}
    counters = getattr(state, "counters", {}) if state is not None else {}
    variables = getattr(state, "variables", {}) if state is not None else {}

    spawn_zone_raw = None
    if isinstance(variables, dict):
        spawn_zone_raw = variables.get("last_zone_id")
    spawn_zone_id = str(spawn_zone_raw or "").strip() or None

    flags_true = sorted([str(k) for k, v in (flags_dict or {}).items() if bool(v) and str(k).strip()])

    gold_raw = 0
    if isinstance(counters, dict):
        gold_raw = counters.get("gold", 0)
    try:
        gold = int(gold_raw)
    except (TypeError, ValueError):
        gold = 0

    return {
        "save_format_version": SAVE_FORMAT_VERSION,
        "version": constants.SNAPSHOT_VERSION,
        "world_file": str(world_file) if world_file else None,
        "world_id": str(world_id) if world_id else None,
        "scene_id": str(scene_id) if scene_id else None,
        "spawn_zone_id": spawn_zone_id,
        "gold": gold,
        "flags": flags_true,
    }


def load_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"flags": {}, "counters": {"gold": 0}}

    version = payload.get("version")
    if version != constants.SNAPSHOT_VERSION:
        return {"flags": {}, "counters": {"gold": 0}}

    flags_list = payload.get("flags")
    flags: dict[str, bool] = {}
    if isinstance(flags_list, list):
        for item in flags_list:
            name = str(item or "").strip()
            if name:
                flags[name] = True

    gold_raw = payload.get("gold", 0)
    try:
        gold = int(gold_raw)
    except (TypeError, ValueError):
        gold = 0

    return {"flags": dict(sorted(flags.items())), "counters": {"gold": gold}}


def apply_snapshot_to_game_state(game_state: object, payload: dict[str, Any]) -> None:
    state = getattr(game_state, "state", None)
    if state is None:
        return

    update = load_snapshot(payload)
    flags = update.get("flags") or {}
    counters = update.get("counters") or {}

    if isinstance(flags, dict):
        state.flags = dict(flags)
    else:
        state.flags = {}

    gold = 0
    if isinstance(counters, dict):
        try:
            gold = int(counters.get("gold", 0))
        except (TypeError, ValueError):
            gold = 0
    state.counters = {"gold": gold}


def _apply_world_from_snapshot(window: object, world_file: str | None) -> None:
    if not world_file:
        return

    cfg = getattr(window, "engine_config", None)
    if cfg is not None:
        try:
            cfg.world_file = str(world_file)
        except Exception:
            pass

    path = resolve_path(world_file)
    if not path.exists():
        return

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw = migrate_payload("world", raw)
        setattr(window, "world_controller", WorldController(raw))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[Mesh][Snapshot] WARNING: Failed to load world '{world_file}': {exc}\n")


def apply_loaded_payload(
    window: object,
    payload: dict[str, Any],
    *,
    mode: Literal["snapshot", "slot"],
) -> bool:
    if not isinstance(payload, dict):
        return False

    if mode == "snapshot":
        world_file = payload.get("world_file")
        _apply_world_from_snapshot(window, str(world_file) if world_file else None)

        controller = getattr(window, "game_state_controller", None)
        if controller is None:
            return False
        apply_snapshot_to_game_state(controller, payload)

        spawn_zone_id = payload.get("spawn_zone_id")
        setter = getattr(window, "set_next_spawn_point", None)
        if callable(setter) and spawn_zone_id:
            setter(str(spawn_zone_id))
        return True

    state_block = payload.get("game_state") or payload.get("state")
    controller = getattr(window, "game_state_controller", None)
    if state_block and controller is not None:
        if hasattr(controller, "import_state"):
            controller.import_state(state_block)
        else:
            controller.replace_state(state_block)

    spawn_zone_id = payload.get("spawn_zone_id")
    setter = getattr(window, "set_next_spawn_point", None)
    if callable(setter) and spawn_zone_id:
        setter(str(spawn_zone_id))

    if hasattr(window, "ui_controller"):
        window.ui_controller.reset_transient_state()

    return True


def build_slot_payload(
    window: "_WindowWithSceneController",
    slot_name: str,
    *,
    compact: bool,
    timestamp: str,
) -> tuple[dict[str, Any], str]:
    snapshot = window.scene_controller.build_scene_snapshot(compact=compact)
    controller = getattr(window, "game_state_controller", None)
    if controller is not None:
        snapshot["game_state"] = controller.export_state()

    content_to_hash = {
        "data": snapshot,
        "slot": slot_name,
        "scene_path": window.scene_controller.current_scene_path,
    }
    content_str = json.dumps(content_to_hash, sort_keys=True)
    content_hash = __import__("hashlib").md5(content_str.encode("utf-8")).hexdigest()

    snapshot["meta"] = {
        "slot": slot_name,
        "scene_path": window.scene_controller.current_scene_path,
        "timestamp": timestamp,
        "version": constants.SLOT_META_VERSION,
    }
    snapshot["save_format_version"] = SAVE_FORMAT_VERSION

    spawn_zone_id = None
    if controller is not None and hasattr(controller, "get_var"):
        try:
            spawn_zone_id = controller.get_var("last_zone_id", None)
        except Exception:
            spawn_zone_id = None
    cleaned_zone = str(spawn_zone_id or "").strip() or None
    snapshot["spawn_zone_id"] = cleaned_zone

    return snapshot, content_hash


class _WindowWithSceneController(Protocol):
    scene_controller: Any
    game_state_controller: Any
