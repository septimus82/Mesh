from __future__ import annotations

from typing import Any

from engine.editor.state import TOOL_MODE_MOVE, TOOL_MODE_PATH, TOOL_MODE_ZONE
from engine.logging_tools import get_logger

logger = get_logger(__name__)


class EditorToolController:
    """Encapsulates editor tool mode toggles."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def cycle_tool_mode(self) -> None:
        modes = [TOOL_MODE_MOVE, TOOL_MODE_PATH, TOOL_MODE_ZONE]
        try:
            idx = modes.index(self._editor.tool_mode)
            self._editor.tool_mode = modes[(idx + 1) % len(modes)]
        except ValueError:
            self._editor.tool_mode = TOOL_MODE_MOVE
        logger.info("[Editor] Tool Mode: %s", self._editor.tool_mode)
        self._editor.selected_waypoint_index = -1
