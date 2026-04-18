"""Binder: Dialogue, Animation & Tile panel delegation shims.

Extracted from ``engine.editor_controller`` to reduce god-class bloat.
Every function takes ``self`` (an ``EditorModeController``) as first arg.
``bind_content_panels_bridge_methods`` monkey-patches them onto the class.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:
    from arcade import Sprite
    from engine.editor_controller import EditorModeController


# -- Dialogue / Quest shims ------------------------------------------------

def _entity_has_dialogue(self: "EditorModeController", sprite: "Optional[Sprite]") -> bool:
    return self.dialogue.entity_has_dialogue(sprite)


def _refresh_dialogue_cache(self: "EditorModeController") -> None:
    self.dialogue.refresh_dialogue_cache()


def _get_entity_dialogue_config(self: "EditorModeController", sprite: "Sprite") -> Dict[str, Any]:
    return self.dialogue.get_entity_dialogue_config(sprite)


def _set_entity_dialogue_config(self: "EditorModeController", sprite: "Sprite", dialogue_root: Dict[str, Any]) -> None:
    self.dialogue.set_entity_dialogue_config(sprite, dialogue_root)


def _dialogue_nodes(self: "EditorModeController") -> List[Dict[str, Any]]:
    return self.dialogue.dialogue_nodes()


def _get_selected_node(self: "EditorModeController") -> Optional[Dict[str, Any]]:
    return self.dialogue.get_selected_node()


def _get_selected_choice(self: "EditorModeController", node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return self.dialogue.get_selected_choice(node)


def _next_dialogue_field(self: "EditorModeController", current: str, *, has_choice: bool) -> str:
    return self.dialogue.next_dialogue_field(current, has_choice=has_choice)


def _prev_dialogue_field(self: "EditorModeController", current: str, *, has_choice: bool) -> str:
    return self.dialogue.prev_dialogue_field(current, has_choice=has_choice)


def _begin_dialogue_edit(self: "EditorModeController") -> None:
    self.dialogue.begin_dialogue_edit()


def _commit_dialogue_edit(self: "EditorModeController") -> None:
    self.dialogue.commit_dialogue_edit()


def _apply_dialogue_edit(
    self: "EditorModeController",
    node: Dict[str, Any],
    choice: Optional[Dict[str, Any]],
    focus: str,
    new_text: str,
) -> bool:
    return self.dialogue.apply_dialogue_edit(node, choice, focus, new_text)


def _collect_dialogue_warnings(self: "EditorModeController", dialogue_root: Dict[str, Any]) -> List[str]:
    return self.dialogue.collect_dialogue_warnings(dialogue_root)


def _quest_definitions(self: "EditorModeController") -> Dict[str, Dict[str, Any]]:
    return self.dialogue._quest_definitions()


def _related_quest_ids(self: "EditorModeController", sprite: "Optional[Sprite]") -> set[str]:
    return self.dialogue._related_quest_ids(sprite)


# -- Animation shims -------------------------------------------------------

def _entity_has_animator(self: "EditorModeController", sprite: "Optional[Sprite]") -> bool:
    return self.animation.entity_has_animator(sprite)


def _refresh_animation_cache(self: "EditorModeController") -> None:
    self.animation.refresh_animation_cache()


def _get_animator_config(self: "EditorModeController", sprite: "Optional[Sprite]") -> Dict[str, Any]:
    return self.animation.get_animator_config(sprite)


def _set_animator_config(self: "EditorModeController", sprite: "Sprite", animator_cfg: Dict[str, Any]) -> None:
    self.animation.set_animator_config(sprite, animator_cfg)


def _apply_animator_runtime(self: "EditorModeController", sprite: "Sprite", animator_cfg: Dict[str, Any]) -> None:
    self.animation.apply_animator_runtime(sprite, animator_cfg)


def _next_animation_field(self: "EditorModeController", current: str) -> str:
    return self.animation.next_animation_field(current)


def _prev_animation_field(self: "EditorModeController", current: str) -> str:
    return self.animation.prev_animation_field(current)


def _cycle_mode(self: "EditorModeController", current: str, forward: bool) -> str:
    return self.animation.cycle_mode(current, forward)


def _commit_animation_edit(self: "EditorModeController") -> None:
    self.animation.commit_animation_edit()


def _apply_animation_change(
    self: "EditorModeController",
    names: List[str],
    animations: Dict[str, Any],
    clip_name: str,
    field: str,
    new_value: Any,
) -> None:
    self.animation.apply_animation_change(names, animations, clip_name, field, new_value)


# -- Tile shims ------------------------------------------------------------

def _tilemap_available(self: "EditorModeController") -> bool:
    return self.tile.tilemap_available()


def _set_tile_panel_active(self: "EditorModeController", value: bool) -> None:
    self.tile.set_tile_panel_active(value)


def _refresh_tile_palette(self: "EditorModeController") -> None:
    self.tile.refresh_tile_palette()


def _current_tile_gid(self: "EditorModeController") -> int:
    return self.tile.current_tile_gid()


def _paint_tile_at(self: "EditorModeController", world_x: float, world_y: float, gid: int) -> None:
    self.tile.paint_tile_at(world_x, world_y, gid)


def _current_tile_layer(self: "EditorModeController") -> str:
    return self.tile.current_tile_layer()


# ---------------------------------------------------------------------------
# Binder
# ---------------------------------------------------------------------------

def bind_content_panels_bridge_methods(cls: Any) -> None:
    # Dialogue
    cls._entity_has_dialogue = _entity_has_dialogue
    cls._refresh_dialogue_cache = _refresh_dialogue_cache
    cls._get_entity_dialogue_config = _get_entity_dialogue_config
    cls._set_entity_dialogue_config = _set_entity_dialogue_config
    cls._dialogue_nodes = _dialogue_nodes
    cls._get_selected_node = _get_selected_node
    cls._get_selected_choice = _get_selected_choice
    cls._next_dialogue_field = _next_dialogue_field
    cls._prev_dialogue_field = _prev_dialogue_field
    cls._begin_dialogue_edit = _begin_dialogue_edit
    cls._commit_dialogue_edit = _commit_dialogue_edit
    cls._apply_dialogue_edit = _apply_dialogue_edit
    cls._collect_dialogue_warnings = _collect_dialogue_warnings
    cls._quest_definitions = _quest_definitions
    cls._related_quest_ids = _related_quest_ids
    # Animation
    cls._entity_has_animator = _entity_has_animator
    cls._refresh_animation_cache = _refresh_animation_cache
    cls._get_animator_config = _get_animator_config
    cls._set_animator_config = _set_animator_config
    cls._apply_animator_runtime = _apply_animator_runtime
    cls._next_animation_field = _next_animation_field
    cls._prev_animation_field = _prev_animation_field
    cls._cycle_mode = _cycle_mode
    cls._commit_animation_edit = _commit_animation_edit
    cls._apply_animation_change = _apply_animation_change
    # Tile
    cls._tilemap_available = _tilemap_available
    cls._set_tile_panel_active = _set_tile_panel_active
    cls._refresh_tile_palette = _refresh_tile_palette
    cls._current_tile_gid = _current_tile_gid
    cls._paint_tile_at = _paint_tile_at
    cls._current_tile_layer = _current_tile_layer
