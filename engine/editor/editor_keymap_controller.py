"""Editor keymap controller.

Extracted from editor_controller.py to encapsulate keymap override
loading, parsing, and application.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

from engine.logging_tools import get_logger

if TYPE_CHECKING:
    from engine.editor.keymap_override_model import ScopedOverrides

logger = get_logger(__name__)


class EditorKeymapController:
    """Encapsulates keymap override loading and application."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self._keymap_overrides: ScopedOverrides = {}

    @property
    def keymap_overrides(self) -> ScopedOverrides:
        """The current keymap overrides."""
        return self._keymap_overrides

    def load_overrides(self) -> None:
        """Load keymap overrides from keymap.json.

        Parses the keymap file, applies overrides to editor actions,
        and logs any conflicts or unknown entries.
        """
        editor = self._editor

        if os.environ.get("PYGBAG") == "1":
            self._keymap_overrides = {}
            return
        if os.environ.get("PYTEST_CURRENT_TEST") and editor._repo_root_override is None:
            self._keymap_overrides = {}
            return

        from engine.editor.editor_actions import get_editor_actions  # noqa: PLC0415
        from engine.editor.keymap_override_model import (  # noqa: PLC0415
            compute_keymap_conflicts,
            apply_keymap_overrides,
            parse_keymap_overrides,
            format_keymap_conflict,
        )
        from engine import json_io  # noqa: PLC0415

        keymap_path = editor._get_repo_root() / "keymap.json"
        if not keymap_path.exists():
            self._keymap_overrides = {}
            return
        try:
            payload = json_io.read_json(keymap_path)
        except Exception:
            self._keymap_overrides = {}
            return
        if not isinstance(payload, dict):
            self._keymap_overrides = {}
            return
        self._keymap_overrides = parse_keymap_overrides(payload)

        actions = get_editor_actions(None, None)
        known_scopes = {getattr(a, "shortcut_scope", "global") for a in actions}

        overridden, unknown_scopes, unknown_keys = apply_keymap_overrides(
            actions, self._keymap_overrides, known_scopes
        )

        applied_count = len(self._keymap_overrides) - len(unknown_scopes) - len(unknown_keys)

        if unknown_scopes:
            for scope in sorted(unknown_scopes):
                logger.warning("[Editor] Keymap overrides: unknown scope %r", scope)

        if unknown_keys:
            for scope, action_id in sorted(unknown_keys):
                logger.warning(
                    "[Editor] Keymap overrides: unknown action id %r in scope %r",
                    action_id,
                    scope,
                )

        conflicts = compute_keymap_conflicts(overridden)
        if conflicts:
            logger.warning("[Editor] Keymap overrides: shortcut conflicts:")
            for conflict in conflicts:
                logger.warning("[Editor]   %s", format_keymap_conflict(conflict))

        logger.info(
            "[Editor] Keymap overrides: applied %d of %d entries",
            applied_count,
            len(self._keymap_overrides),
        )
