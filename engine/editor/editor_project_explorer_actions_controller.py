from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.editor.editor_dock_query import get_dock_snapshot, get_effective_dock_widths
from engine.i18n import tr


class EditorProjectExplorerActionsController:
    """Coordinates Project Explorer actions and input handling.

    Keeps EditorController slim by owning project-explorer orchestration while
    delegating storage/selection to ProjectExplorerController.
    """

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def refresh_rows(self) -> None:
        self._editor.project_explorer.refresh_tree()

    def ensure_project_tab(self) -> None:
        dock_ctl = getattr(self._editor, "dock", None)
        setter = getattr(dock_ctl, "apply_tab_change", None) if dock_ctl is not None else None
        if callable(setter):
            setter(self._editor, "left", "Project")

    def reveal_path(self, path: str, viewport_height: int = 400, row_height: int = 20) -> bool:
        """Reveal a path in the Project Explorer list."""
        self.ensure_project_tab()
        return bool(self._editor.project_explorer.reveal_path(path, viewport_height, row_height))

    def delete_selected_paths_if_active(self) -> bool:
        snapshot = get_dock_snapshot(self._editor)
        if not self._editor.active or snapshot is None or snapshot.left_tab != "Project":
            return False
        paths = self._editor.project_explorer.selected_paths(self._editor._project_explorer_selectable_rows())
        if not paths:
            return False
        self._editor._file_ops_ctl.delete_selected_paths(paths)
        return True

    def get_display_rows(self) -> list[Any]:
        self._editor.project_explorer.ensure_rows()
        return list(getattr(self._editor.project_explorer, "cached_rows", []) or [])

    def get_selectable_rows(self) -> list[Any]:
        self._editor.project_explorer.ensure_rows()
        return list(getattr(self._editor.project_explorer, "selectable_rows", []) or [])

    def activate_selected(self) -> bool:
        from engine.editor.project_explorer_model import (  # noqa: PLC0415
            activation_intent_for_display_row,
        )

        row = self._editor.project_explorer.get_selected_row()
        if row is None:
            return False

        recent = getattr(row, "recent", None)
        entry = getattr(row, "entry", None)
        intent = activation_intent_for_display_row(row)
        kind = intent.get("kind")
        if kind == "clear_recents":
            return self.clear_recents()
        if kind == "open_scene":
            handled = bool(self._editor._open_scene_by_id(str(intent.get("scene_id", ""))))
            if handled and entry is not None:
                self.push_recent("scene", entry.rel_path, entry.name)
            elif handled and recent is not None:
                self.push_recent(recent.kind, recent.rel_path, recent.label)
            return handled
        if kind == "spawn_asset":
            handled = bool(self._editor._spawn_find_asset(str(intent.get("asset_path", ""))))
            if handled and entry is not None:
                self.push_recent("asset", entry.rel_path, entry.name)
            elif handled and recent is not None:
                self.push_recent(recent.kind, recent.rel_path, recent.label)
            return handled
        if kind == "copy_path":
            handled = bool(self._editor._copy_find_asset_path(str(intent.get("path", ""))))
            if handled and entry is not None:
                self.push_recent("path", entry.rel_path, entry.name)
            elif handled and recent is not None:
                self.push_recent(recent.kind, recent.rel_path, recent.label)
            return handled
        return True

    def handle_input(self, key: int, modifiers: int) -> bool:
        snapshot = get_dock_snapshot(self._editor)
        if not self._editor.active or snapshot is None or snapshot.left_tab != "Project":
            return False

        # Inline rename mode: consume all keys here (special keys handled via
        # scoped shortcuts in input.py, other keys should not fall through)
        if self._editor.project_explorer.inline_rename_active:
            # Non-special keys are consumed but not processed (text input via on_text)
            return True

        # Ensure rows populated
        if not self._editor.project_explorer.selectable_rows:
            self._editor.project_explorer.ensure_rows()

        if not self._editor.project_explorer.selectable_rows:
            return True

        if self._editor.search.is_panel_search_focused("project"):
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor.search.backspace_search_text()
                return True

        if key == optional_arcade.arcade.key.UP:
            extend = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
            self._editor.project_explorer.move_selection(-1, extend=extend)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            extend = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
            self._editor.project_explorer.move_selection(1, extend=extend)
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            return self.activate_selected()
        return True

    def handle_mouse_click(self, x: float, y: float, button: int, modifiers: int) -> bool:
        snapshot = get_dock_snapshot(self._editor)
        if not self._editor.active or snapshot is None or snapshot.left_tab != "Project":
            return False

        from engine.editor.editor_shell_layout import (  # noqa: PLC0415
            compute_editor_shell_layout,
        )
        from engine.editor.project_explorer_model import (  # noqa: PLC0415
            PROJECT_LINE_HEIGHT,
            compute_project_explorer_hit_index,
            compute_project_explorer_layout,
            compute_project_window,
            display_index_from_selectable_index,
            selectable_index_from_display_index,
        )

        window_w = int(getattr(self._editor.window, "width", 1280) or 1280)
        window_h = int(getattr(self._editor.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(self._editor, window_w)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.left_dock
        if not dock.contains_point(x, y):
            return False

        panel = compute_project_explorer_layout(dock)
        if not panel.list_rect.contains_point(x, y):
            return True

        # Existing behavior: Left click ignored if search focus is active
        if self._editor.search.is_panel_search_focused("project") and button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        if button not in (optional_arcade.arcade.MOUSE_BUTTON_LEFT, optional_arcade.arcade.MOUSE_BUTTON_RIGHT):
            return True

        display_rows = self.get_display_rows()
        selectable_rows = self.get_selectable_rows()
        if not display_rows:
            return True

        visible_capacity = int(panel.list_rect.height / PROJECT_LINE_HEIGHT)

        display_selected = display_index_from_selectable_index(
            display_rows,
            self._editor.project_explorer.selected_index,
        )
        display_index = display_selected if display_selected is not None else 0
        start_idx, visible = compute_project_window(
            display_index,
            len(display_rows),
            visible_capacity,
        )
        hit_index = compute_project_explorer_hit_index(
            y,
            panel.list_rect,
            start_idx,
            visible,
        )
        if hit_index is not None:
            selectable_index = selectable_index_from_display_index(display_rows, hit_index)
            if selectable_index is None:
                return True
            if selectable_index < len(selectable_rows):
                if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
                    ctrl = bool(modifiers & optional_arcade.arcade.key.MOD_CTRL)
                    shift = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
                    self._editor.project_explorer.handle_click(selectable_index, ctrl=ctrl, shift=shift)
                elif button == optional_arcade.arcade.MOUSE_BUTTON_RIGHT:
                    # Select immediately on right click (simplification)
                    self._editor.project_explorer.handle_click(selectable_index, ctrl=False, shift=False)
                    self.open_context_menu(int(x), int(y))
            return True

        return True

    def open_context_menu(self, x: int, y: int) -> None:
        from engine.editor.shortcut_resolver_model import (  # noqa: PLC0415
            SHORTCUT_SCOPE_GLOBAL,
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
        )
        self._editor.project_explorer.open_context_menu(
            x,
            y,
            self._editor,
            active_scopes=(SHORTCUT_SCOPE_PROJECT_EXPLORER, SHORTCUT_SCOPE_GLOBAL),
        )

    def open_context_menu_at_selection(self) -> None:
        snapshot = get_dock_snapshot(self._editor)
        if not self._editor.active or snapshot is None or snapshot.left_tab != "Project":
            return
        from engine.editor.editor_shell_layout import (  # noqa: PLC0415
            compute_editor_shell_layout,
        )
        from engine.editor.project_explorer_model import (  # noqa: PLC0415
            PROJECT_LINE_HEIGHT,
            compute_project_explorer_layout,
            compute_project_window,
            display_index_from_selectable_index,
        )
        from engine.editor.shortcut_resolver_model import (  # noqa: PLC0415
            SHORTCUT_SCOPE_GLOBAL,
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
        )

        window_w = int(getattr(self._editor.window, "width", 1280) or 1280)
        window_h = int(getattr(self._editor.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(self._editor, window_w)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.left_dock
        panel = compute_project_explorer_layout(dock)

        display_rows = self.get_display_rows()
        if not display_rows:
            return
        display_selected = display_index_from_selectable_index(
            display_rows,
            self._editor.project_explorer.selected_index,
        )
        display_index = display_selected if display_selected is not None else 0
        visible_capacity = int(panel.list_rect.height / PROJECT_LINE_HEIGHT)
        start_idx, visible = compute_project_window(
            display_index,
            len(display_rows),
            visible_capacity,
        )
        # Clamp within visible window
        local_index = max(0, min(display_index - start_idx, max(0, visible - 1)))
        row_top = panel.list_rect.top - (local_index * PROJECT_LINE_HEIGHT)
        x = int(panel.list_rect.left)
        y = int(row_top - PROJECT_LINE_HEIGHT)

        self._editor.project_explorer.open_context_menu(
            x,
            y,
            self._editor,
            active_scopes=(SHORTCUT_SCOPE_PROJECT_EXPLORER, SHORTCUT_SCOPE_GLOBAL),
        )

    def activate_recent(self, recent: Any) -> bool:
        kind = str(getattr(recent, "kind", "") or "")
        rel_path = str(getattr(recent, "rel_path", "") or "")
        if kind == "scene":
            return bool(self._editor._open_scene_by_id(rel_path))
        if kind == "asset":
            return bool(self._editor._spawn_find_asset(rel_path))
        if kind == "path":
            return bool(self._editor._copy_find_asset_path(rel_path))
        return False

    def push_recent(self, kind: str, rel_path: str, label: str) -> None:
        from engine.editor.project_explorer_model import ProjectExplorerRecentItem  # noqa: PLC0415

        item = ProjectExplorerRecentItem(
            kind=str(kind),
            rel_path=str(rel_path),
            label=str(label),
        )
        self._editor.project_explorer.push_recent_item(item)
        self._editor._autosave_workspace()

    def get_recent_payloads(self) -> list[dict[str, Any]]:
        payload = self._editor.project_explorer.get_recents_payload()
        return list(payload) if isinstance(payload, list) else []

    def clear_recents(self) -> bool:
        if not self._editor.project_explorer.recents:
            hud = getattr(self._editor.window, "player_hud", None)
            toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
            if callable(toaster):
                toaster(tr("UI_NO_RECENTS"), seconds=2.5)
            # Return True because we handled the input (by showing a warning), preventing fallback
            return True

        self._editor.project_explorer.clear_recents()
        self._editor._autosave_workspace()

        hud = getattr(self._editor.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster(tr("UI_RECENTS_CLEARED"), seconds=2.5)
        return True

    def reveal_in_explorer(self, target_path: str) -> bool:
        """Reveal a file path in the Project Explorer panel."""
        from engine.editor.project_explorer_model import PROJECT_LINE_HEIGHT  # noqa: PLC0415

        # Switch to Project tab
        self._editor.dock.set_left_tab("Project", force=True)

        window_h = int(getattr(self._editor.window, "height", 720) or 720)
        # Approximate viewport height (dock space)
        viewport_h = max(300, window_h - 100)

        return bool(self._editor.project_explorer.reveal_path(
            target_path=target_path,
            viewport_height=viewport_h,
            row_height=PROJECT_LINE_HEIGHT,
        ))

    def reveal_current_in_explorer(self) -> bool:
        """Reveal the current scene or selected entity asset in Project Explorer."""
        from engine.editor.project_explorer_reveal_model import choose_reveal_target  # noqa: PLC0415

        scene_path = self.get_current_scene_path()
        entity_asset_path = self.get_selected_entity_asset_path()

        target = choose_reveal_target(scene_path, entity_asset_path)
        if not target:
            hud = getattr(self._editor.window, "player_hud", None)
            toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
            if callable(toaster):
                toaster(tr("UI_NO_REVEAL_TARGET"), seconds=2.5)
            return False

        return self.reveal_in_explorer(target)

    def get_current_scene_path(self) -> str | None:
        """Get the path of the currently loaded scene."""
        scene_controller = getattr(self._editor.window, "scene_controller", None)
        if scene_controller is None:
            return None
        scene_path = getattr(scene_controller, "current_scene_path", None)
        return scene_path if isinstance(scene_path, str) else None

    def get_selected_entity_asset_path(self) -> str | None:
        """Get the sprite/asset path of the selected entity."""
        entity_json = self._editor._get_selected_entity_json_for_inspector()
        if entity_json is None:
            return None

        # Check for sprite path
        sprite_path = entity_json.get("sprite")
        if isinstance(sprite_path, str) and sprite_path.strip():
            return sprite_path

        # Check for sprite_sheet image
        sprite_sheet = entity_json.get("sprite_sheet")
        if isinstance(sprite_sheet, dict):
            image_path = sprite_sheet.get("image")
            if isinstance(image_path, str) and image_path.strip():
                return image_path

        return None

    def copy_selected_path(self) -> bool:
        """Copy the selected Project Explorer row path to clipboard."""
        return bool(self._editor._file_ops_ctl.copy_selected_path())

    def try_copy_to_os_clipboard(self, text: str) -> None:
        """Attempt to copy text to OS clipboard. Safe no-op if unavailable."""
        try:
            import pyperclip  # noqa: PLC0415

            pyperclip.copy(text)
        except Exception:  # noqa: BLE001
            # Clipboard not available (headless, web, missing deps) - silent no-op
            pass

    def safe_rename_selected_asset(self, new_name: str) -> bool:
        """Rename the selected Project Explorer asset and update scene references."""
        return bool(self._editor._file_ops_ctl.rename_selected_asset(new_name))

    def safe_move_selected_asset(self, dest_folder_rel: str) -> bool:
        """Move the selected Project Explorer asset and update scene references."""
        return bool(self._editor._file_ops_ctl.move_selected_asset(dest_folder_rel))

    def safe_move_selected_assets(self, dest_folder_rel: str) -> bool:
        """Move multiple selected assets and update references."""
        paths = self._editor.project_explorer.selected_paths(self.get_selectable_rows())
        if not paths:
            return False
        from engine.editor.asset_move_model import compute_move_paths  # noqa: PLC0415

        old_paths = sorted(paths)
        new_paths: list[str] = []
        for old_rel in old_paths:
            _, new_rel = compute_move_paths(old_rel, dest_folder_rel)
            new_paths.append(new_rel)

        result = bool(self._editor._file_ops_ctl.move_selected_paths_to_folder(old_paths, dest_folder_rel))
        if result:
            self._editor.project_explorer.apply_post_move_selection(
                old_paths,
                new_paths,
                self._editor.project_explorer.primary_path(),
            )
        return result

    def prompt_move_destination(self, on_confirm) -> bool:
        """Prompt for destination folder and call on_confirm with selected path."""
        handler = getattr(self._editor.window, "project_explorer_move_prompt", None)
        if callable(handler):
            return bool(handler(on_confirm))
        hud = getattr(self._editor.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster("Safe Move: Select specific folder logic pending UI", seconds=2.5)
        return False

    def get_selected_project_entry_path(self) -> str | None:
        """Get the relative path of the selected Project Explorer entry."""
        path = self._editor.project_explorer.primary_path(self.get_selectable_rows())
        return path if isinstance(path, str) else None
