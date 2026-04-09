from __future__ import annotations

from typing import Any


def _format_coord(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    text = f"{float(value):.1f}"
    if text.endswith(".0"):
        return text[:-2]
    return text


def get_scene_inspector_payload(window: Any) -> dict[str, Any] | None:
    overlay = getattr(window, "scene_inspector_overlay", None)
    provider = getattr(overlay, "provider", None)
    if not callable(provider):
        return None
    try:
        value = provider(window)
    except Exception:  # noqa: BLE001  # REASON: scene-inspector provider failures should fail closed to no authoring snippet payload
        return None
    return value if isinstance(value, dict) else None


def build_player_pos_snippet(payload: dict[str, Any] | None) -> str:
    player = payload.get("player") if isinstance(payload, dict) else None
    if not isinstance(player, dict):
        return "PLAYER_POS (missing player position)"
    x = _format_coord(player.get("x"))
    y = _format_coord(player.get("y"))
    if x == "-" or y == "-":
        return "PLAYER_POS (missing player position)"
    return f"PLAYER_POS --x {x} --y {y}"


def build_hover_pos_snippet(payload: dict[str, Any] | None) -> str:
    hover = payload.get("hover") if isinstance(payload, dict) else None
    if not isinstance(hover, dict):
        return "HOVER_POS (no hovered entity)"

    pos = hover.get("pos")
    if not isinstance(pos, dict):
        return "HOVER_POS (no hovered entity)"

    x = _format_coord(pos.get("x"))
    y = _format_coord(pos.get("y"))
    if x == "-" or y == "-":
        return "HOVER_POS (no hovered entity)"

    entity_id = hover.get("id")
    prefab_id = hover.get("prefab_id")
    if entity_id in (None, "") or prefab_id in (None, ""):
        return "HOVER_POS (no hovered entity)"

    return f"HOVER_POS --x {x} --y {y} --id {entity_id} --prefab {prefab_id}"


def _get_selected_entity_id(window: Any) -> str | None:
    value = getattr(window, "authoring_selected_entity_id", None)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _set_selected_entity_id(window: Any, value: str | None) -> None:
    setattr(window, "authoring_selected_entity_id", value)
    editor = getattr(window, "editor_controller", None)
    session = getattr(editor, "session", None) if editor is not None else None
    setter = getattr(session, "set_authoring_selected_active", None) if session is not None else None
    if callable(setter):
        setter(bool(value))


def _build_hover_payload_from_sprite(sprite: Any) -> dict[str, Any]:
    entity_data = getattr(sprite, "mesh_entity_data", None)
    if not isinstance(entity_data, dict):
        entity_data = {}
    entity_id = entity_data.get("id") or entity_data.get("entity_id")
    prefab_id = entity_data.get("prefab_id")
    return {
        "id": entity_id,
        "prefab_id": prefab_id,
        "pos": {"x": float(getattr(sprite, "center_x", 0.0)), "y": float(getattr(sprite, "center_y", 0.0))},
    }


def _find_sprite_by_entity_id(window: Any, entity_id: str) -> Any | None:
    scene = getattr(window, "scene_controller", None)
    sprites = getattr(scene, "all_sprites", None)
    if sprites is None:
        return None
    try:
        from engine.scene_index import SceneIndex  # noqa: PLC0415

        idx = SceneIndex.build_from_sprites(sprites)
        return idx.get_by_id(entity_id)
    except Exception:  # noqa: BLE001  # REASON: SceneIndex lookup failures should fall back to a direct sprite scan for the requested entity id
        for sprite in sprites:
            data = getattr(sprite, "mesh_entity_data", None)
            if isinstance(data, dict):
                if (data.get("id") or data.get("entity_id")) == entity_id:
                    return sprite
        return None


def toggle_locked_selection_from_hover(window: Any, payload: dict[str, Any] | None) -> str | None:
    """
    Toggle the authoring selection based on hover payload.

    Returns the selected id (when set) or None (when cleared or missing hover).
    """
    current = _get_selected_entity_id(window)
    if current is not None:
        _set_selected_entity_id(window, None)
        return None

    hover = payload.get("hover") if isinstance(payload, dict) else None
    if not isinstance(hover, dict):
        _set_selected_entity_id(window, None)
        return None

    hover_id = hover.get("id")
    if not isinstance(hover_id, str) or not hover_id.strip():
        _set_selected_entity_id(window, None)
        return None

    selected = hover_id.strip()
    _set_selected_entity_id(window, selected)
    return selected


def get_effective_hover_payload(window: Any, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Return a payload where hover reflects the locked selection when set.
    """
    selected = _get_selected_entity_id(window)
    if selected is None:
        return payload

    sprite = _find_sprite_by_entity_id(window, selected)
    if sprite is None:
        _set_selected_entity_id(window, None)
        return payload

    hover_payload = _build_hover_payload_from_sprite(sprite)
    merged: dict[str, Any] = dict(payload) if isinstance(payload, dict) else {}
    merged["hover"] = hover_payload
    return merged


def nudge_selected_entity(window: Any, *, dx: float, dy: float) -> bool:
    selected = _get_selected_entity_id(window)
    if selected is None:
        return False

    sprite = _find_sprite_by_entity_id(window, selected)
    if sprite is None:
        _set_selected_entity_id(window, None)
        return False

    sprite.center_x = float(getattr(sprite, "center_x", 0.0)) + float(dx)
    sprite.center_y = float(getattr(sprite, "center_y", 0.0)) + float(dy)

    entity_data = getattr(sprite, "mesh_entity_data", None)
    if isinstance(entity_data, dict):
        entity_data["x"] = float(sprite.center_x)
        entity_data["y"] = float(sprite.center_y)
    return True
