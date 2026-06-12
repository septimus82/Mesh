from __future__ import annotations

from typing import Any, List

import engine.optional_arcade as optional_arcade
from engine.editor.find_everything_model import build_find_items
from engine.editor_commands import get_all_commands
from engine.editor_entity_ops import list_entities
from engine.scene_index import build_scene_rows
from engine.swallowed_exceptions import _log_swallow
from engine.ui_overlays.widget_overlay_helpers import (
    apply_backspace,
    apply_enter,
    apply_mouse_press,
    apply_mouse_scroll,
    apply_nav_key,
    apply_text_input,
)


class EditorSearchController:
    """Encapsulates command palette + find everything flows."""

    def __init__(self, editor: Any, ui_flow: Any) -> None:
        self._editor = editor
        self._ui_flow = ui_flow
        self._command_palette_query: str = ""
        self._command_palette_index: int = 0
        self._outliner_search: str = ""
        self._assets_search: str = ""
        self._search_focus: str | None = None

    @property
    def command_palette_query(self) -> str:
        return self._command_palette_query

    @command_palette_query.setter
    def command_palette_query(self, value: str) -> None:
        self._command_palette_query = str(value or "")

    @property
    def command_palette_index(self) -> int:
        return self._command_palette_index

    @command_palette_index.setter
    def command_palette_index(self, value: int) -> None:
        self._command_palette_index = int(value or 0)

    def clear_command_palette_state(self) -> None:
        self._command_palette_query = ""
        self._command_palette_index = 0

    def get_command_palette_state(self) -> tuple[str, int]:
        return (self._command_palette_query, int(self._command_palette_index))

    def append_command_palette_text(self, text: str) -> bool:
        if not text or not text.isprintable():
            return False
        self._command_palette_query = f"{self._command_palette_query}{text}"
        self._command_palette_index = 0
        return True

    def backspace_command_palette(self) -> bool:
        if not self._command_palette_query:
            return False
        self._command_palette_query = self._command_palette_query[:-1]
        self._command_palette_index = 0
        return True

    def move_command_palette_selection(self, delta: int) -> None:
        idx = int(self._command_palette_index or 0)
        self._command_palette_index = max(0, idx + int(delta))

    def get_search_focus(self) -> str | None:
        return self._search_focus

    def is_search_focused(self) -> bool:
        return self._search_focus in ("project", "outliner", "assets", "history", "problems", "debug")

    def is_panel_search_focused(self, panel: str) -> bool:
        return self._search_focus == panel

    def focus_search_for_active_panel(self) -> bool:
        if not getattr(self._editor, "active", False):
            return False
        panel = self._resolve_active_search_panel()
        if panel is None:
            return False
        self._search_focus = panel
        self._editor.entity_panels_filter_active = panel == "outliner"
        return True

    def clear_search_focus(self) -> None:
        self._search_focus = None
        self._editor.entity_panels_filter_active = False

    def get_active_panel_search_text(self) -> str:
        panel = self._resolve_active_search_panel()
        if panel is None:
            return ""
        return self._get_search_text_for_panel(panel)

    def set_active_panel_search_text(self, new_text: str) -> bool:
        panel = self._resolve_active_search_panel()
        if panel is None:
            return False
        self._set_search_text_for_panel(panel, new_text)
        return True

    def clear_search_for_active_panel(self) -> bool:
        panel = self._search_focus
        if panel is None:
            return False
        current = self._get_search_text_for_panel(panel)
        if not current:
            return False
        self._set_search_text_for_panel(panel, "")
        return True

    def append_search_text(self, text: str) -> bool:
        panel = self._search_focus
        if panel is None:
            return False
        if not text or not text.isprintable():
            return False
        current = self._get_search_text_for_panel(panel)
        self._set_search_text_for_panel(panel, current + text)
        return True

    def backspace_search_text(self) -> bool:
        panel = self._search_focus
        if panel is None:
            return False
        current = self._get_search_text_for_panel(panel)
        if not current:
            return False
        self._set_search_text_for_panel(panel, current[:-1])
        return True

    def get_outliner_search(self) -> str:
        return self._outliner_search

    def set_outliner_search(self, value: str, *, autosave: bool = True) -> None:
        text = str(value or "")
        if text == self._outliner_search:
            return
        self._outliner_search = text
        self._editor.entity_panels_filter = text
        self._editor._refresh_entity_panels_list()
        if autosave:
            self._editor._autosave_workspace()

    def get_assets_search(self) -> str:
        return self._assets_search

    def set_assets_search(self, value: str) -> None:
        text = str(value or "")
        if text == self._assets_search:
            return
        self._assets_search = text

    def sync_search_focus(self) -> None:
        if self._search_focus is None:
            return
        if self._resolve_active_search_panel() != self._search_focus:
            self.clear_search_focus()

    def toggle_command_palette(self) -> bool:
        if not self._editor.active:
            return False
        opened = bool(self._editor.panels.toggle_command_palette())
        self.clear_command_palette_state()
        if opened:
            self.clear_search_focus()
        self._editor._autosave_workspace()
        try:
            from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

            save_editor_ui_state_for_editor(self._editor)
        except Exception:  # noqa: BLE001  # REASON: editor UI state persistence is best-effort and should not block search panel toggles
            _log_swallow("EDIT-001", "engine/editor/editor_search_controller.py pass-only blanket swallow")
            pass
        return bool(self._editor.panels.is_command_palette_open())

    def _resolve_active_search_panel(self) -> str | None:
        snapshot = self._editor.dock.get_snapshot()
        left_tab = snapshot.left_tab
        right_tab = snapshot.right_tab
        if left_tab == "Project":
            return "project"
        if left_tab == "Outliner" and self._editor.entity_panels_active:
            return "outliner"
        if right_tab == "Assets" and self._editor.asset_browser_active:
            return "assets"
        if right_tab == "History":
            return "history"
        if right_tab == "Problems":
            return "problems"
        if right_tab == "Debug":
            return "debug"
        return None

    def _get_search_text_for_panel(self, panel: str) -> str:
        if panel == "project":
            return str(self._editor.project_explorer.search_query or "")
        if panel == "outliner":
            return self._outliner_search
        if panel == "assets":
            return self._assets_search
        if panel == "history":
            return str(self._editor.history.get_search_text() or "")
        if panel == "problems":
            return str(self._editor.problems.query or "")
        if panel == "debug":
            debug_panels = getattr(self._editor, "debug_panels", None)
            if debug_panels is not None:
                return str(debug_panels.get_active_filter_text() or "")
        return ""

    def _set_search_text_for_panel(self, panel: str, new_text: str) -> None:
        value = str(new_text or "")
        if panel == "project":
            if value == self._editor.project_explorer.search_query:
                return
            self._editor.project_explorer.set_query(value)
            self._editor._autosave_workspace()
            return
        if panel == "outliner":
            self.set_outliner_search(value)
            return
        if panel == "assets":
            self._editor.set_asset_browser_filter(value)
            return
        if panel == "history":
            if self._editor.history.set_search_text(value):
                self._editor._autosave_workspace()
            return
        if panel == "problems":
            if value == self._editor.problems.query:
                return
            self._editor.problems.set_query(value)
            self._editor._autosave_workspace()
            return
        if panel == "debug":
            debug_panels = getattr(self._editor, "debug_panels", None)
            if debug_panels is not None:
                debug_panels.set_active_filter_text(value)
            return

    def ui_get_palette_items(self) -> List[Any]:
        # Support legacy test override
        override = self._editor._find_items_override
        if isinstance(override, list):
            return list(override)

        window = self._editor.window
        commands = get_all_commands(window) if window else []

        # Get recent scenes
        recents = self._editor.scene_switcher_recent
        scenes = build_scene_rows("", recents)

        # Get entities
        sc = getattr(window, "scene_controller", None)
        scene_data = getattr(sc, "_loaded_scene_data", None)
        entities = list_entities(scene_data) if isinstance(scene_data, dict) else []

        # Get assets
        assets: List[Any] = []
        if self._editor._asset_browser_cached_rows:
            assets = self._editor._asset_browser_cached_rows

        if not assets:
            repo_root = getattr(window, "repo_root", None)
            if repo_root:
                from engine.asset_index import scan_assets  # noqa: PLC0415

                assets = scan_assets(repo_root)

        # Get problems
        problems = self._ui_get_problems(scene_data, window)

        # Side effect: Update asset lookup (delegated state)
        # We must keep this populated as referencing code expects it via _find_asset_lookup
        if hasattr(self._ui_flow, "asset_lookup"):
            self._ui_flow.asset_lookup = {
                str(getattr(row, "rel_path", "") or ""): row
                for row in assets
                if str(getattr(row, "rel_path", "") or "")
            }

        return build_find_items(
            commands=commands,
            scenes=scenes,
            entities=entities,
            assets=assets,
            problems=problems,
        )

    def _ui_get_problems(self, scene_data: Any, window: Any) -> List[Any]:
        """Helper for palette items."""
        providers = getattr(self._editor, "providers", None)
        if providers is not None and hasattr(providers, "get_palette_problems"):
            return list(providers.get_palette_problems(scene_data, window))

        if self._editor.problems.issues:
            return list(self._editor.problems.issues)

        if not isinstance(scene_data, dict):
            return []

        from pathlib import Path  # noqa: PLC0415

        from engine.editor.scene_lint_model import build_scene_lint_issues  # noqa: PLC0415

        repo_root = getattr(window, "repo_root", None) if window else None
        if not isinstance(repo_root, Path):
            return []

        def resolver(prefab_id: str) -> bool:
            try:
                from engine.prefabs import get_prefab_manager  # noqa: PLC0415

                manager = get_prefab_manager()
                return bool(manager.get_prefab(prefab_id))
            except Exception:
                return False

        return build_scene_lint_issues(scene_data, repo_root, prefab_resolver=resolver)

    def toggle_find_everything(self) -> bool:
        if not self._editor.active:
            return False
        self._ui_flow.toggle_palette()
        return bool(self._ui_flow.is_open)

    def close_find_everything(self) -> None:
        self._ui_flow.close_palette(cancel_preview=True)

    def _get_find_everything_overlay(self) -> Any:
        window = getattr(self._editor, "window", None)
        if window is None:
            return None
        return getattr(window, "find_everything_overlay", None)

    def handle_find_everything_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:
        overlay = self._get_find_everything_overlay()
        return apply_mouse_press(overlay, x, y, button=button, modifiers=modifiers)

    def handle_find_everything_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
        overlay = self._get_find_everything_overlay()
        return apply_mouse_scroll(overlay, scroll_y, x=x, y=y, scroll_x=scroll_x)

    def handle_find_everything_input(self, key: int, modifiers: int) -> bool:
        if not self._editor.active or not self._editor._find_everything_open:
            return False
        if key in (optional_arcade.arcade.key.K, optional_arcade.arcade.key.J) and (
            modifiers & optional_arcade.arcade.key.MOD_CTRL
        ):
            self.close_find_everything()
            return True
        ctrl_n_key = getattr(optional_arcade.arcade.key, "N", None)
        ctrl_p_key = getattr(optional_arcade.arcade.key, "P", None)
        if modifiers & optional_arcade.arcade.key.MOD_CTRL:
            if ctrl_n_key is not None and key == ctrl_n_key:
                key = optional_arcade.arcade.key.DOWN
            elif ctrl_p_key is not None and key == ctrl_p_key:
                key = optional_arcade.arcade.key.UP
            elif key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                overlay = self._get_find_everything_overlay()
                activator = getattr(overlay, "activate_selected", None)
                if callable(activator) and bool(activator()):
                    return True
                self.activate_find_selection()
                return True
        if key == optional_arcade.arcade.key.ESCAPE:
            if self._editor._find_everything_query:
                # Clear query first (delegate to update_query)
                self._ui_flow.update_query("")
            else:
                self.close_find_everything()
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            self.backspace_find_query()
            return True
        if key == optional_arcade.arcade.key.TAB:
            overlay = self._get_find_everything_overlay()
            toggle_focus = getattr(overlay, "toggle_focus", None)
            if callable(toggle_focus):
                toggle_focus()
                return True
            return True
        if key == optional_arcade.arcade.key.UP:
            overlay = self._get_find_everything_overlay()
            if apply_nav_key(overlay, key):
                return True
            self.move_find_selection(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            overlay = self._get_find_everything_overlay()
            if apply_nav_key(overlay, key):
                return True
            self.move_find_selection(1)
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            overlay = self._get_find_everything_overlay()
            if apply_enter(overlay):
                return True
            self.activate_find_selection()
            return True
        return True

    def set_find_query(self, text: str) -> None:
        self._ui_flow.update_query(str(text or ""))

    def append_find_query_text(self, text: str) -> bool:
        if not text or not text.isprintable():
            return False
        overlay = self._get_find_everything_overlay()
        if apply_text_input(overlay, text):
            return True
        self._ui_flow.update_query(self._ui_flow.query + text)
        return True

    def backspace_find_query(self) -> bool:
        overlay = self._get_find_everything_overlay()
        if apply_backspace(overlay):
            return True
        if not self._ui_flow.query:
            return False
        self._ui_flow.update_query(self._ui_flow.query[:-1])
        return True

    def move_find_selection(self, delta: int) -> None:
        self._ui_flow.move_selection(delta)

    def activate_find_selection(self) -> bool:
        return bool(self._ui_flow.commit_selection())

    def refresh_find_everything_results(self) -> None:
        self._ui_flow._refresh_results()

    def build_find_everything_items(self) -> list[Any]:
        return list(self._ui_flow._build_items())

    def get_find_everything_problems(self) -> list[Any]:
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        return list(self._ui_flow._get_problems(scene, self._editor.window))
