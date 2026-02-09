from typing import Callable, List, Optional
from engine.optional_arcade import arcade
from typing import TYPE_CHECKING
from engine.editor.confirm_modal_window_model import clamp_scroll, slice_lines

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

class EditorConfirmModalController:
    """
    Controller for the generic Confirm Modal.
    Manages the input and state (title, lines, callbacks) of the modal overlay.
    """
    def __init__(self, controller: 'EditorModeController') -> None:
        self.controller = controller
        self.title: str = "Confirm"
        self._all_message_lines: List[str] = []
        self.details_expanded: bool = False
        self.scroll_y: int = 0
        self._on_confirm: Optional[Callable[[], None]] = None
        self._on_cancel: Optional[Callable[[], None]] = None
        
        # Display settings
        self.compact_rows = 18
        self.expanded_rows = 35

    @property
    def visible_rows_count(self) -> int:
        return self.expanded_rows if self.details_expanded else self.compact_rows

    @property
    def message_lines(self) -> List[str]:
        """Return windowed lines based on scroll state."""
        visible, start_idx = slice_lines(
            self._all_message_lines, 
            self.scroll_y, 
            self.visible_rows_count
        )
        
        # Add scroll indicators if needed
        # (Though scrollbar UI is preferred, here we just return text content)
        # We can append status footer line if we want:
        # visible.append(f"Line {start_idx}-{start_idx+len(visible)} of {len(self._all_message_lines)}")
        
        return visible

    def request_confirmation(self, 
                             title: str, 
                             message_lines: List[str], 
                             on_confirm: Callable[[], None], 
                             on_cancel: Callable[[], None]) -> None:
        """Setup the modal with data and open it."""
        self.title = title
        self._all_message_lines = message_lines
        self.details_expanded = False # Reset state
        self.scroll_y = 0
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        
        panels = getattr(self.controller, "panels", None)
        if panels and hasattr(panels, "open_confirm_modal"):
            panels.open_confirm_modal()
        elif hasattr(self.controller, "ui_layers"):
            self.controller.ui_layers.push_modal("confirm_modal")

    def handle_input(self, key: int, modifiers: int) -> bool:
        """Handle input for the modal (Enter/Esc/D/Nav)."""
        if key == arcade.key.ENTER:
            self.execute_confirm()
            return True
        elif key == arcade.key.ESCAPE:
            self.execute_cancel()
            return True
        elif key == arcade.key.D:
            self.details_expanded = not self.details_expanded
            # Re-clamp scroll if viewport shrank
            self._clamp_scroll()
            return True
        elif key == arcade.key.UP:
            self.scroll_y -= 1
            self._clamp_scroll()
            return True
        elif key == arcade.key.DOWN:
            self.scroll_y += 1
            self._clamp_scroll()
            return True
        elif key == arcade.key.PAGE_UP:
            self.scroll_y -= self.visible_rows_count
            self._clamp_scroll()
            return True
        elif key == arcade.key.PAGE_DOWN:
            self.scroll_y += self.visible_rows_count
            self._clamp_scroll()
            return True
        elif key == arcade.key.HOME:
            self.scroll_y = 0
            self._clamp_scroll()
            return True
        elif key == arcade.key.END:
            self.scroll_y = len(self._all_message_lines)
            self._clamp_scroll()
            return True
        
        # Block all other input
        return True

    def _clamp_scroll(self) -> None:
        self.scroll_y = clamp_scroll(
            self.scroll_y, 
            len(self._all_message_lines), 
            self.visible_rows_count
        )


    def execute_confirm(self) -> None:
        """Run confirm callback and close modal."""
        if self._on_confirm:
            self._on_confirm()
        self.close()

    def execute_cancel(self) -> None:
        """Run cancel callback and close modal."""
        if self._on_cancel:
            self._on_cancel()
        self.close()

    def close(self) -> None:
        """Close the modal without triggering actions."""
        panels = getattr(self.controller, "panels", None)
        if panels and hasattr(panels, "close_confirm_modal"):
            panels.close_confirm_modal()
        elif hasattr(self.controller, "ui_layers"):
            self.controller.ui_layers.pop_modal("confirm_modal")
        # Cleanup references
        self._on_confirm = None
        self._on_cancel = None
