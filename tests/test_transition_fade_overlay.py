from types import SimpleNamespace

import pytest

from engine.ui_overlays.transition_fade import TransitionFadeOverlay


def test_transition_fade_overlay_alpha_progression() -> None:
    window = SimpleNamespace(width=100, height=100)
    overlay = TransitionFadeOverlay(window)

    overlay.start_fade_out(1.0)
    overlay.update(0.25)
    assert overlay.alpha == pytest.approx(31.875)
    assert overlay.alpha != pytest.approx(63.75)
    overlay.update(0.25)
    assert overlay.alpha == pytest.approx(127.5)
    overlay.update(0.25)
    assert overlay.alpha == pytest.approx(223.125)
    overlay.update(0.25)
    assert overlay.alpha == pytest.approx(255.0)
    assert overlay.is_active is True

    overlay.start_fade_in(1.0)
    overlay.update(0.5)
    assert overlay.alpha == pytest.approx(127.5)
    overlay.update(0.5)
    assert overlay.alpha == pytest.approx(0.0)
    assert overlay.is_active is False


def test_transition_fade_overlay_blocks_input_while_active() -> None:
    window = SimpleNamespace(width=100, height=100)
    overlay = TransitionFadeOverlay(window)

    overlay.start_fade_out(0.2)
    assert overlay.blocks_input is True
    overlay.update(0.2)
    assert overlay.blocks_input is True

    overlay.start_fade_in(0.1)
    overlay.update(0.1)
    assert overlay.blocks_input is False


def test_transition_fade_overlay_loading_text_toggle() -> None:
    window = SimpleNamespace(
        width=100,
        height=100,
        engine_config=SimpleNamespace(scene_fade_show_loading_text=True),
        scene_controller=SimpleNamespace(scene_settings={}),
    )
    overlay = TransitionFadeOverlay(window)

    overlay.start_fade_out(1.0)
    overlay.update(0.01)
    assert overlay.should_draw_loading_text is False

    overlay.update(0.24)
    assert overlay.should_draw_loading_text is True

    window.scene_controller.scene_settings["scene_fade_show_loading_text"] = False
    assert overlay.should_draw_loading_text is False
