from __future__ import annotations

from typing import Any


def close_palette(editor: Any) -> bool:
    panels = getattr(editor, "panels", None)
    if panels and hasattr(panels, "close_command_palette"):
        panels.close_command_palette()
    search = getattr(editor, "search", None)
    if search is not None:
        clear = getattr(search, "clear_command_palette_state", None)
        if callable(clear):
            clear()
    return True


def backspace(editor: Any) -> bool:
    search = getattr(editor, "search", None)
    if search is None:
        return False
    handler = getattr(search, "backspace_command_palette", None)
    if callable(handler):
        return bool(handler())
    return False


def move_up(editor: Any) -> bool:
    search = getattr(editor, "search", None)
    if search is None:
        return False
    mover = getattr(search, "move_command_palette_selection", None)
    if callable(mover):
        mover(-1)
        return True
    return True


def move_down(editor: Any) -> bool:
    search = getattr(editor, "search", None)
    if search is None:
        return False
    mover = getattr(search, "move_command_palette_selection", None)
    if callable(mover):
        mover(1)
        return True
    return True


def activate(editor: Any) -> bool:
    from engine.editor_commands import (  # noqa: PLC0415
        filter_commands,
        get_all_commands,
        get_palette_focus_target,
    )

    focus_target = get_palette_focus_target(editor)
    search = getattr(editor, "search", None)
    query, idx = ("", 0)
    if search is not None:
        getter = getattr(search, "get_command_palette_state", None)
        if callable(getter):
            query, idx = getter()
    commands = filter_commands(
        get_all_commands(getattr(editor, "window", None)),
        str(query or ""),
        focus_target=focus_target,
    )
    if commands:
        max_items = min(len(commands), 8)
        use_idx = max(0, min(int(idx or 0), max_items - 1))
        command = commands[use_idx]
        command.run(getattr(editor, "window", None))
        from engine.editor import command_palette_rank_model as rank_model  # noqa: PLC0415

        rank_model.record_command_executed(command.id)
    panels = getattr(editor, "panels", None)
    if panels and hasattr(panels, "close_command_palette"):
        panels.close_command_palette()
    if search is not None:
        clear = getattr(search, "clear_command_palette_state", None)
        if callable(clear):
            clear()
    return True
