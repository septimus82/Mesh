"""Controller for the Project Explorer context menu.

Manages state for the context menu (open/closed, position, items)
and handles input routing.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING, Tuple
from engine.editor.shortcut_resolver_model import SHORTCUT_SCOPE_GLOBAL, SHORTCUT_SCOPE_PROJECT_EXPLORER

if TYPE_CHECKING:
    from engine.game import GameWindow

class ProjectExplorerContextMenuController:
    """Controller for the Project Explorer context menu."""

    def __init__(self, window: GameWindow) -> None:
        self.window = window
        self.active: bool = False
        self.position: Tuple[int, int] = (0, 0)

    def open(self, x: int, y: int) -> None:
        """Open the context menu at the given coordinates."""
        editor = getattr(self.window, "editor_controller", None)
        if not editor:
            return
        project_ctrl = getattr(editor, "project_explorer", None)
        if not project_ctrl:
            return
        project_ctrl.open_context_menu(
            x,
            y,
            editor,
            active_scopes=(SHORTCUT_SCOPE_PROJECT_EXPLORER, SHORTCUT_SCOPE_GLOBAL),
        )
        self.active = True

    def close(self) -> None:
        """Close the context menu."""
        editor = getattr(self.window, "editor_controller", None)
        if not editor:
            return
        project_ctrl = getattr(editor, "project_explorer", None)
        if project_ctrl is None:
            return
        project_ctrl.close_context_menu(editor)
        self.active = False
    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Handle mouse move for hovering."""
        editor = getattr(self.window, "editor_controller", None)
        project_ctrl = getattr(editor, "project_explorer", None) if editor else None
        if project_ctrl is None:
            return False
        return bool(project_ctrl.handle_context_menu_mouse_move(x, y))

    def handle_mouse_press(self, x: float, y: float, button: int) -> bool:
        """Handle mouse press. 
        
        Returns:
            True to consume event (handled or closed), False to let it pass (shouldn't happen for modal).
        """
        editor = getattr(self.window, "editor_controller", None)
        project_ctrl = getattr(editor, "project_explorer", None) if editor else None
        if project_ctrl is None:
            return False
        return bool(project_ctrl.handle_context_menu_mouse_press(x, y, button, editor))

    def handle_key_press(self, key: int, modifiers: int) -> bool:
        """Handle key press (Esc to close)."""
        editor = getattr(self.window, "editor_controller", None)
        if editor is None:
            return False
        from engine.editor_runtime import editor_input_shortcut_handlers as shortcuts
        return bool(shortcuts.handle_editor_action_shortcut(editor, key, modifiers))

    def activate_item(self, index: int) -> None:
        """Run the action for the clicked item."""
        editor = getattr(self.window, "editor_controller", None)
        project_ctrl = getattr(editor, "project_explorer", None) if editor else None
        if project_ctrl is None:
            return
        if 0 <= index < len(project_ctrl.context_menu_items):
            project_ctrl.context_menu_index = index
            project_ctrl.activate_context_menu_item(editor)
