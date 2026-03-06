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
from engine.ui_overlays.widget_overlay_helpers import (
    apply_backspace,
    apply_enter,
    apply_mouse_press,
    apply_mouse_scroll,
    apply_nav_key,
    apply_text_input,
    resolve_preserved_selection_index,
)


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


logger = get_logger(__name__)


class EditorAssetBrowserController:
    """Encapsulates asset browser behavior."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def _get_overlay(self) -> Any | None:
        return getattr(self._editor, "asset_browser_overlay", None)

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
            overlay = self._get_overlay()
            reset = getattr(overlay, "reset_for_open", None)
            if callable(reset):
                reset()
            logger.info("[Editor] Asset browser OPEN")
        else:
            if self._editor.search.is_panel_search_focused("assets"):
                self._editor.search.clear_search_focus()
            overlay = self._get_overlay()
            reset = getattr(overlay, "reset_for_close", None)
            if callable(reset):
                reset()
            logger.info("[Editor] Asset browser CLOSED")
        self._editor._autosave_workspace()
        try:
            from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

            save_editor_ui_state_for_editor(self._editor)
        except Exception:  # noqa: BLE001
            _log_swallow("EDIT-001", "engine/editor/editor_asset_browser_controller.py pass-only blanket swallow")
            pass
        return bool(self._editor.asset_browser_active)

    def refresh_asset_browser(self) -> None:
        self._editor._asset_browser_cached_rows = scan_assets(self._editor._get_repo_root())
        self._filter_asset_browser()

    def set_asset_browser_filter(self, text: str) -> None:
        previous_rel_path: str | None = None
        rows_before = list(getattr(self._editor, "_asset_browser_filtered_rows", []) or [])
        prev_idx = int(getattr(self._editor, "asset_browser_selection_index", 0) or 0)
        if 0 <= prev_idx < len(rows_before):
            previous_rel_path = str(getattr(rows_before[prev_idx], "rel_path", "") or "") or None

        search = getattr(self._editor, "search", None)
        if search is not None and search.get_assets_search() != text:
            search.set_assets_search(text)
        if self._editor.asset_browser_filter == text:
            return
        self._editor.asset_browser_filter = text
        self._filter_asset_browser(previous_rel_path=previous_rel_path)
        self._editor._autosave_workspace()

    def cycle_asset_browser_kind(self) -> None:
        self._editor.asset_browser_kind = _cycle_asset_browser_kind_impl(self._editor.asset_browser_kind)
        self._filter_asset_browser()
        self._editor._autosave_workspace()

    def _filter_asset_browser(self, previous_rel_path: str | None = None) -> None:
        self._editor._asset_browser_filtered_rows = _filter_assets_for_browser_impl(
            self._editor._asset_browser_cached_rows,
            self._editor.asset_browser_filter,
            self._editor.asset_browser_kind,
        )
        previous_items = [{"rel_path": previous_rel_path}] if previous_rel_path else []
        resolved_idx, _preserved = resolve_preserved_selection_index(
            previous_items,
            self._editor._asset_browser_filtered_rows,
            0,
            identity_fn=lambda item: (
                str(item.get("rel_path", "") or "")
                if isinstance(item, dict)
                else str(getattr(item, "rel_path", "") or "")
            )
            or None,
            clamp_fn=_clamp_asset_selection_index_impl,
            fallback_index=int(getattr(self._editor, "asset_browser_selection_index", 0) or 0),
        )
        self._editor.asset_browser_selection_index = resolved_idx

    def asset_browser_move_selection(self, delta: int) -> None:
        count = len(self._editor._asset_browser_filtered_rows)
        self._editor.asset_browser_selection_index = _move_asset_selection_impl(
            self._editor.asset_browser_selection_index, delta, count
        )

    def handle_asset_browser_input(self, key: int, modifiers: int) -> bool:
        tab_key = getattr(optional_arcade.arcade.key, "TAB", None)
        page_up_key = getattr(optional_arcade.arcade.key, "PAGE_UP", None)
        if page_up_key is None:
            page_up_key = getattr(optional_arcade.arcade.key, "PAGEUP", None)
        page_down_key = getattr(optional_arcade.arcade.key, "PAGE_DOWN", None)
        if page_down_key is None:
            page_down_key = getattr(optional_arcade.arcade.key, "PAGEDOWN", None)
        home_key = getattr(optional_arcade.arcade.key, "HOME", None)
        end_key = getattr(optional_arcade.arcade.key, "END", None)
        return_key = getattr(optional_arcade.arcade.key, "RETURN", optional_arcade.arcade.key.ENTER)
        ctrl_n_key = getattr(optional_arcade.arcade.key, "N", None)
        ctrl_p_key = getattr(optional_arcade.arcade.key, "P", None)
        if bool(getattr(self._editor, "asset_browser_active", False)) and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
            if ctrl_n_key is not None and key == ctrl_n_key:
                key = optional_arcade.arcade.key.DOWN
            elif ctrl_p_key is not None and key == ctrl_p_key:
                key = optional_arcade.arcade.key.UP
            elif key in (optional_arcade.arcade.key.ENTER, return_key):
                overlay = self._get_overlay()
                activator = getattr(overlay, "activate_selected", None)
                if callable(activator) and bool(activator()):
                    return True
                self._activate_selected_asset()
                return True

        if key == optional_arcade.arcade.key.ESCAPE:
            self.toggle_asset_browser()
            return True
        if tab_key is not None and key == tab_key:
            overlay = self._get_overlay()
            toggle = getattr(overlay, "toggle_focus", None)
            if callable(toggle):
                toggle()
                return True
            return True
        if key in (
            optional_arcade.arcade.key.UP,
            optional_arcade.arcade.key.DOWN,
        ) or (page_up_key is not None and key == page_up_key) or (page_down_key is not None and key == page_down_key) or (
            home_key is not None and key == home_key
        ) or (end_key is not None and key == end_key):
            overlay = self._get_overlay()
            if apply_nav_key(overlay, key):
                return True
        if self._editor.search.is_panel_search_focused("assets"):
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor.search.backspace_search_text()
                return True
        if key == optional_arcade.arcade.key.UP:
            self.asset_browser_move_selection(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.asset_browser_move_selection(1)
            return True
        if page_up_key is not None and key == page_up_key:
            self.asset_browser_move_selection(-10)
            return True
        if page_down_key is not None and key == page_down_key:
            self.asset_browser_move_selection(10)
            return True
        if home_key is not None and key == home_key:
            self._editor.asset_browser_selection_index = 0
            return True
        if end_key is not None and key == end_key:
            count = len(self._editor._asset_browser_filtered_rows)
            if count > 0:
                self._editor.asset_browser_selection_index = count - 1
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            overlay = self._get_overlay()
            if apply_backspace(overlay):
                return True
            return True
        if key in (optional_arcade.arcade.key.ENTER, return_key):
            overlay = self._get_overlay()
            if apply_enter(overlay):
                return True
            self._activate_selected_asset()
            return True
        return True

    def handle_asset_browser_text_input(self, text: str) -> bool:
        if not self._editor.asset_browser_active:
            return False
        overlay = self._get_overlay()
        if apply_text_input(overlay, text):
            return True
        if text and text.isprintable():
            search = getattr(self._editor, "search", None)
            current = str(search.get_assets_search() if search is not None else "" or "")
            self.set_asset_browser_filter(current + text)
            return True
        return False

    def handle_asset_browser_mouse_click(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:
        if not self._editor.asset_browser_active:
            return False
        overlay = self._get_overlay()
        return apply_mouse_press(overlay, x, y, button=button, modifiers=modifiers)

    def handle_asset_browser_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
        if not self._editor.asset_browser_active:
            return False
        overlay = self._get_overlay()
        return apply_mouse_scroll(overlay, scroll_y, x=x, y=y, scroll_x=scroll_x)

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
