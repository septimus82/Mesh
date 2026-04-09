# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Callable

from ._shared import _build_entity_index, _sorted_dedup_ids, debug_apply_authored_scene_payload, get_authored_scene_payload

if TYPE_CHECKING:
    from ....scene_controller import SceneController
def debug_config_triggerzone_set_zone_id(controller: "SceneController", selected_ids: list[str], zone_id: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.TriggerZone.zone_id for selected entities that have TriggerZone.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return _debug_config_set_field_for_behaviour(
        controller,
        selected_ids,
        behaviour_name="TriggerZone",
        field_path=("zone_id",),
        value=str(zone_id or "").strip(),
    )


def debug_config_triggerzone_set_radius(
    controller: "SceneController",
    selected_ids: list[str],
    trigger_radius: float,
) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.TriggerZone.trigger_radius for selected entities that have TriggerZone.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return _debug_config_set_field_for_behaviour(
        controller,
        selected_ids,
        behaviour_name="TriggerZone",
        field_path=("trigger_radius",),
        value=float(trigger_radius),
    )


def debug_config_set_game_state_set_toast(
    controller: "SceneController",
    selected_ids: list[str],
    *,
    toast: str,
    toast_seconds: float | None,
) -> tuple[int, int, int]:
    """
    Debug-only: set toast (+ optional toast_seconds) for selected entities with SetGameStateOnEvent.

    - If toast_seconds is None: keep existing toast_seconds if present, else use 3.0.
    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted_toast = str(toast or "").strip()
    if not wanted_toast:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        changed_any = False
        before_toast = cfg.get("toast")
        if before_toast != wanted_toast:
            cfg["toast"] = wanted_toast
            changed_any = True
        if toast_seconds is None:
            existing = cfg.get("toast_seconds")
            if not isinstance(existing, (int, float)) or float(existing) <= 0.0:
                cfg["toast_seconds"] = 3.0
                changed_any = True
        else:
            before_s = cfg.get("toast_seconds")
            if not isinstance(before_s, (int, float)) or float(before_s) != float(toast_seconds):
                cfg["toast_seconds"] = float(toast_seconds)
                changed_any = True
        return changed_any

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_set_game_state_add_require_flag(controller: "SceneController", selected_ids: list[str], flag: str) -> tuple[int, int, int]:
    """
    Debug-only: append a require_flags entry for SetGameStateOnEvent, idempotently.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(flag or "").strip()
    if not wanted:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        req = cfg.get("require_flags")
        if not isinstance(req, list):
            req = []
            cfg["require_flags"] = req
        existing = {str(v).strip() for v in req if isinstance(v, str) and str(v).strip()}
        if wanted in existing:
            return False
        req.append(wanted)
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_set_game_state_add_forbid_flag(controller: "SceneController", selected_ids: list[str], flag: str) -> tuple[int, int, int]:
    """
    Debug-only: append a forbid_flags entry for SetGameStateOnEvent, idempotently.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(flag or "").strip()
    if not wanted:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        forbid = cfg.get("forbid_flags")
        if not isinstance(forbid, list):
            forbid = []
            cfg["forbid_flags"] = forbid
        existing = {str(v).strip() for v in forbid if isinstance(v, str) and str(v).strip()}
        if wanted in existing:
            return False
        forbid.append(wanted)
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_set_game_state_set_flag_true(controller: "SceneController", selected_ids: list[str], flag_key: str) -> tuple[int, int, int]:
    """
    Debug-only: set set_flags[flag_key] = True for SetGameStateOnEvent, without removing other keys.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    key = str(flag_key or "").strip()
    if not key:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        flags = cfg.get("set_flags")
        if not isinstance(flags, dict):
            flags = {}
            cfg["set_flags"] = flags
        before = flags.get(key)
        if before is True:
            return False
        flags[key] = True
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_scene_transition_set_target_scene(controller: "SceneController", selected_ids: list[str], target_scene: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.SceneTransition.target_scene for selected entities that have SceneTransition.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(target_scene or "").strip()
    if not wanted:
        return (0, 0, 0)
    return _debug_config_set_field_for_behaviour(
        controller,
        selected_ids,
        behaviour_name="SceneTransition",
        field_path=("target_scene",),
        value=wanted,
    )


def debug_config_scene_transition_set_spawn_id(controller: "SceneController", selected_ids: list[str], spawn_id: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.SceneTransition.spawn_id (and spawn_point alias) for selected entities.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(spawn_id or "").strip()
    if not wanted:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        changed_any = False
        if cfg.get("spawn_id") != wanted:
            cfg["spawn_id"] = wanted
            changed_any = True
        if cfg.get("spawn_point") != wanted:
            cfg["spawn_point"] = wanted
            changed_any = True
        return changed_any

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SceneTransition", mutate=_mutate)


def _debug_config_entity_has_behaviour(controller: "SceneController", entity_payload: dict[str, Any], behaviour_name: str) -> bool:
    behaviours = entity_payload.get("behaviours")
    if not isinstance(behaviours, list):
        return False
    wanted = str(behaviour_name or "").strip()
    if not wanted:
        return False
    for b in behaviours:
        if isinstance(b, str) and b.strip() == wanted:
            return True
        if isinstance(b, dict):
            bt = b.get("type")
            if isinstance(bt, str) and bt.strip() == wanted:
                return True
    return False


def _debug_config_mutate_for_behaviour(
    controller: "SceneController",
    selected_ids: list[str],
    *,
    behaviour_name: str,
    mutate: "Callable[[dict[str, Any]], bool]",
) -> tuple[int, int, int]:
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    if not isinstance(selected_ids, list) or not selected_ids:
        return (0, 0, 0)
    wanted_behaviour = str(behaviour_name or "").strip()
    if not wanted_behaviour:
        return (0, 0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0, 0)

    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    skipped_no_behaviour = 0

    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        if not _debug_config_entity_has_behaviour(controller, ent, wanted_behaviour):
            skipped_no_behaviour += 1
            continue
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(wanted_behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[wanted_behaviour] = cfg
        try:
            did = bool(mutate(cfg))
        except Exception:  # noqa: BLE001  # REASON: per-entity debug config mutation failures should skip only that entity update
            did = False
        if did:
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player, skipped_no_behaviour)


def _debug_config_set_field_for_behaviour(
    controller: "SceneController",
    selected_ids: list[str],
    *,
    behaviour_name: str,
    field_path: tuple[str, ...],
    value: Any,
) -> tuple[int, int, int]:
    wanted_path = tuple(str(p).strip() for p in (field_path or ()) if str(p).strip())
    if not wanted_path:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        key = wanted_path[0]
        before = cfg.get(key)
        if before == value:
            return False
        cfg[key] = value
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name=behaviour_name, mutate=_mutate)
