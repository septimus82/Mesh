# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

from typing import TYPE_CHECKING

from ...index_build import build_scene_index_from_sprites
from ._shared import _debug_iter_authoring_payloads, _debug_remove_sprite, debug_find_sprite_by_entity_id

if TYPE_CHECKING:
    from ....scene_controller import SceneController
def debug_remove_entity_by_id(controller: "SceneController", entity_id: str) -> bool:
    """Debug-only: remove an entity by id from payload(s) and from live sprites."""
    from ....entity_paint_mode import apply_remove_entity  # noqa: PLC0415

    removed_any = False
    for payload in _debug_iter_authoring_payloads(controller):
        if apply_remove_entity(payload, entity_id=entity_id):
            removed_any = True

    sprite = debug_find_sprite_by_entity_id(controller, entity_id)
    if sprite is not None:
        _debug_remove_sprite(controller, sprite)
        removed_any = True

    if removed_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return removed_any
