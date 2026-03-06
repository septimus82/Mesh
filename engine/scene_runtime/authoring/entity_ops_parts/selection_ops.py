# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

import engine.optional_arcade as optional_arcade

from ...index_build import build_scene_index_from_sprites
from ._shared import _debug_iter_authoring_payloads, debug_find_sprite_by_entity_id

if TYPE_CHECKING:
    from ....scene_controller import SceneController
def debug_add_entity_payload(controller: "SceneController", entity_payload: Dict[str, Any]) -> bool:
    """
    Debug-only: add a new entity payload (by id) to the authored + runtime payloads and spawn a sprite.
    """
    from ....entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415

    if not isinstance(entity_payload, dict):
        return False
    entity_id = str(entity_payload.get("id") or "").strip()
    if not entity_id:
        return False

    prefab_id = entity_payload.get("prefab_id")
    if not isinstance(prefab_id, str) or not prefab_id.strip():
        return False

    changed_any = False
    for payload in _debug_iter_authoring_payloads(controller):
        entities = ensure_entities_list(payload)
        if find_entity_by_id(entities, entity_id) is not None:
            continue
        entities.append(dict(entity_payload))
        changed_any = True

    if not changed_any:
        return False

    sprite = controller._create_sprite(dict(entity_payload))
    if sprite is None:
        return True

    layer_name = str(entity_payload.get("layer") or "entities")
    if layer_name not in controller.layers:
        controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
    controller.layers[layer_name].append(sprite)
    controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return True


def debug_move_entity_by_id(controller: "SceneController", entity_id: str, *, x: float, y: float) -> bool:
    """Debug-only: move an entity by id in payload(s) and update the live sprite if present."""
    from ....entity_paint_mode import apply_move_entity  # noqa: PLC0415

    moved_any = False
    for payload in _debug_iter_authoring_payloads(controller):
        if apply_move_entity(payload, entity_id=entity_id, x=x, y=y):
            moved_any = True

    sprite = debug_find_sprite_by_entity_id(controller, entity_id)
    if sprite is not None:
        sprite.center_x = float(x)
        sprite.center_y = float(y)
        data = getattr(sprite, "mesh_entity_data", None)
        if isinstance(data, dict):
            data["x"] = float(x)
            data["y"] = float(y)
        moved_any = True

    if moved_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return moved_any
