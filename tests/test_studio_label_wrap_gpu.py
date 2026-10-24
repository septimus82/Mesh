"""Milestone 14: a wrapped Studio label keeps its words whole.

pyglet 2.1 wraps at the right word but draws that word's first letter at the end of the line before ("It w" /
"orks"). Studio labels get pyglet's own break points as line breaks, so pyglet never wraps them itself. This also
guards the private pyglet layout ``engine.studio.hard_wrap`` reads. GL-gated: set MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tooling"))

TEXT = "Not drawn in the game: an opening, a way off the map. It works in its outlined area."


@pytest.fixture(scope="module")
def window():
    from shadow_bench import Bench

    bench = Bench()  # a hidden window: a GL context for text
    yield bench
    bench.close()


def _lines(label) -> list[str]:
    layout = label._label._label
    return [layout.document.text[ln.start:ln.start + ln.length].rstrip("\n ") for ln in layout._lines]


def test_a_wrapped_label_breaks_between_words_and_pyglet_no_longer_wraps_it(window) -> None:
    import arcade.gui as gui

    from engine.studio import hard_wrap

    for size in (9, 10, 11):
        label = gui.UILabel(text=TEXT, font_size=size, width=310, multiline=True)
        hard_wrap(label)
        lines = label.text.split("\n")
        assert len(lines) >= 2 and " ".join(lines) == TEXT, "breaks only where spaces were"
        assert _lines(label) == lines, "each line fits: pyglet draws them as given"
    short = gui.UILabel(text="Area changed.", font_size=9, width=310, multiline=True)
    hard_wrap(short)
    assert short.text == "Area changed."
