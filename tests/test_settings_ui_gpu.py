"""Milestone 21B.1: the pause menu's and main menu's Settings drawn in a hidden window: each slider's label (as its
text renders) clear of its bar, five presses of LEFT saying "Settings saved" once, and the value kept. Silent (master
volume 0); the player's settings file is the test's own. GL-gated: MESH_GL_SMOKE=1."""

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
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import settings_ui_check

    out = tmp_path_factory.mktemp("settings_ui")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    try:
        return settings_ui_check.check(out)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)


def test_the_pause_menus_slider_labels_are_clear_of_their_bars(run: dict) -> None:
    sliders = run["pause"]["sliders"]
    assert sliders and not any(s["overlaps"] for s in sliders)


@pytest.mark.parametrize("menu", ["pause", "main"])
def test_five_steps_say_settings_saved_once_and_are_kept(run: dict, menu: str) -> None:
    assert run[menu]["toasts_showing"] == ["Settings saved"]
    before, after = run[menu]["music_before_after"]
    assert after == pytest.approx(before - 0.25) and run[menu]["saved"] == pytest.approx(after)
