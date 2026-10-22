"""Creator Mode text fields take characters from the window's text event (CREATOR-POLISH 1).

A real keyboard sends a key press (raw key code, no Shift/layout applied) and then a
text event with the character the OS layout produced. The fields used to build text
from the key code, so Shift and layouts were ignored (Swedish users couldn't type å ä ö).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.editor.creator_mode.creator_add_person import ADD_PERSON_LINE_ACTION_ID
from engine.editor.creator_mode.creator_overlay import build_creator_overlay_model
from engine.editor.creator_mode.creator_overlay_renderer import build_creator_overlay_draw_commands
from engine.editor.live_session_bridge import EditorLiveSessionBridge
from tests._headless_editor import headless_editor

pytestmark = [pytest.mark.fast]

# (raw key code a Swedish keyboard sends, Shift held, character from the text event)
_SWEDISH_KEYS = [
    (ord("h"), True, "H"), (ord("e"), False, "e"), (ord("j"), False, "j"),
    (ord("1"), True, "!"), (ord(" "), False, " "),
    (ord("å"), True, "Å"), (ord("s"), False, "s"), (ord("a"), False, "a"),
    (ord("+"), True, "?"),
]


@pytest.fixture
def window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with headless_editor(tmp_path, monkeypatch) as win:
        editor = win.editor_controller
        editor.live_bridge = EditorLiveSessionBridge(editor, tmp_path)
        editor.creator_mode.toggle()
        yield win


def _focus_person_line(win) -> None:
    creator = win.editor_controller.creator_mode
    model = build_creator_overlay_model(creator.build_snapshot())
    field = next(c for c in build_creator_overlay_draw_commands(model, win.width, win.height) if c.action_id == ADD_PERSON_LINE_ACTION_ID)
    creator.handle_overlay_click(field.hit_left + 2.0, (field.hit_top + field.hit_bottom) / 2.0)
    assert creator.person_line_focused


def _type(win, keys) -> None:
    from engine import arcade_fallback

    shift = arcade_fallback.key.MOD_SHIFT
    for code, shifted, char in keys:
        win.on_key_press(code, shift if shifted else 0)
        win.on_text(char)
        win.on_key_release(code, shift if shifted else 0)


def _clear(win, count: int) -> None:
    from engine import arcade_fallback

    for _ in range(count):
        win.on_key_press(arcade_fallback.key.BACKSPACE, 0)
        win.on_key_release(arcade_fallback.key.BACKSPACE, 0)


def test_window_typing_uses_layout_and_shift_without_doubling(window) -> None:
    creator = window.editor_controller.creator_mode
    _focus_person_line(window)
    _clear(window, len("Hello!"))
    _type(window, _SWEDISH_KEYS)
    assert creator.build_snapshot().add_person_panel.line == "Hej! Åsa?"


def test_escape_unfocuses_field_even_over_an_active_tour(window) -> None:
    from engine import arcade_fallback

    editor = window.editor_controller
    creator = editor.creator_mode
    tour = editor.tour
    assert tour.is_active  # a fresh project: Shift+F5 opens Creator over the first-launch tour
    _focus_person_line(window)

    window.on_key_press(arcade_fallback.key.ESCAPE, 0)
    assert not creator.text_field_focused  # Esc unfocused the field...
    assert tour.is_active and creator.active  # ...and did nothing else

    window.on_key_press(arcade_fallback.key.ESCAPE, 0)  # unfocused Esc: normal effect (skip the tour)
    assert not tour.is_active and creator.active

    window.on_key_press(arcade_fallback.key.L, 0)  # shortcuts work again after unfocus
    assert editor.lights_tool_active is True


def test_enter_while_typing_does_not_advance_the_tour(window) -> None:
    from engine import arcade_fallback

    tour = window.editor_controller.tour
    step = tour.current_step
    _focus_person_line(window)
    window.on_key_press(arcade_fallback.key.ENTER, 0)
    assert tour.is_active and tour.current_step == step


def test_focused_typing_does_not_fire_editor_shortcuts(window) -> None:
    from engine import arcade_fallback

    editor = window.editor_controller
    l_key = [(arcade_fallback.key.L, False, "l")]  # L toggles the lights tool in the editor
    _focus_person_line(window)
    _type(window, l_key)
    assert editor.lights_tool_active is False
    assert editor.creator_mode.build_snapshot().add_person_panel.line.endswith("l")

    # Control: the same key does fire the shortcut once the field loses focus (click on the canvas).
    editor.creator_mode.handle_overlay_click(window.width / 2.0, window.height / 2.0)
    assert not editor.creator_mode.text_field_focused
    _type(window, l_key)
    assert editor.lights_tool_active is True
