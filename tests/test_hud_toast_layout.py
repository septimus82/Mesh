"""#422 H8: a toast's lines and box come from one layout, measured in the font it is drawn in. The controls hint ran
far past its border: the box was guessed from the character count and capped at 360 px, the text drawn unbounded.
The rendered checks (real fonts, real frames) are tests/test_gameplay_viewport_hud_gpu.py."""

from __future__ import annotations

import pytest

from engine.ui_overlays.hud import TOAST_MIN_WIDTH, TOAST_PAD_X, TOAST_PAD_Y, ToastLayout, layout_toast

pytestmark = pytest.mark.fast

HINT = "Q: Quest Log  Tab: Inventory  I: Inspector  C: Character  H: Help"
PITCH = 22.0


def mono(line: str) -> float:  # (a monospaced font, 9 px a letter)
    return 9.0 * len(line)


def _fits(layout: ToastLayout, max_width: float) -> None:
    assert layout.width <= max_width
    for line in layout.lines:
        assert mono(line) + 2 * TOAST_PAD_X <= layout.width, f"{line!r} is wider than its box"
    assert layout.height == len(layout.lines) * PITCH + 2 * TOAST_PAD_Y


def test_the_controls_hint_gets_a_box_as_wide_as_its_text() -> None:
    layout = layout_toast(HINT, measure=mono, line_height=PITCH, max_width=640)
    assert layout.lines == (HINT,)
    assert layout.width == mono(HINT) + 2 * TOAST_PAD_X > 360, "no longer capped at 360 px"
    _fits(layout, 640)


@pytest.mark.parametrize("max_width", [520, 400, 300, 200])
def test_a_narrow_window_wraps_it_between_its_groups(max_width: float) -> None:
    layout = layout_toast(HINT, measure=mono, line_height=PITCH, max_width=max_width)
    assert len(layout.lines) > 1
    _fits(layout, max_width)
    assert " ".join(" ".join(layout.lines).split()) == " ".join(HINT.split()), "every word, in order"
    if max_width >= 200:  # (each "key: what" group fits a line of its own)
        assert all(not line.endswith(":") for line in layout.lines), "never 'Tab:' on one line, 'Inventory' on the next"


def test_a_short_toast_keeps_its_box() -> None:
    layout = layout_toast("Game saved", measure=mono, line_height=PITCH, max_width=640)
    assert (layout.lines, layout.width, layout.height) == (("Game saved",), TOAST_MIN_WIDTH, 34.0), "as before H8"


def test_a_word_longer_than_a_line_is_broken_not_cut() -> None:
    word = "Supercalifragilisticexpialidocious-ever-so-long"
    layout = layout_toast(f"Found {word}!", measure=mono, line_height=PITCH, max_width=180)
    assert "".join(layout.lines).replace(" ", "") == f"Found{word}!"
    _fits(layout, 180)


def test_the_box_never_outgrows_a_tiny_window_and_lands_on_whole_pixels() -> None:
    layout = layout_toast("Game saved", measure=lambda s: 7.3 * len(s), line_height=21.4, max_width=150.6)
    assert layout.width == 150 and layout.line_height == 22.0
    wide = layout_toast(HINT, measure=lambda s: 7.3 * len(s), line_height=21.4, max_width=900)
    assert wide.width == int(wide.width) and wide.width >= 7.3 * len(HINT) + 2 * TOAST_PAD_X


def test_a_taller_line_pitch_makes_a_taller_box() -> None:  # (a larger text scale)
    small = layout_toast(HINT, measure=mono, line_height=22.0, max_width=400)
    large = layout_toast(HINT, measure=lambda s: 1.5 * mono(s), line_height=33.0, max_width=400)
    assert len(large.lines) > len(small.lines) and large.height == len(large.lines) * 33.0 + 2 * TOAST_PAD_Y
