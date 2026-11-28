"""Milestone 15 Stage 3: the launcher's recent projects are cards. A card is still a button whose text is the
project's name (what the launcher and its tests click), with its location under it, shortened from the start to fit.
GL-gated: set MESH_GL_SMOKE=1."""

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


@pytest.fixture(scope="module")
def window():
    from shadow_bench import Bench

    bench = Bench()  # a hidden window: a GL context for text
    yield bench
    bench.close()


def _detail(card) -> str:
    return next(c.text for c in card.children if isinstance(c, card.ui_label.__class__) and c is not card.ui_label)


def test_a_card_is_a_button_named_for_the_project_with_its_location_under_it(window) -> None:
    from engine import studio_ui as ui

    card = ui.CardButton(text="M14 Check", detail=r"C:\Users\me\Documents\Mesh Projects\M14 Check", icon="folder",
                         width=420, height=46, style=ui.S_CARD)
    assert isinstance(card, ui.gui.UIFlatButton) and card.text == "M14 Check"
    assert _detail(card) == r"C:\Users\me\Documents\Mesh Projects\M14 Check", "short enough: shown whole"
    assert card._icon is not None


def test_a_long_location_loses_its_start_and_keeps_its_prefix(window) -> None:
    from engine import studio_ui as ui

    folder = "C:\\" + "\\".join(["a-very-long-folder-name"] * 8) + "\\Old Prototype"
    card = ui.CardButton(text="Old Prototype", detail=folder, detail_prefix="Missing: ", icon="folder",
                         width=324, height=46, style=ui.S_CARD_MISSING)
    shown = _detail(card)
    assert shown.startswith("Missing: ...") and shown.endswith("\\Old Prototype")
    line = next(c for c in card.children if getattr(c, "text", None) == shown)
    assert line._label.content_width <= 324 - (14 + 20 + 12) - 12, "fits inside the card"
