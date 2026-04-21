"""Editor play session controller.

Extracted from editor_controller.py to encapsulate play session operations:
start, stop, camera handling, and player spawning.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple, TYPE_CHECKING

from engine.logging_tools import get_logger
from engine.swallowed_exceptions import _log_swallow


if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class EditorPlayController:
    """Encapsulates play session operations."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def play_from_here(self) -> bool:
        """Start play session from current camera position.

        Returns:
            True if play session started, False otherwise.
        """
        editor = self._editor
        if not editor.active or editor.play_session.is_playing:
            return False

        def _apply() -> None:
            self.start_session()

        if editor.confirm_unsaved_changes("Play From Here", _apply):
            return False
        _apply()
        return True

    def stop_playing(self) -> bool:
        """Stop the current play session.

        Returns:
            True if stopped, False if not playing.
        """
        editor = self._editor
        if not editor.play_session.is_playing:
            return False
        self.stop_session()
        return True

    def start_session(self) -> None:
        """Start play session."""
        editor = self._editor
        session = editor.play_session
        session.is_playing = True
        scene_controller = getattr(editor.window, "scene_controller", None)
        session.return_scene_id = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
        session.return_camera_pos = self._get_camera_center()
        session.return_selection = editor.selected_entity
        session.spawn_mode = "camera_center"
        editor.active = False
        try:
            editor.window.paused = False
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EDIT-001", "engine/editor/editor_play_controller.py pass-only blanket swallow")
            pass
        self._spawn_player()

    def stop_session(self) -> None:
        """Stop play session and restore editor state."""
        editor = self._editor
        session = editor.play_session
        session.is_playing = False
        editor.active = True
        try:
            editor.window.paused = True
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EDIT-002", "engine/editor/editor_play_controller.py pass-only blanket swallow")
            pass

        scene_controller = getattr(editor.window, "scene_controller", None)
        current_scene = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
        return_scene = session.return_scene_id
        if return_scene and current_scene and return_scene != current_scene:
            requester = getattr(editor.window, "request_scene_change", None)
            if callable(requester):
                requester(return_scene)
            else:
                changer = getattr(scene_controller, "request_scene_change", None) if scene_controller is not None else None
                if callable(changer):
                    changer(return_scene)

        if return_scene and current_scene and return_scene == current_scene:
            selection = session.return_selection
            sprites = getattr(scene_controller, "all_sprites", None) if scene_controller is not None else None
            if selection is not None and isinstance(sprites, list) and selection in sprites:
                editor.selected_entity = selection

        self._restore_camera_position(session.return_camera_pos)

    def _get_camera_center(self) -> Tuple[float, float]:
        """Get the current camera center position."""
        editor = self._editor
        getter = getattr(editor.window, "get_camera_center", None)
        if callable(getter):
            try:
                pos = getter()
                if isinstance(pos, (tuple, list)) and len(pos) == 2:
                    return (float(pos[0]), float(pos[1]))
            except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
                _log_swallow("EDIT-003", "engine/editor/editor_play_controller.py pass-only blanket swallow")
                pass
        camera = getattr(editor.window, "camera", None)
        if camera is None:
            controller = getattr(editor.window, "camera_controller", None)
            camera = getattr(controller, "camera", None) if controller is not None else None
        position = getattr(camera, "position", None) if camera is not None else None
        if isinstance(position, (tuple, list)) and len(position) == 2:
            return (float(position[0]), float(position[1]))
        return (0.0, 0.0)

    def _restore_camera_position(self, pos: Tuple[float, float] | None) -> None:
        """Restore camera to a saved position."""
        if pos is None:
            return
        editor = self._editor
        camera = getattr(editor.window, "camera", None)
        if camera is None:
            controller = getattr(editor.window, "camera_controller", None)
            camera = getattr(controller, "camera", None) if controller is not None else None
        if camera is None:
            return
        move_to = getattr(camera, "move_to", None)
        if callable(move_to):
            move_to(pos, 1.0)
            return
        try:
            setattr(camera, "position", pos)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EDIT-004", "engine/editor/editor_play_controller.py pass-only blanket swallow")
            pass

    def _spawn_player(self) -> None:
        """Spawn player at camera center for play session."""
        editor = self._editor
        if editor.play_session.spawn_mode != "camera_center":
            return
        scene_controller = getattr(editor.window, "scene_controller", None)
        if scene_controller is None:
            return
        finder = getattr(scene_controller, "_find_player_sprite", None)
        player = finder() if callable(finder) else None
        if player is None:
            return
        cam_x, cam_y = self._get_camera_center()
        mutator = getattr(scene_controller, "_apply_entity_mutation", None)
        if callable(mutator):
            mutator(player, x=cam_x, y=cam_y)
            return
        try:
            player.center_x = float(cam_x)
            player.center_y = float(cam_y)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            return
        entity_data = getattr(player, "mesh_entity_data", None)
        if isinstance(entity_data, dict):
            entity_data["x"] = float(cam_x)
            entity_data["y"] = float(cam_y)
