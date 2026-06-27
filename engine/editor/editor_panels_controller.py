from __future__ import annotations

from typing import Any

from engine.editor_ui_layer_stack_controller import EditorUiLayerStackController


class EditorPanelsController:
    """Owns editor panel/modal wiring and UI layer registration."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        # Modal/panel visibility state (mirrors UI layer stack)
        self.command_palette_open: bool = False
        self.context_menu_open: bool = False
        self.project_context_menu_open: bool = False
        self.keybinds_open: bool = False
        self.confirm_modal_open: bool = False
        self._panel_visibility: dict[str, bool] = {}
        self.ui_layers = EditorUiLayerStackController(editor)
        editor.ui_layers = self.ui_layers
        self._register_layers()

    def _set_modal_visible(self, modal_id: str, visible: bool) -> None:
        self._set_modal_state(modal_id, visible)
        if visible:
            self.ui_layers.push_modal(modal_id)
        else:
            self.ui_layers.pop_modal(modal_id)

    def _set_modal_state(self, modal_id: str, visible: bool) -> None:
        if modal_id == "command_palette":
            self.command_palette_open = visible
        elif modal_id == "context_menu":
            self.context_menu_open = visible
        elif modal_id == "project_context_menu":
            self.project_context_menu_open = visible
        elif modal_id == "keybinds":
            self.keybinds_open = visible
        elif modal_id == "confirm_modal":
            self.confirm_modal_open = visible

    def _sync_modal_state(self, modal_id: str) -> bool:
        visible = bool(self.ui_layers.is_visible(modal_id))
        self._set_modal_state(modal_id, visible)
        return visible

    def is_command_palette_open(self) -> bool:
        return self._sync_modal_state("command_palette")

    def open_command_palette(self) -> None:
        self._set_modal_visible("command_palette", True)
        session = getattr(self._editor, "session", None)
        if session is not None:
            setter = getattr(session, "set_command_palette_focused", None)
            if callable(setter):
                setter(True)

    def close_command_palette(self) -> None:
        self._set_modal_visible("command_palette", False)
        session = getattr(self._editor, "session", None)
        if session is not None:
            setter = getattr(session, "set_command_palette_focused", None)
            if callable(setter):
                setter(False)

    def toggle_command_palette(self) -> bool:
        if self.is_command_palette_open():
            self.close_command_palette()
            return False
        self.open_command_palette()
        return True

    def is_context_menu_open(self) -> bool:
        return self._sync_modal_state("context_menu")

    def open_context_menu(self) -> None:
        self._set_modal_visible("context_menu", True)

    def close_context_menu(self) -> None:
        self._set_modal_visible("context_menu", False)

    def is_project_context_menu_open(self) -> bool:
        return self._sync_modal_state("project_context_menu")

    def open_project_context_menu(self) -> None:
        self._set_modal_visible("project_context_menu", True)

    def close_project_context_menu(self) -> None:
        self._set_modal_visible("project_context_menu", False)

    def is_keybinds_visible(self) -> bool:
        return self._sync_modal_state("keybinds")

    def open_keybinds(self) -> None:
        keybinds = getattr(self._editor, "keybinds", None)
        if keybinds:
            keybinds.open()
        self._set_modal_visible("keybinds", True)

    def close_keybinds(self) -> None:
        keybinds = getattr(self._editor, "keybinds", None)
        if keybinds:
            keybinds.close()
        self._set_modal_visible("keybinds", False)

    def toggle_keybinds(self) -> bool:
        if self.is_keybinds_visible():
            self.close_keybinds()
            return False
        self.open_keybinds()
        return True

    def is_confirm_modal_visible(self) -> bool:
        return self._sync_modal_state("confirm_modal")

    def open_confirm_modal(self) -> None:
        self._set_modal_visible("confirm_modal", True)

    def close_confirm_modal(self) -> None:
        self._set_modal_visible("confirm_modal", False)

    def set_panel_visible(self, panel_id: str, visible: bool) -> None:
        if self.ui_layers.is_visible(panel_id) == visible:
            return
        self.ui_layers.toggle_layer(panel_id)
        self._panel_visibility[panel_id] = visible

    def _register_layers(self) -> None:
        editor = self._editor

        # Core modals
        self.ui_layers.register_layer("command_palette", "modal", z=1000, blocks_input=True)
        self._panel_visibility["command_palette"] = False

        from engine.editor.editor_keybinds_controller import EditorKeybindsController

        editor.keybinds = EditorKeybindsController(editor)
        self.ui_layers.register_layer(
            "keybinds",
            "modal",
            z=1500,
            blocks_input=True,
            input_handler=editor.keybinds.handle_input,
            text_handler=editor.keybinds.on_text,
            draw_handler=lambda _: getattr(editor, "keybinds_overlay", None) and editor.keybinds_overlay.draw(),
        )
        self._panel_visibility["keybinds"] = False

        self.ui_layers.register_layer("context_menu", "modal", z=2000, blocks_input=True)
        self._panel_visibility["context_menu"] = False

        from engine.ui_overlays.project_explorer_context_menu_overlay import (
            ProjectExplorerContextMenuOverlay,
        )

        editor.project_context_menu_overlay = ProjectExplorerContextMenuOverlay(editor.window)
        self.ui_layers.register_layer(
            "project_context_menu",
            "modal",
            z=2000,
            blocks_input=True,
            input_handler=editor._handle_context_menu_input,
            draw_handler=lambda _: editor.project_context_menu_overlay.draw(),
        )
        self._panel_visibility["project_context_menu"] = False

        from engine.editor.editor_confirm_modal_controller import EditorConfirmModalController
        from engine.ui_overlays.confirm_modal_overlay import ConfirmModalOverlay

        editor.confirm_modal = EditorConfirmModalController(editor)
        editor.confirm_modal_overlay = ConfirmModalOverlay(editor.window)
        self.ui_layers.register_layer(
            "confirm_modal",
            "modal",
            z=2500,
            blocks_input=True,
            input_handler=editor.confirm_modal.handle_input,
            draw_handler=lambda _: editor.confirm_modal_overlay.draw(
                editor.confirm_modal.title,
                editor.confirm_modal.message_lines,
            ),
        )
        self._panel_visibility["confirm_modal"] = False

        # Panels & overlays
        from engine.ui_overlays.keybinds_overlay import KeybindsOverlay

        editor.keybinds_overlay = KeybindsOverlay(editor.window)
        editor.keybinds_overlay.visible = True  # Modal layer controls visibility via stack

        self.ui_layers.register_layer("project_explorer", "panel", z=10)
        self.ui_layers.register_layer("problems", "panel", z=10)
        self.ui_layers.register_layer("inspector", "panel", z=10)
        self.ui_layers.register_layer("outliner", "panel", z=10)
        self.ui_layers.register_layer("history", "panel", z=10)
        self.ui_layers.register_layer("ai_proposals", "panel", z=10)
        self.ui_layers.register_layer("prefab_variant", "panel", z=10)
        self.ui_layers.register_layer("debug", "panel", z=10)
        self.ui_layers.register_layer("tooltips", "overlay", z=500)
        for panel_id in (
            "project_explorer",
            "problems",
            "inspector",
            "outliner",
            "history",
            "ai_proposals",
            "prefab_variant",
            "debug",
            "tooltips",
        ):
            self._panel_visibility[panel_id] = False

    def draw_panels(self) -> None:
        self.ui_layers.draw_all()

    def dispatch_input(self, key: int, modifiers: int) -> bool:
        return self.ui_layers.dispatch_input(key, modifiers)

    def dispatch_text(self, text: str) -> bool:
        return self.ui_layers.dispatch_text(text)
