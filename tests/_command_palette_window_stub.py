from __future__ import annotations

from typing import Any, cast

from engine.game import GameWindow


class _StubUiController:
    input_blocked = False

    def on_key_press(self, *_args: object) -> bool:
        return False


class _StubConsoleController:
    active = False

    def toggle(self, *_args: object) -> None:
        return None

    def process_key(self, *_args: object) -> bool:
        return False


class _StubEditorController:
    active = False


class _StubInputController:
    def __init__(self, *, mouse_x: float = 0.0, mouse_y: float = 0.0) -> None:
        self.mouse_x = float(mouse_x)
        self.mouse_y = float(mouse_y)


class CommandPaletteWindowStub:
    def __init__(self, **extra_attrs: Any) -> None:
        self.show_debug = True
        self.scene_dirty = False
        self.scene_dirty_reason = ""
        self.scene_dirty_counter = 0
        self.undo_stack: list[object] = []
        self.redo_stack: list[object] = []
        self._undo_ts_counter = 0
        self._undo_suppress_count = 0
        self.command_palette_enabled = False
        self.command_palette_query = ""
        self.command_palette_index = 0
        self.command_palette_prompt_active = False
        self.last_macro_args: dict[str, object] = {}
        self.ui_controller = _StubUiController()
        self.console_controller = _StubConsoleController()
        self.editor_controller = _StubEditorController()
        self.input_controller = _StubInputController()
        for key, value in extra_attrs.items():
            setattr(self, key, value)

    def mark_scene_dirty(self, reason: str) -> None:
        self.scene_dirty = True
        self.scene_dirty_reason = str(reason)
        self.scene_dirty_counter = int(self.scene_dirty_counter) + 1

    def push_undo_frame(self, reason: str) -> None:
        GameWindow.push_undo_frame(cast(Any, self), reason)

    def undo(self) -> None:
        GameWindow.undo(cast(Any, self))

    def redo(self) -> None:
        GameWindow.redo(cast(Any, self))

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        return (float(x), float(y))


def as_game_window(window: CommandPaletteWindowStub) -> Any:
    return cast(Any, window)
