# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

import copy
import re
import sys
from typing import TYPE_CHECKING, Any, Callable, Dict

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from ....background_layers import parse_background_layers
from ...index_build import build_scene_index_from_sprites
from .. import entity_ops_geometry as _geometry_helpers

if TYPE_CHECKING:
    from ....scene_controller import SceneController

def _sorted_dedup_ids(raw_ids: list[str] | None) -> list[str]:
    """Return sorted, deduplicated, stripped, non-empty entity IDs."""
    return sorted(
        {str(i).strip() for i in (raw_ids or []) if isinstance(i, str) and str(i).strip()}
    )


def _build_entity_index(entities: list[Dict[str, Any]]) -> dict[str, Dict[str, Any]]:
    """Build an ``{id: entity_dict}`` index in O(N) for fast lookup."""
    idx: dict[str, Dict[str, Any]] = {}
    for ent in entities:
        if isinstance(ent, dict):
            eid = ent.get("id")
            if isinstance(eid, str) and eid.strip():
                idx[eid.strip()] = ent
    return idx


def _collect_participants(
    sorted_ids: list[str],
    index: dict[str, Dict[str, Any]],
    is_player_entity: Callable[[dict[str, Any]], bool],
    *,
    require_position: bool = False,
    skip_group_entity: bool = False,
) -> tuple[list[tuple[str, dict]], int]:
    """Gather participant entities from *sorted_ids* using an index.

    Returns ``(participants, skipped_count)``.  *participants* is a list of
    ``(id, entity_dict)`` pairs in the same order as *sorted_ids*.
    """
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if require_position and ("x" not in ent or "y" not in ent):
            skipped += 1
            continue
        if skip_group_entity and _is_group_entity(ent):
            skipped += 1
            continue
        participants.append((eid, ent))
    return participants, skipped


def _build_used_id_set(entities: list[Dict[str, Any]]) -> set[str]:
    """Collect all entity IDs currently in the scene for collision avoidance."""
    used: set[str] = set()
    for ent in entities:
        if isinstance(ent, dict):
            eid = ent.get("id")
            if isinstance(eid, str) and eid.strip():
                used.add(eid.strip())
    return used


def _next_unique_dup_id(orig_id: str, used_ids: set[str]) -> str:
    """Allocate the next ``{orig_id}__dup{k}`` that isn't in *used_ids*, and add it."""
    k = 1
    while True:
        candidate = f"{orig_id}__dup{k}"
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate
        k += 1


def get_authored_scene_payload(controller: "SceneController") -> Dict[str, Any]:
    """Return a copy of the scene payload before runtime-only mutations (e.g., themed spawn resolution)."""
    payload = getattr(controller, "_loaded_scene_source_data", None)
    if isinstance(payload, dict):
        return payload
    public_mod = sys.modules.get("engine.scene_runtime.authoring.entity_ops")
    if public_mod is not None:
        hook = getattr(public_mod, "get_authored_scene_payload", None)
        if callable(hook) and hook is not get_authored_scene_payload:
            try:
                value = hook(controller)
            except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
                _log_swallow("EOPS-001", "get_authored_scene_payload hook call", once=True)
                value = None
            if isinstance(value, dict):
                return value
    getter = getattr(controller, "get_authored_scene_payload", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
            _log_swallow("EOPS-002", "get_authored_scene_payload getter call", once=True)
            value = None
        if isinstance(value, dict):
            return value
    return {}


def debug_apply_authored_scene_payload(controller: "SceneController", authored_payload: Dict[str, Any]) -> bool:
    """
    Debug-only: replace the current authored scene payload in-memory (no disk I/O),
    rebuild runtime scene data, and refresh tile/entity visuals deterministically.
    """
    if not isinstance(authored_payload, dict):
        return False
    if not hasattr(controller, "_loaded_scene_source_data"):
        public_mod = sys.modules.get("engine.scene_runtime.authoring.entity_ops")
        if public_mod is not None:
            hook = getattr(public_mod, "debug_apply_authored_scene_payload", None)
            if callable(hook) and hook is not debug_apply_authored_scene_payload:
                try:
                    return bool(hook(controller, authored_payload))
                except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
                    _log_swallow("EOPS-003", "debug_apply_authored_scene_payload hook call", once=True)
                    return False
        debug_apply = getattr(controller, "debug_apply_authored_scene_payload", None)
        if callable(debug_apply):
            try:
                return bool(debug_apply(authored_payload))
            except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
                _log_swallow("EOPS-004", "debug_apply_authored_scene_payload debug_apply call", once=True)
                return False
        apply_payload = getattr(controller, "apply_authored_scene_payload", None)
        if callable(apply_payload):
            try:
                result = apply_payload(authored_payload)
            except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
                _log_swallow("EOPS-005", "debug_apply_authored_scene_payload apply_payload call", once=True)
                return False
            return True if result is None else bool(result)
        return False

    scene_path = str(controller.current_scene_path or "").strip()
    if not scene_path:
        return False

    controller._loaded_scene_source_data = copy.deepcopy(authored_payload)
    runtime_scene: Dict[str, Any] = copy.deepcopy(authored_payload)
    controller._background_layers = parse_background_layers(runtime_scene)
    controller._apply_theme_runtime(runtime_scene)
    controller._loaded_scene_data = runtime_scene
    controller.scene_settings = runtime_scene.get("settings", {}) if isinstance(runtime_scene.get("settings"), dict) else {}

    controller._scene_index = None

    window = getattr(controller, "window", None)
    if window is None or getattr(window, "assets", None) is None or getattr(window, "scene_loader", None) is None:
        return True

    controller._clear_scene_event_subscriptions()
    controller._ensure_layers(runtime_scene.get("layers", []))

    for sprite_list in controller.layers.values():
        sprite_list.clear()
    try:
        controller.solid_sprites.clear()
    except RuntimeError:
        _log_swallow("EOPS-006", "solid_sprites clear RuntimeError", once=True)
        controller.solid_sprites = optional_arcade.arcade.SpriteList()

    try:
        controller.refresh_tilemap_layers()
    except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
        from engine.logging_tools import get_logger; get_logger(__name__).debug("SWALLOW[%s] %s", "ENTI-001", "engine/scene_runtime/authoring/entity_ops_impl.py pass-only blanket swallow", exc_info=True)
        pass

    prev_suppress = bool(getattr(controller, "_suppress_spawn_toasts", False))
    controller._suppress_spawn_toasts = True
    try:
        from ....scene_entity_gating import filter_entities_by_flags  # noqa: PLC0415

        getter = getattr(window, "get_flag", None)
        entities_payload = filter_entities_by_flags(
            runtime_scene.get("entities", []),
            get_flag=getter if callable(getter) else None,
        )
        for entity in entities_payload:
            if not isinstance(entity, dict):
                continue
            sprite = controller._create_sprite(entity)
            if not sprite:
                continue
            layer_name = entity.get("layer", "entities")
            if layer_name not in controller.layers:
                controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
            layer = controller.layers[layer_name]
            layer.append(sprite)
            is_solid = bool(entity.get("solid", False))
            sprite.mesh_is_solid = is_solid
            if is_solid:
                controller.solid_sprites.append(sprite)
    finally:
        controller._suppress_spawn_toasts = prev_suppress

    controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return True


def debug_find_sprite_by_entity_id(controller: "SceneController", entity_id: str) -> optional_arcade.arcade.Sprite | None:
    idx = controller._ensure_scene_index()
    sprite = idx.get_by_id(entity_id)
    return sprite if isinstance(sprite, optional_arcade.arcade.Sprite) else None


def _debug_iter_authoring_payloads(controller: "SceneController") -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    loaded_scene = getattr(controller, "_loaded_scene_data", None)
    if isinstance(loaded_scene, dict):
        out.append(loaded_scene)
    authored_scene = getattr(controller, "_loaded_scene_source_data", None)
    if isinstance(authored_scene, dict):
        out.append(authored_scene)
    if not out:
        getter = getattr(controller, "get_authored_scene_payload", None)
        if callable(getter):
            try:
                payload = getter()
            except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
                _log_swallow("EOPS-007", "_debug_iter_authoring_payloads getter call", once=True)
                payload = None
            if isinstance(payload, dict):
                out.append(payload)
    return out


def _debug_remove_sprite(controller: "SceneController", sprite: optional_arcade.arcade.Sprite) -> None:
    for layer in controller.layers.values():
        try:
            if sprite in layer:
                layer.remove(sprite)
        except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
            _log_swallow("EOPS-008", "_debug_remove_sprite layer remove", once=True)
            continue
    try:
        if sprite in controller.solid_sprites:
            controller.solid_sprites.remove(sprite)
    except Exception:  # noqa: BLE001  # REASON: shared fallback isolation
        from engine.logging_tools import get_logger; get_logger(__name__).debug("SWALLOW[%s] %s", "ENTI-002", "engine/scene_runtime/authoring/entity_ops_impl.py pass-only blanket swallow", exc_info=True)
        pass


def _entity_bounds(ent: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Return (cx, cy, half_w, half_h) from authored entity data, or *None* if no position."""
    return _geometry_helpers._entity_bounds(ent)


def _anchor_value(cx: float, cy: float, hw: float, hh: float, axis: str, mode: str) -> float:
    return _geometry_helpers._anchor_value(cx, cy, hw, hh, axis, mode)


def _snap_value(v: float, step: int, mode: str) -> float:
    """Snap *v* to the grid defined by *step* using *mode*.

    ``nearest`` - deterministic half-up rounding (ties round away from zero).
    ``floor`` - always round toward negative infinity.
    ``ceil``  - always round toward positive infinity.
    """
    return _geometry_helpers._snap_value(v, step, mode)


def _is_group_entity(ent: Dict[str, Any]) -> bool:
    """Return True if *ent* is a logical group container."""
    if ent.get("is_group") is True:
        return True
    tags = ent.get("tags")
    if isinstance(tags, list) and any(isinstance(t, str) and t.strip().lower() == "group" for t in tags):
        return True
    return False


def _next_group_id(used_ids: set[str]) -> str:
    """Return the next deterministic ``group_NNN`` id not in *used_ids*."""
    k = 1
    while True:
        candidate = f"group_{k}"
        if candidate not in used_ids:
            return candidate
        k += 1


def _next_group_name(entities: list[Dict[str, Any]], base: str) -> str:
    """Return ``{base}_NNN`` with the next available number (width=3)."""
    import re  # noqa: PLC0415

    pattern = re.compile(rf"^{re.escape(base)}_(\d+)$", re.IGNORECASE)
    max_n = 0
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        name = ent.get("name")
        if not isinstance(name, str):
            continue
        m = pattern.match(name.strip())
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return f"{base}_{max_n + 1:03d}"
