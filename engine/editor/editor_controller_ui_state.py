from __future__ import annotations

from typing import Any


def ui_activate_command(self, cmd_id: str):
    return self._activate_find_command(cmd_id)


def ui_activate_asset(self, item_id: str):
    return self._activate_find_asset(item_id)


def ui_activate_scene(self, item_id: str):
    return self._activate_find_scene(item_id)


def ui_activate_entity(self, item_id: str):
    return self._activate_find_entity(item_id)


def ui_activate_problem(self, item_id: str):
    return self._activate_find_problem(item_id)


def ui_get_palette_items(self):
    return self.search.ui_get_palette_items()


def _ui_get_problems(self, scene_data: Any, window: Any):
    """Helper for palette items."""
    return self.search._ui_get_problems(scene_data, window)

def ui_hd2d_preview(self, preset_id: str):
    self.preview_hd2d_preset(preset_id)


def ui_hd2d_cancel_preview(self):
    self._cancel_hd2d_preview()


def ui_hd2d_commit(self, preset_id: str):
    return self.commit_hd2d_preset(preset_id)

def bind_ui_state_methods(cls: Any) -> None:
    cls.ui_activate_command = ui_activate_command
    cls.ui_activate_asset = ui_activate_asset
    cls.ui_activate_scene = ui_activate_scene
    cls.ui_activate_entity = ui_activate_entity
    cls.ui_activate_problem = ui_activate_problem
    cls.ui_get_palette_items = ui_get_palette_items
    cls._ui_get_problems = _ui_get_problems
    cls.ui_hd2d_preview = ui_hd2d_preview
    cls.ui_hd2d_cancel_preview = ui_hd2d_cancel_preview
    cls.ui_hd2d_commit = ui_hd2d_commit
