"""Mouse handling for entity_paint scope."""
from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine.input_runtime.capture_mouse_router_handlers_modal_base import (
    maybe_handle_editor_mouse_press,
)
from engine.input_runtime.capture_mouse_router_model import MouseEvent


def dispatch_entity_paint_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for entity_paint scope."""
    window = controller.window

    if action_id == "mouse.entity_paint.press":
        if maybe_handle_editor_mouse_press(window, event):
            return True
        return _handle_entity_paint_mouse_press(window, event)

    if action_id == "mouse.entity_paint.scroll":
        return _handle_entity_paint_mouse_scroll(window, event)

    return False


def _handle_entity_paint_mouse_press(window: Any, event: MouseEvent) -> bool:
    from engine.entity_paint_mode import (  # noqa: PLC0415
        EntityPaintState,
        build_add_snippet,
        get_selected_prefab_id,
        load_prefab_infos,
        make_entity_id,
    )

    entity_state = getattr(window, "entity_paint_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(entity_state, EntityPaintState)
        and bool(getattr(entity_state, "enabled", False))
    ):
        return False
    if int(event.button or 0) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        return True

    # Ensure prefabs loaded if missing
    if not getattr(entity_state, "prefabs", ()):
        entity_state.prefabs = load_prefab_infos()

    prefab_id = get_selected_prefab_id(entity_state)
    if not isinstance(prefab_id, str) or not prefab_id.strip():
        print("ENTITY_ADD noop reason=no_prefab")
        return True

    sc = getattr(window, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "")
    try:
        world_x, world_y = window.screen_to_world(float(event.x), float(event.y))
    except Exception:  # noqa: BLE001  # REASON: screen-to-world conversion failures should fall back to no entity-paint placement click
        return True

    entity_id = make_entity_id(scene_path, prefab_id, float(world_x), float(world_y))
    payload = {
        "id": entity_id,
        "prefab_id": str(prefab_id),
        "x": float(world_x),
        "y": float(world_y),
        "layer": "entities",
    }
    added = False
    adder = getattr(sc, "debug_add_entity_payload", None) if sc is not None else None
    if callable(adder):
        added = bool(adder(payload))
    else:
        authored = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
        payloads_list: list[dict] = []
        if callable(authored):
            try:
                payloads_list.append(authored())
            except Exception:  # noqa: BLE001  # REASON: authored scene payload queries are optional and should fall back to loaded scene payloads only
                payloads_list = []
        if not payloads_list and sc is not None and isinstance(getattr(sc, "_loaded_scene_data", None), dict):
            payloads_list.append(sc._loaded_scene_data)
        for scene_payload in payloads_list:
            ents = scene_payload.setdefault("entities", [])
            if isinstance(ents, list):
                ents.append(dict(payload))
                added = True
    if added:
        entity_state.adds += 1
        entity_state.last_snippet = build_add_snippet(
            prefab_id=str(prefab_id),
            entity_id=entity_id,
            x=float(world_x),
            y=float(world_y),
        )
        marker = getattr(window, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_paint")
        from engine.input_runtime.capture_io import _recent_push_str  # noqa: PLC0415

        _recent_push_str(window, attr="prefab_recent", value=str(prefab_id), max_items=12)
        print(f"ENTITY_ADD ok prefab={prefab_id} id={entity_id}")
    else:
        print("ENTITY_ADD noop reason=duplicate")
    return True


def _handle_entity_paint_mouse_scroll(window: Any, event: MouseEvent) -> bool:
    from engine.entity_paint_mode import EntityPaintState, cycle_selected_prefab  # noqa: PLC0415

    state = getattr(window, "entity_paint_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, EntityPaintState)
        and bool(getattr(state, "enabled", False))
    ):
        return False

    delta = int(1 if float(event.scroll_y) > 0 else (-1 if float(event.scroll_y) < 0 else 0))
    if delta == 0:
        return True

    cycle_selected_prefab(state, direction=delta)
    return True


__all__ = ["dispatch_entity_paint_mouse"]
