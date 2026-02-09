from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.asset_index import AssetRow, scan_assets
from engine.logging_tools import get_logger
from engine.editor_asset_ops import spawn_entity_from_asset
from engine.editor.asset_browser_panel import (
    clamp_asset_selection_index as _clamp_asset_selection_index_impl,
    cycle_asset_browser_kind as _cycle_asset_browser_kind_impl,
    filter_assets_for_browser as _filter_assets_for_browser_impl,
    move_asset_selection as _move_asset_selection_impl,
    resolve_asset_activation as _resolve_asset_activation_impl,
)
from engine.editor_light_occluder_ops import snap_world_point


logger = get_logger(__name__)


class EditorAssetBrowserController:
    """Encapsulates asset browser behavior."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def toggle_asset_browser(self) -> bool:
        if not self._editor.active:
            return False
        self._editor.asset_browser_active = not self._editor.asset_browser_active
        if self._editor.asset_browser_active:
            # Close conflicting overlays
            self._editor.scene_switcher_active = False
            self._editor.scene_browser_active = False
            self._editor.panels.close_command_palette()

            self.refresh_asset_browser()
            logger.info("[Editor] Asset browser OPEN")
        else:
            if self._editor.search.is_panel_search_focused("assets"):
                self._editor.search.clear_search_focus()
            logger.info("[Editor] Asset browser CLOSED")
        self._editor._autosave_workspace()
        return bool(self._editor.asset_browser_active)

    def refresh_asset_browser(self) -> None:
        self._editor._asset_browser_cached_rows = scan_assets(self._editor._get_repo_root())
        self._filter_asset_browser()

    def set_asset_browser_filter(self, text: str) -> None:
        search = getattr(self._editor, "search", None)
        if search is not None and search.get_assets_search() != text:
            search.set_assets_search(text)
        if self._editor.asset_browser_filter == text:
            return
        self._editor.asset_browser_filter = text
        self._filter_asset_browser()
        self._editor._autosave_workspace()

    def cycle_asset_browser_kind(self) -> None:
        self._editor.asset_browser_kind = _cycle_asset_browser_kind_impl(self._editor.asset_browser_kind)
        self._filter_asset_browser()
        self._editor._autosave_workspace()

    def _filter_asset_browser(self) -> None:
        self._editor._asset_browser_filtered_rows = _filter_assets_for_browser_impl(
            self._editor._asset_browser_cached_rows,
            self._editor.asset_browser_filter,
            self._editor.asset_browser_kind,
        )
        self._editor.asset_browser_selection_index = _clamp_asset_selection_index_impl(
            self._editor.asset_browser_selection_index,
            len(self._editor._asset_browser_filtered_rows),
        )

    def asset_browser_move_selection(self, delta: int) -> None:
        count = len(self._editor._asset_browser_filtered_rows)
        self._editor.asset_browser_selection_index = _move_asset_selection_impl(
            self._editor.asset_browser_selection_index, delta, count
        )

    def handle_asset_browser_input(self, key: int, modifiers: int) -> bool:
        if key == optional_arcade.arcade.key.ESCAPE:
            self.toggle_asset_browser()
            return True
        if self._editor.search.is_panel_search_focused("assets"):
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor.search.backspace_search_text()
                return True
        if key == optional_arcade.arcade.key.TAB:
            self.cycle_asset_browser_kind()
            return True
        if key == optional_arcade.arcade.key.UP:
            self.asset_browser_move_selection(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.asset_browser_move_selection(1)
            return True
        if key == optional_arcade.arcade.key.PAGE_UP:
            self.asset_browser_move_selection(-10)
            return True
        if key == optional_arcade.arcade.key.PAGE_DOWN:
            self.asset_browser_move_selection(10)
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            return True
        if key == optional_arcade.arcade.key.ENTER:
            self._activate_selected_asset()
            return True
        return True

    def _activate_selected_asset(self) -> None:
        if not self._editor._asset_browser_filtered_rows:
            return

        idx = _clamp_asset_selection_index_impl(
            self._editor.asset_browser_selection_index,
            len(self._editor._asset_browser_filtered_rows),
        )
        if idx < 0 or idx >= len(self._editor._asset_browser_filtered_rows):
            return

        row: AssetRow = self._editor._asset_browser_filtered_rows[idx]
        intent = _resolve_asset_activation_impl(row)

        hud = getattr(self._editor.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud else None

        if intent["kind"] == "spawn_entity":
            # Enter placement mode
            self._editor.asset_place_active = True
            self._editor.asset_place_path = intent["asset_path"]
            self._editor.asset_place_kind = row.kind
            self._editor.asset_browser_active = False

            if callable(toaster):
                toaster(f"Placement Mode: {row.display_name}")
        else:
            # Copy path (mock)
            if callable(toaster):
                toaster(f"Copied: {intent['asset_path']}")

    def place_asset_at(self, x: float, y: float) -> None:
        if not self._editor.asset_place_active or not self._editor.asset_place_path:
            return

        if self._editor.snap_enabled:
            x, y = snap_world_point((x, y), self._editor.snap_mode, self._editor.grid_size)

        scene_controller = getattr(self._editor.window, "scene_controller", None)
        if scene_controller:
            scene_data = getattr(scene_controller, "_loaded_scene_data", None)
            if isinstance(scene_data, dict):
                spawn_entity_from_asset(scene_data, self._editor.asset_place_path, (x, y))
                self._editor.scene_dirty = True
                if hasattr(scene_controller, "reload_scene"):
                    scene_controller.reload_scene()

    def activate_find_asset(self, asset_path: str) -> bool:
        row = self._editor._find_asset_lookup.get(asset_path)
        if row is None:
            return self._copy_find_asset_path(asset_path)

        intent = _resolve_asset_activation_impl(row)
        if intent.get("kind") == "spawn_entity":
            return self._spawn_find_asset(str(intent.get("asset_path", asset_path)))
        return self._copy_find_asset_path(str(intent.get("asset_path", asset_path)))

    def _spawn_find_asset(self, asset_path: str) -> bool:
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return False
        cam_x, cam_y = self._editor._get_camera_center()
        self._editor.asset_place_active = True
        self._editor.asset_place_path = asset_path
        self.place_asset_at(cam_x, cam_y)
        self._editor.asset_place_active = False
        self._editor.asset_place_path = None
        return True

    def _copy_find_asset_path(self, asset_path: str) -> bool:
        hud = getattr(self._editor.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster(f"Copied path: {asset_path}")
        return True
