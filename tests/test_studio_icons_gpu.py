"""Milestone 15 Stage 3: an icon button is the same button (text, size, click target) with a tinted icon that
follows its state, and a plain button when the icon is missing or wouldn't fit. GL-gated: set MESH_GL_SMOKE=1."""

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


def test_an_icon_button_is_the_same_button_with_a_tinted_icon(window) -> None:
    from engine import studio_ui as ui

    plain = ui.gui.UIFlatButton(text="Undo", width=64, height=28, style=ui.S_BUTTON)
    button = ui.make_button("Undo", width=64, height=28, style=ui.S_BUTTON)
    assert isinstance(button, ui.gui.UIFlatButton) and button.text == plain.text == "Undo"
    assert (button.width, button.height) == (plain.width, plain.height)
    assert button._icon is not None and tuple(button._icon.tint)[:3] == ui.C_TEXT

    selected = ui.make_button("Look", width=100, height=28, style=ui.S_ACTIVE)
    assert tuple(selected._icon.tint)[:3] == (190, 230, 255), "the selected state's text colour"
    selected.disabled = True
    selected._apply_style(selected.get_current_style())
    assert tuple(selected._icon.tint)[:3] == ui.C_MUTED, "disabled: muted, still distinguishable"


def test_a_missing_icon_or_a_too_narrow_button_falls_back_to_a_plain_button(window, monkeypatch, tmp_path) -> None:
    from engine import studio_ui as ui

    assert ui.make_button("Undo", width=40, height=28, style=ui.S_BUTTON)._icon is None, "no room: text only"
    assert ui.make_button("Some room", width=200, height=28, style=ui.S_BUTTON)._icon is None, "no icon for it"
    monkeypatch.setattr(ui, "ICONS", tmp_path)
    monkeypatch.setattr(ui, "_ICON_TEXTURES", {})
    bare = ui.make_button("Save", width=100, height=28, style=ui.S_BUTTON)
    assert bare._icon is None and bare.text == "Save", "a copy without icons still has its buttons"
