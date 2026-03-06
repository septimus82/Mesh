from __future__ import annotations

from typing import Any
from engine.editor.state import SCENE_SWITCHER_RECENT_LIMIT
from engine.path_norm import normalize_scene_path

def record_recent_scene(self, scene_path: str):
    normalized = normalize_scene_path(scene_path)
    if not normalized:
        return
    recent = [path for path in self.scene_switcher_recent if path != normalized]
    recent.insert(0, normalized)
    self.scene_switcher_recent = recent[:SCENE_SWITCHER_RECENT_LIMIT]


def _refresh_scene_switcher_items(self):
    self.scene_browse.refresh_scene_switcher_items()


def _scene_switcher_all_options(self):
    return self.scene_browse.scene_switcher_all_options()


def _scene_switcher_visible_options(self):
    return self.scene_browse.scene_switcher_visible_options()


def _scene_switcher_clamp_index(self, count: int):
    self.scene_browse.scene_switcher_clamp_index(count)


def _scene_switcher_lines(self):
    return self.scene_browse.scene_switcher_lines()


def _refresh_scene_browser_rows(self):
    self.scene_browse.refresh_scene_browser_rows()


def _scene_browser_rows(self):
    return self.scene_browse.scene_browser_rows()


def _scene_browser_clamp_index(self, count: int):
    self.scene_browse.scene_browser_clamp_index(count)


def _scene_browser_window(self, count: int):
    return self.scene_browse.scene_browser_window(count)


def _scene_browser_layout(self, count: int):
    return self.scene_browse.scene_browser_layout(count)


def _scene_browser_lines(self):
    return self.scene_browse.scene_browser_lines()


def _open_scene_by_id(self, scene_id: str):
    return self.scene_open.open_scene_by_id(scene_id)


def _scene_switcher_open_selected(self):
    return self.scene_browse.scene_switcher_open_selected()


def _scene_browser_open_selected(self):
    return self.scene_browse.scene_browser_open_selected()


def _scene_browser_handle_mouse_click(self, x: float, y: float, button: int):
    return self.scene_browse.scene_browser_handle_mouse_click(x, y, button)

def bind_scene_ops_methods(cls: Any) -> None:
    cls.record_recent_scene = record_recent_scene
    cls._refresh_scene_switcher_items = _refresh_scene_switcher_items
    cls._scene_switcher_all_options = _scene_switcher_all_options
    cls._scene_switcher_visible_options = _scene_switcher_visible_options
    cls._scene_switcher_clamp_index = _scene_switcher_clamp_index
    cls._scene_switcher_lines = _scene_switcher_lines
    cls._refresh_scene_browser_rows = _refresh_scene_browser_rows
    cls._scene_browser_rows = _scene_browser_rows
    cls._scene_browser_clamp_index = _scene_browser_clamp_index
    cls._scene_browser_window = _scene_browser_window
    cls._scene_browser_layout = _scene_browser_layout
    cls._scene_browser_lines = _scene_browser_lines
    cls._open_scene_by_id = _open_scene_by_id
    cls._scene_switcher_open_selected = _scene_switcher_open_selected
    cls._scene_browser_open_selected = _scene_browser_open_selected
    cls._scene_browser_handle_mouse_click = _scene_browser_handle_mouse_click
