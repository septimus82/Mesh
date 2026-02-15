# mypy: disable-error-code=no-any-return

from __future__ import annotations

from typing import Any

from engine.editor_runtime import ops as editor_ops


def _selected_entity_ids_get(self: Any) -> list[str]:
    return self._selection_ctl.selected_ids


def _selected_entity_ids_set(self: Any, value: list[str]) -> None:
    if value is None:
        value = []
    self._selection_ctl.selected_ids = value


def _primary_entity_id_get(self: Any) -> str | None:
    return self._selection_ctl.primary_selected_id


def _primary_entity_id_set(self: Any, value: str | None) -> None:
    self._selection_ctl.primary_selected_id = value


def nudge_selected(self: Any, dx: float, dy: float) -> None:
    editor_ops.nudge_selected(self, dx, dy)


def duplicate_selected(self: Any) -> None:
    editor_ops.duplicate_selected(self)


def delete_selected(self: Any) -> None:
    if self.project_explorer_actions.delete_selected_paths_if_active():
        return
    editor_ops.delete_selected(self)


def copy_selected_entity_to_clipboard(self: Any) -> None:
    self.clipboard.copy_selected_entity()


def paste_entity_from_clipboard(self: Any, spawn_world_xy: tuple[float, float] | None = None) -> None:
    self.clipboard.paste_entity(spawn_world_xy)


def _entity_clipboard_get(self: Any) -> dict[str, Any] | None:
    return self.clipboard.entity_clipboard


def _entity_clipboard_set(self: Any, value: dict[str, Any] | None) -> None:
    self.clipboard.entity_clipboard = value


def _entity_clipboard_source_id_get(self: Any) -> str | None:
    return self.clipboard.entity_clipboard_source_id


def _entity_clipboard_source_id_set(self: Any, value: str | None) -> None:
    self.clipboard.entity_clipboard_source_id = value


def _hd2d_overrides_clipboard_get(self: Any) -> dict[str, Any] | None:
    return self.clipboard.hd2d_overrides_clipboard


def _hd2d_overrides_clipboard_set(self: Any, value: dict[str, Any] | None) -> None:
    self.clipboard.hd2d_overrides_clipboard = value


def _alt_dup_original_selection_get(self: Any) -> list[str] | None:
    return self.duplicate.original_selection


def _alt_dup_original_selection_set(self: Any, value: list[str] | None) -> None:
    self.duplicate.original_selection = value


def _alt_dup_drag_start_world_get(self: Any) -> tuple[float, float] | None:
    return self.duplicate.drag_start_world


def _alt_dup_drag_start_world_set(self: Any, value: tuple[float, float] | None) -> None:
    self.duplicate.drag_start_world = value


def _alt_dup_last_world_get(self: Any) -> tuple[float, float] | None:
    return self.duplicate.last_world


def _alt_dup_last_world_set(self: Any, value: tuple[float, float] | None) -> None:
    self.duplicate.last_world = value


def _alt_dup_original_primary_get(self: Any) -> str | None:
    return self.duplicate.original_primary


def _alt_dup_original_primary_set(self: Any, value: str | None) -> None:
    self.duplicate.original_primary = value


def begin_marquee(self: Any, world_x: float, world_y: float, shift: bool) -> None:
    self.marquee.begin(world_x, world_y, shift)


def update_marquee(self: Any, world_x: float, world_y: float) -> None:
    self.marquee.update(world_x, world_y)


def end_marquee(self: Any) -> None:
    self.marquee.end()


def cancel_marquee(self: Any) -> None:
    self.marquee.cancel()


def _reset_marquee(self: Any) -> None:
    self.marquee.reset()


def begin_alt_drag_duplicate(self: Any, world_x: float, world_y: float) -> None:
    self.duplicate.begin(world_x, world_y)


def update_alt_drag_duplicate(self: Any, world_x: float, world_y: float) -> None:
    self.duplicate.update(world_x, world_y)


def cancel_alt_drag_duplicate(self: Any) -> None:
    self.duplicate.cancel()


def end_alt_drag_duplicate(self: Any) -> None:
    self.duplicate.end()


def _reset_alt_drag_duplicate(self: Any) -> None:
    self.duplicate.reset()


def _get_entity_tags(self: Any, sprite: Any) -> list[str]:
    tags: list[str] = []
    entity_data = getattr(sprite, "mesh_entity_data", {}) or {}
    raw_tags = entity_data.get("tags")
    if isinstance(raw_tags, (list, tuple, set)):
        for entry in raw_tags:
            if isinstance(entry, str) and entry.strip():
                tags.append(entry.strip())
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags.append(raw_tags.strip())

    single_tag = getattr(sprite, "mesh_tag", None)
    if isinstance(single_tag, str) and single_tag.strip():
        tag_value = single_tag.strip()
        if tag_value not in tags:
            tags.append(tag_value)
    return tags


def bind_selection_clipboard_methods(controller_cls: Any) -> None:
    controller_cls._selected_entity_ids = property(_selected_entity_ids_get, _selected_entity_ids_set)
    controller_cls._primary_entity_id = property(_primary_entity_id_get, _primary_entity_id_set)
    controller_cls._entity_clipboard = property(_entity_clipboard_get, _entity_clipboard_set)
    controller_cls._entity_clipboard_source_id = property(
        _entity_clipboard_source_id_get,
        _entity_clipboard_source_id_set,
    )
    controller_cls._hd2d_overrides_clipboard = property(
        _hd2d_overrides_clipboard_get,
        _hd2d_overrides_clipboard_set,
    )
    controller_cls._alt_dup_original_selection = property(
        _alt_dup_original_selection_get,
        _alt_dup_original_selection_set,
    )
    controller_cls._alt_dup_drag_start_world = property(
        _alt_dup_drag_start_world_get,
        _alt_dup_drag_start_world_set,
    )
    controller_cls._alt_dup_last_world = property(_alt_dup_last_world_get, _alt_dup_last_world_set)
    controller_cls._alt_dup_original_primary = property(
        _alt_dup_original_primary_get,
        _alt_dup_original_primary_set,
    )

    method_map = {
        "nudge_selected": nudge_selected,
        "duplicate_selected": duplicate_selected,
        "delete_selected": delete_selected,
        "copy_selected_entity_to_clipboard": copy_selected_entity_to_clipboard,
        "paste_entity_from_clipboard": paste_entity_from_clipboard,
        "begin_marquee": begin_marquee,
        "update_marquee": update_marquee,
        "end_marquee": end_marquee,
        "cancel_marquee": cancel_marquee,
        "_reset_marquee": _reset_marquee,
        "begin_alt_drag_duplicate": begin_alt_drag_duplicate,
        "update_alt_drag_duplicate": update_alt_drag_duplicate,
        "cancel_alt_drag_duplicate": cancel_alt_drag_duplicate,
        "end_alt_drag_duplicate": end_alt_drag_duplicate,
        "_reset_alt_drag_duplicate": _reset_alt_drag_duplicate,
        "_get_entity_tags": _get_entity_tags,
    }
    for name, fn in method_map.items():
        setattr(controller_cls, name, fn)
