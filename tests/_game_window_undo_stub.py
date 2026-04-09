from __future__ import annotations

from typing import Any

from tests._typing import as_any


def as_game_window(window: object) -> Any:
    return as_any(window)


def bind_game_window_undo_methods(
    window: object,
    *,
    include_undo: bool = False,
    include_redo: bool = False,
) -> None:
    from engine.game import GameWindow

    any_window = as_any(window)

    if getattr(any_window, "mark_scene_dirty", None) is None:
        def _mark_scene_dirty(self: Any, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter = int(getattr(self, "scene_dirty_counter", 0) or 0) + 1

        any_window.mark_scene_dirty = _mark_scene_dirty.__get__(window)

    if getattr(any_window, "push_undo_frame", None) is None:
        any_window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(as_any(window), reason)

    if include_undo and getattr(any_window, "undo", None) is None:
        any_window.undo = lambda: GameWindow.undo(as_any(window))

    if include_redo and getattr(any_window, "redo", None) is None:
        any_window.redo = lambda: GameWindow.redo(as_any(window))
