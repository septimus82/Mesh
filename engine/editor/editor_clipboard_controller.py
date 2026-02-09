"""Editor clipboard controller.

Extracted from editor_controller.py to encapsulate clipboard state and
copy/paste operations for entities.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, TYPE_CHECKING

from engine.logging_tools import get_logger

if TYPE_CHECKING:
    import engine.optional_arcade as optional_arcade

logger = get_logger(__name__)


class EditorClipboardController:
    """Encapsulates clipboard state and copy/paste operations."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        # Clipboard state (internal, not OS clipboard)
        self._entity_clipboard: Optional[Dict[str, Any]] = None
        self._entity_clipboard_source_id: Optional[str] = None
        self._hd2d_overrides_clipboard: Optional[Dict[str, Any]] = None

    @property
    def entity_clipboard(self) -> Optional[Dict[str, Any]]:
        """The currently copied entity data."""
        return self._entity_clipboard

    @entity_clipboard.setter
    def entity_clipboard(self, value: Optional[Dict[str, Any]]) -> None:
        self._entity_clipboard = value

    @property
    def entity_clipboard_source_id(self) -> Optional[str]:
        """The ID of the entity that was copied."""
        return self._entity_clipboard_source_id

    @entity_clipboard_source_id.setter
    def entity_clipboard_source_id(self, value: Optional[str]) -> None:
        self._entity_clipboard_source_id = value

    @property
    def hd2d_overrides_clipboard(self) -> Optional[Dict[str, Any]]:
        """The currently copied HD2D overrides."""
        return self._hd2d_overrides_clipboard

    @hd2d_overrides_clipboard.setter
    def hd2d_overrides_clipboard(self, value: Optional[Dict[str, Any]]) -> None:
        self._hd2d_overrides_clipboard = value

    def copy_selected_entity(self) -> None:
        """Copy the selected entity to the internal clipboard."""
        from engine.editor.editor_clipboard_ops import get_entity_id_from_data  # noqa: PLC0415

        editor = self._editor
        if not editor.active or editor.selected_entity is None:
            return

        entity_data = getattr(editor.selected_entity, "mesh_entity_data", None)
        if not isinstance(entity_data, dict):
            logger.info("[Editor] Cannot copy: missing entity data")
            return

        self._entity_clipboard = copy.deepcopy(entity_data)
        self._entity_clipboard_source_id = get_entity_id_from_data(entity_data)

        logger.info("[Editor] Copied entity: %s", self._entity_clipboard_source_id)

        # Toast feedback
        hud = getattr(editor.window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue(f"Copied: {self._entity_clipboard_source_id}")

    def paste_entity(
        self, spawn_world_xy: tuple[float, float] | None = None
    ) -> None:
        """Paste an entity from the internal clipboard.

        Args:
            spawn_world_xy: Optional position to spawn at. If None, uses camera center.
        """
        from engine.editor.editor_clipboard_ops import (  # noqa: PLC0415
            clone_entity_payload,
            collect_existing_entity_ids,
            generate_copy_entity_id,
        )

        editor = self._editor
        if not editor.active:
            return

        if self._entity_clipboard is None:
            logger.info("[Editor] Nothing to paste")
            hud = getattr(editor.window, "player_hud", None)
            if hud is not None:
                enqueue = getattr(hud, "enqueue_toast", None)
                if callable(enqueue):
                    enqueue("Nothing to paste")
            return

        # Get spawn position (camera center if not specified)
        if spawn_world_xy is None:
            camera_ctrl = getattr(editor.window, "camera_controller", None)
            if camera_ctrl is not None:
                camera = getattr(camera_ctrl, "camera", None)
                if camera is not None:
                    pos = getattr(camera, "position", None)
                    if pos is not None:
                        spawn_world_xy = (float(pos[0]), float(pos[1]))
            if spawn_world_xy is None:
                spawn_world_xy = (0.0, 0.0)

        # Generate unique ID
        existing_ids = collect_existing_entity_ids(editor.window.scene_controller.all_sprites)
        source_id = self._entity_clipboard_source_id or "entity"
        new_id = generate_copy_entity_id(existing_ids, source_id)

        # Clone entity with new ID and position
        new_entity_data = clone_entity_payload(self._entity_clipboard, new_id, spawn_world_xy)

        # Create entity
        new_sprite = editor._create_entity_internal(new_entity_data)
        if new_sprite:
            editor.selected_entity = new_sprite
            editor.shape.reset_zone_selection_state()
            editor.shape.sync_zone_selection_state(editor.selected_entity)
            logger.info("[Editor] Pasted entity: %s at (%.1f, %.1f)", new_id, spawn_world_xy[0], spawn_world_xy[1])

            # Push undo command
            editor._push_command({
                "type": "AddEntity",
                "entity_name": new_id,
                "data": new_entity_data,
            })

            # Toast feedback
            hud = getattr(editor.window, "player_hud", None)
            if hud is not None:
                enqueue = getattr(hud, "enqueue_toast", None)
                if callable(enqueue):
                    enqueue(f"Pasted: {new_id}")

    def has_entity_clipboard(self) -> bool:
        """Check if there's something in the entity clipboard."""
        return self._entity_clipboard is not None

    def clear_entity_clipboard(self) -> None:
        """Clear the entity clipboard."""
        self._entity_clipboard = None
        self._entity_clipboard_source_id = None
