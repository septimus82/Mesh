from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.editor.scene_opening import (
    build_scene_browser_lines,
    build_scene_switcher_lines,
    build_scene_switcher_rows,
    clamp_scene_selection_index,
    compute_scene_browser_hit_index,
    compute_scene_browser_layout,
    compute_scene_window,
)
from engine.logging_tools import get_logger
from engine.swallowed_exceptions import _log_swallow
from engine.ui_overlays.widget_overlay_helpers import (
    apply_backspace,
    apply_enter,
    apply_mouse_press,
    apply_mouse_scroll,
    apply_nav_key,
    apply_text_input,
)


logger = get_logger(__name__)


class EditorSceneBrowseController:
    """Orchestrates scene switcher/browser UI interactions."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def _get_scene_browser_overlay(self) -> Any:
        window = getattr(self._editor, "window", None)
        if window is None:
            return None
        return getattr(window, "scene_browser_overlay", None)

    def toggle_scene_switcher(self) -> bool:
        if not self._editor.active:
            return False
        self._editor.scene_switcher_active = not self._editor.scene_switcher_active
        if self._editor.scene_switcher_active:
            self._editor.scene_browser_active = False
            self._editor.scene_switcher_query = ""
            self._editor.scene_switcher_index = 0
            self.refresh_scene_switcher_items()
            logger.info("[Editor] Scene switcher OPEN")
        else:
            self._editor.scene_switcher_query = ""
            self._editor.scene_switcher_index = 0
            logger.info("[Editor] Scene switcher CLOSED")
        self._editor._autosave_workspace()
        try:
            from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

            save_editor_ui_state_for_editor(self._editor)
        except Exception:  # noqa: BLE001  # REASON: editor UI state persistence is best-effort and should not block scene switcher toggles
            _log_swallow("EDIT-001", "engine/editor/editor_scene_browse_controller.py pass-only blanket swallow")
            pass
        return bool(self._editor.scene_switcher_active)

    def toggle_scene_browser(self) -> bool:
        if not self._editor.active:
            return False
        self._editor.scene_browser_active = not self._editor.scene_browser_active
        if self._editor.scene_browser_active:
            self._editor.scene_switcher_active = False
            self._editor.scene_browser_query = ""
            self._editor.scene_browser_index = 0
            self.refresh_scene_browser_rows()
            logger.info("[Editor] Scene browser OPEN")
        else:
            self._editor.scene_browser_query = ""
            self._editor.scene_browser_index = 0
            logger.info("[Editor] Scene browser CLOSED")
        self._editor._autosave_workspace()
        try:
            from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

            save_editor_ui_state_for_editor(self._editor)
        except Exception:  # noqa: BLE001  # REASON: editor UI state persistence is best-effort and should not block scene browser toggles
            _log_swallow("EDIT-002", "engine/editor/editor_scene_browse_controller.py pass-only blanket swallow")
            pass
        return bool(self._editor.scene_browser_active)

    def refresh_scene_switcher_items(self) -> None:
        from engine.scene_index import list_pack_scene_options  # noqa: PLC0415

        self._editor._scene_switcher_cached = list_pack_scene_options()

    def scene_switcher_all_options(self) -> list[tuple[str, str]]:
        if not self._editor._scene_switcher_cached:
            self.refresh_scene_switcher_items()
        return list(self._editor._scene_switcher_cached)

    def scene_switcher_visible_options(self) -> list[tuple[str, str]]:
        options = self.scene_switcher_all_options()
        return build_scene_switcher_rows(
            options,
            self._editor.scene_switcher_query,
            self._editor.scene_switcher_recent,
        )

    def scene_switcher_clamp_index(self, count: int) -> None:
        self._editor.scene_switcher_index = clamp_scene_selection_index(
            self._editor.scene_switcher_index, count
        )

    def scene_switcher_lines(self) -> list[str]:
        options = self.scene_switcher_visible_options()
        self.scene_switcher_clamp_index(len(options))
        return build_scene_switcher_lines(
            self._editor.scene_switcher_active,
            self._editor.scene_switcher_query,
            options,
            self._editor.scene_switcher_index,
            self._editor.scene_switcher_recent,
        )

    def refresh_scene_browser_rows(self) -> None:
        from engine.scene_index import build_scene_rows  # noqa: PLC0415

        self._editor._scene_browser_cached_rows = build_scene_rows(
            self._editor.scene_browser_query,
            self._editor.scene_switcher_recent,
        )

    def scene_browser_rows(self) -> list[Any]:
        if not self._editor._scene_browser_cached_rows:
            self.refresh_scene_browser_rows()
        return list(self._editor._scene_browser_cached_rows)

    def _set_scene_browser_query_preserve_selection(self, query: str) -> None:
        previous_scene_id: str | None = None
        rows_before = self.scene_browser_rows()
        prev_idx = int(getattr(self._editor, "scene_browser_index", 0) or 0)
        if 0 <= prev_idx < len(rows_before):
            previous_scene_id = str(getattr(rows_before[prev_idx], "scene_id", "") or "") or None

        self._editor.scene_browser_query = str(query or "")
        self.refresh_scene_browser_rows()

        if previous_scene_id:
            rows_after = self.scene_browser_rows()
            for idx, row in enumerate(rows_after):
                if str(getattr(row, "scene_id", "") or "") == previous_scene_id:
                    self._editor.scene_browser_index = idx
                    break

        self.scene_browser_clamp_index(len(self.scene_browser_rows()))

    def scene_browser_clamp_index(self, count: int) -> None:
        self._editor.scene_browser_index = clamp_scene_selection_index(
            self._editor.scene_browser_index, count
        )

    def scene_browser_window(self, count: int) -> tuple[int, int]:
        return compute_scene_window(self._editor.scene_browser_index, count)

    def scene_browser_layout(self, count: int) -> dict[str, float]:
        return compute_scene_browser_layout(
            float(self._editor.window.width),
            float(self._editor.window.height),
            count,
        )

    def scene_browser_lines(self) -> list[str]:
        rows = self.scene_browser_rows()
        self.scene_browser_clamp_index(len(rows))
        return build_scene_browser_lines(
            self._editor.scene_browser_active,
            self._editor.scene_browser_query,
            rows,
            self._editor.scene_browser_index,
        )

    def scene_switcher_open_selected(self) -> bool:
        options = self.scene_switcher_visible_options()
        if not options:
            return False
        self.scene_switcher_clamp_index(len(options))
        if self._editor.scene_switcher_index < 0:
            return False
        path, _label = options[self._editor.scene_switcher_index]
        return bool(self._editor._open_scene_by_id(path))

    def scene_browser_open_selected(self) -> bool:
        rows = self.scene_browser_rows()
        if not rows:
            return False
        self.scene_browser_clamp_index(len(rows))
        if self._editor.scene_browser_index < 0:
            return False
        row = rows[self._editor.scene_browser_index]
        return bool(self._editor._open_scene_by_id(row.scene_id))

    def scene_browser_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        if not self._editor.scene_browser_active:
            return False
        overlay = self._get_scene_browser_overlay()
        if apply_mouse_press(overlay, x, y, button=button, modifiers=0):
            return True
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        rows = self.scene_browser_rows()
        if not rows:
            return True
        layout = self.scene_browser_layout(len(rows))
        start_idx, end_idx = self.scene_browser_window(len(rows))
        visible = end_idx - start_idx

        hit_index = compute_scene_browser_hit_index(
            x, y, layout, start_idx, visible
        )
        if hit_index is not None:
            self._editor.scene_browser_index = hit_index
            self.scene_browser_open_selected()
        return True

    def handle_scene_browser_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
        if not self._editor.scene_browser_active:
            return False
        overlay = self._get_scene_browser_overlay()
        return apply_mouse_scroll(overlay, scroll_y, x=x, y=y, scroll_x=scroll_x)

    def handle_scene_switcher_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self._editor.scene_switcher_active:
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self._editor.scene_switcher_active = False
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            self._editor.scene_switcher_query = self._editor.scene_switcher_query[:-1]
            self.scene_switcher_clamp_index(len(self.scene_switcher_visible_options()))
            return True
        if key == optional_arcade.arcade.key.UP:
            self._editor.scene_switcher_index = max(0, self._editor.scene_switcher_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            count = len(self.scene_switcher_visible_options())
            if count:
                self._editor.scene_switcher_index = min(count - 1, self._editor.scene_switcher_index + 1)
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            return self.scene_switcher_open_selected()

        return True

    def handle_scene_browser_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self._editor.scene_browser_active:
            return False

        overlay = self._get_scene_browser_overlay()
        page_up_key = getattr(optional_arcade.arcade.key, "PAGE_UP", None)
        if page_up_key is None:
            page_up_key = getattr(optional_arcade.arcade.key, "PAGEUP", None)
        page_down_key = getattr(optional_arcade.arcade.key, "PAGE_DOWN", None)
        if page_down_key is None:
            page_down_key = getattr(optional_arcade.arcade.key, "PAGEDOWN", None)
        ctrl_n_key = getattr(optional_arcade.arcade.key, "N", None)
        ctrl_p_key = getattr(optional_arcade.arcade.key, "P", None)
        if modifiers & optional_arcade.arcade.key.MOD_CTRL:
            if ctrl_n_key is not None and key == ctrl_n_key:
                key = optional_arcade.arcade.key.DOWN
            elif ctrl_p_key is not None and key == ctrl_p_key:
                key = optional_arcade.arcade.key.UP
            elif key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                activator = getattr(overlay, "activate_selected", None)
                if callable(activator) and bool(activator()):
                    return True
                return self.scene_browser_open_selected()
        if key == optional_arcade.arcade.key.ESCAPE:
            self._editor.scene_browser_active = False
            return True
        if key == optional_arcade.arcade.key.TAB:
            toggle_focus = getattr(overlay, "toggle_focus", None)
            if callable(toggle_focus):
                toggle_focus()
                return True
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            if apply_backspace(overlay):
                return True
            self._set_scene_browser_query_preserve_selection(self._editor.scene_browser_query[:-1])
            return True
        if key in (
            optional_arcade.arcade.key.UP,
            optional_arcade.arcade.key.DOWN,
            optional_arcade.arcade.key.HOME,
            optional_arcade.arcade.key.END,
        ) or (page_up_key is not None and key == page_up_key) or (page_down_key is not None and key == page_down_key):
            apply_nav_key(overlay, key)
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            if apply_enter(overlay):
                return True
            return self.scene_browser_open_selected()

        return True

    def handle_scene_switcher_text_input(self, text: str) -> bool:
        if not self._editor.scene_switcher_active:
            return False
        if text and text.isprintable():
            self._editor.scene_switcher_query += text
            self.scene_switcher_clamp_index(len(self.scene_switcher_visible_options()))
            return True
        return False

    def handle_scene_browser_text_input(self, text: str) -> bool:
        if not self._editor.scene_browser_active:
            return False
        overlay = self._get_scene_browser_overlay()
        if apply_text_input(overlay, text):
            return True
        if text and text.isprintable():
            self._set_scene_browser_query_preserve_selection(self._editor.scene_browser_query + text)
            return True
        return False
