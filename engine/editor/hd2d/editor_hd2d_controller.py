"""Editor HD2D controller.

Extracted from editor_controller.py to encapsulate HD2D preset preview,
commit, and auto-apply operations.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, TYPE_CHECKING

from engine.logging_tools import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class EditorHd2dController:
    """Encapsulates HD2D preset preview/commit operations."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        # HD-2D preset preview state (non-destructive preview while browsing)
        self._preview_active: bool = False
        self._preview_snapshot: Any = None  # PreviewSnapshot from hd2d_preset_preview_model
        self._preview_preset_id: str | None = None

    @property
    def preview_active(self) -> bool:
        """Whether HD2D preview is currently active."""
        return self._preview_active

    @preview_active.setter
    def preview_active(self, value: bool) -> None:
        self._preview_active = value

    @property
    def preview_snapshot(self) -> Any:
        """The preview snapshot for restoration."""
        return self._preview_snapshot

    @preview_snapshot.setter
    def preview_snapshot(self, value: Any) -> None:
        self._preview_snapshot = value

    @property
    def preview_preset_id(self) -> str | None:
        """The currently previewed preset ID."""
        return self._preview_preset_id

    @preview_preset_id.setter
    def preview_preset_id(self, value: str | None) -> None:
        self._preview_preset_id = value

    def preview_preset(self, preset_id: str) -> bool:
        """Begin or update HD-2D preset preview without marking dirty or pushing undo.

        Args:
            preset_id: The preset to preview (e.g., "soft", "crisp").

        Returns:
            True if preview was applied.
        """
        from .hd2d_preset_preview_model import (  # noqa: PLC0415
            begin_preset_preview,
            update_preset_preview,
        )

        editor = self._editor
        sc = getattr(editor.window, "scene_controller", None)
        if sc is None:
            return False
        scene = getattr(sc, "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return False

        if self._preview_active and self._preview_snapshot is not None:
            # Already previewing - update to new preset
            if self._preview_preset_id == preset_id:
                return True  # Same preset, nothing to do
            new_scene = update_preset_preview(scene, preset_id, self._preview_snapshot)
        else:
            # Start new preview
            new_scene, snapshot = begin_preset_preview(scene, preset_id)
            self._preview_snapshot = snapshot
            self._preview_active = True

        self._preview_preset_id = preset_id
        sc._loaded_scene_data = new_scene
        return True

    def cancel_preview(self) -> None:
        """Cancel active HD2D preview and restore original settings.

        Does NOT mark dirty or push undo - this is non-destructive.
        """
        if not self._preview_active or self._preview_snapshot is None:
            self._preview_active = False
            self._preview_snapshot = None
            self._preview_preset_id = None
            return

        from .hd2d_preset_preview_model import end_preset_preview  # noqa: PLC0415

        editor = self._editor
        sc = getattr(editor.window, "scene_controller", None)
        if sc is None:
            self._preview_active = False
            self._preview_snapshot = None
            self._preview_preset_id = None
            return
        scene = getattr(sc, "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            self._preview_active = False
            self._preview_snapshot = None
            self._preview_preset_id = None
            return

        restored = end_preset_preview(scene, self._preview_snapshot)
        sc._loaded_scene_data = restored
        self._preview_active = False
        self._preview_snapshot = None
        self._preview_preset_id = None

    def commit_preset(self, preset_id: str) -> bool:
        """Commit an HD2D preset (cancels preview first, then applies via action).

        This marks dirty and pushes ONE undo entry.

        Args:
            preset_id: The preset to commit.

        Returns:
            True if preset was committed.
        """
        # Cancel preview first to restore original state
        self.cancel_preview()

        # Now apply normally via the action system
        from engine.editor.editor_actions import run_editor_action  # noqa: PLC0415

        editor = self._editor
        action_id = f"editor.hd2d.preset.{preset_id}.apply"
        return run_editor_action(action_id, editor, editor.window)

    def maybe_auto_apply_defaults(self) -> bool:
        """Auto-apply HD2D defaults to the current scene if configured.

        This is called after scene load. It will apply the default preset
        ONLY if:
        1. A default preset is configured in workspace settings
        2. The scene does NOT already have any HD2D setting keys

        Does NOT push undo or mark dirty (silent auto-apply).

        Returns:
            True if defaults were applied, False otherwise.
        """
        editor = self._editor
        default_preset_id = editor._hd2d_default_preset_id
        if not default_preset_id:
            return False

        from .hd2d_defaults_model import (  # noqa: PLC0415
            should_auto_apply_default,
            apply_safe_merge,
        )

        sc = getattr(editor.window, "scene_controller", None)
        if sc is None:
            return False
        scene = getattr(sc, "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return False

        if not should_auto_apply_default(scene, default_preset_id):
            return False

        # Apply defaults silently (no undo, no dirty mark)
        new_scene = apply_safe_merge(scene, default_preset_id)
        sc._loaded_scene_data = new_scene
        return True

    def upgrade_scene_to_defaults(self) -> bool:
        """Explicitly upgrade scene to HD2D defaults.

        This is the user-triggered action. It:
        1. Uses the configured default preset (no-op if not set)
        2. Only fills missing HD2D keys (safe merge)
        3. Marks dirty
        4. Pushes ONE undo entry

        Returns:
            True if upgrade was applied, False otherwise.
        """
        editor = self._editor
        default_preset_id = editor._hd2d_default_preset_id
        if not default_preset_id:
            return False

        from .hd2d_defaults_model import (  # noqa: PLC0415
            is_valid_default_preset_id,
            compute_safe_merge_patch,
            apply_safe_merge,
            format_upgrade_undo_label,
        )

        if not is_valid_default_preset_id(default_preset_id):
            return False

        sc = getattr(editor.window, "scene_controller", None)
        if sc is None:
            return False
        scene = getattr(sc, "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return False

        # Compute what keys will be added (for undo entry)
        before_settings = copy.deepcopy(scene.get("settings")) if isinstance(scene.get("settings"), dict) else {}
        merge_patch = compute_safe_merge_patch(scene, default_preset_id)

        if not merge_patch:
            # No missing keys to fill - no-op
            return False

        new_scene = apply_safe_merge(scene, default_preset_id)
        after_settings = new_scene.get("settings") if isinstance(new_scene.get("settings"), dict) else {}

        sc._loaded_scene_data = new_scene

        # Mark dirty
        if callable(getattr(editor, "_mark_dirty", None)):
            editor._mark_dirty()

        # Push undo entry
        if callable(getattr(editor, "_push_command", None)):
            editor._push_command({
                "type": "UpgradeSceneHd2dDefaults",
                "label": format_upgrade_undo_label(default_preset_id),
                "preset_id": default_preset_id,
                "before": before_settings,
                "after": after_settings,
            })

        return True
