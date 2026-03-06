from __future__ import annotations

from typing import Any

from engine.path_norm import normalize_scene_path


class EditorSceneOpenController:
    """Encapsulates scene open/switch orchestration for editor."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def open_scene_by_id(self, scene_id: str) -> bool:
        normalized = normalize_scene_path(scene_id)
        if not normalized:
            return False

        def _apply() -> None:
            self._editor.scene_switcher_active = False
            self._editor.scene_browser_active = False
            requester = getattr(self._editor.window, "request_scene_change", None)
            if callable(requester):
                requester(normalized)
            else:
                controller = getattr(self._editor.window, "scene_controller", None)
                change = getattr(controller, "request_scene_change", None) if controller is not None else None
                if callable(change):
                    change(normalized)
            self._editor.record_recent_scene(normalized)
            problems = getattr(self._editor, "problems", None)
            if problems is not None:
                refresher = getattr(problems, "refresh_structured_diagnostics", None)
                if callable(refresher):
                    refresher()

        if self._editor.confirm_unsaved_changes("Switch Scene", _apply):
            return False
        _apply()
        return True
