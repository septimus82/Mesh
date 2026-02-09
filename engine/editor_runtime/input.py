from __future__ import annotations

from typing import TYPE_CHECKING

from .editor_input_dispatch import handle_input as handle_input
from .editor_input_menu_handlers import (
    handle_context_menu_motion,
    handle_menu_bar_motion,
    _execute_context_menu_item,
    _focus_camera_on_entity,
    _begin_context_rename,
)
from .editor_input_drag_handlers import (
    handle_mouse_drag as handle_mouse_drag,
    handle_mouse_release as handle_mouse_release,
)
from .editor_input_click_handlers import handle_mouse_click as handle_mouse_click
from .editor_input_text_handlers import handle_text_input as handle_text_input
from .editor_input_shortcut_handlers import (
    get_active_shortcut_scopes as _get_active_shortcut_scopes,
    get_focus_snapshot as _get_focus_snapshot,
    handle_editor_action_shortcut as _handle_editor_action_shortcut,
    is_text_input_active as _is_text_input_active,
)

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController

from ..logging_tools import get_logger
logger = get_logger(__name__)
_shortcut_conflicts_warned: set[str] = set()




