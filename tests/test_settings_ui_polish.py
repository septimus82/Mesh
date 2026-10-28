"""Milestone 21B.1: the game's Settings pages. A slider's label and its bar don't overlap (the pause menu's did), and a
settings change says "Settings saved" once, in words (it said "UI_SETTINGS_SAVED", once per slider step). Headless."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine.ui_overlays.widgets import Rect, Slider
from engine.ui_toasts import ToastManager
from tests._typing import as_any

pytestmark = pytest.mark.fast

BOUNDS = Rect(x=20.0, y=30.0, width=240.0, height=50.0)


def _parts(slider: Slider, bounds: Rect = BOUNDS) -> dict[str, Any]:
    return {i.kind: i.payload for i in slider.layout(bounds).instructions}


def test_a_slider_with_a_label_line_keeps_its_bar_below_it() -> None:
    for value in (0.0, 0.5, 1.0):
        parts = _parts(Slider(label="Music Volume", value=value, height=50.0, label_size=26.0))
        label_bottom = parts["slider_label_text"]["y"] - 26.0
        for kind in ("slider_track", "slider_fill", "slider_knob"):
            rect = parts[kind]["rect"]
            assert rect.top <= label_bottom - 2.0 and rect.bottom >= BOUNDS.bottom, kind


def test_a_slider_without_a_label_line_is_laid_out_as_before() -> None:
    """``label_size`` 0 (the default): the settings overlay and every other slider keep their geometry."""
    parts = _parts(Slider(label="SFX Volume", value=0.4, height=28.0), Rect(x=20.0, y=30.0, width=240.0, height=28.0))
    track, knob = parts["slider_track"]["rect"], parts["slider_knob"]["rect"]
    assert (track.center_y, track.height) == (44.0, 7.0)  # centred: bounds 30-58, a quarter of 28 high
    assert (knob.center_y, knob.height) == pytest.approx((44.0, 16.8))


def _pause_menu() -> Any:
    from engine.ui_overlays.pause_menu import PauseMenu

    settings = SimpleNamespace(music_volume=0.5, sfx_volume=0.5, ambience_volume=1.0, fog_enabled=False,
                               reduced_flicker=False, text_scale=1.0, apply=lambda _w: None)
    window = SimpleNamespace(width=1280, height=720, paused=True, runtime_settings=settings, engine_config=None,
                             save_manager=SimpleNamespace(list_slots=lambda: []))
    menu = PauseMenu(as_any(window))
    menu.visible, menu.state = True, "settings"
    return menu


def test_the_pause_menus_slider_labels_sit_above_their_bars() -> None:
    menu = _pause_menu()
    layout = menu.layout_current_state()
    sliders = [w for w in menu._settings_widgets.values() if isinstance(w, Slider)]
    assert sliders and all(s.label_size > 0 for s in sliders)
    label_bottom = None
    checked = 0
    for instruction in layout.instructions:
        if instruction.kind == "slider_label_text":
            slider = next(s for s in sliders if s.label == instruction.payload["text"])
            label_bottom = instruction.payload["y"] - slider.label_size
        elif instruction.kind in ("slider_track", "slider_knob") and label_bottom is not None:
            assert instruction.payload["rect"].top < label_bottom, instruction.payload
            checked += 1
    assert checked >= 2 * len(sliders)


class _Hud:
    """The game HUD's toasts (its real toast manager)."""

    def __init__(self) -> None:
        self.toasts = ToastManager()

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:
        self.toasts.push_toast(message, ttl_s=seconds)

    def active_toasts(self) -> list[str]:
        return self.toasts.get_active_toasts()


def test_many_setting_changes_say_settings_saved_once_in_words(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from engine.ui_overlays._settings_data import toast_settings_saved

    monkeypatch.chdir(tmp_path)  # a game's own folder: no locales of its own
    from engine import paths

    monkeypatch.setattr(paths, "get_content_roots", lambda: [tmp_path])
    import engine.i18n as i18n

    monkeypatch.setattr(i18n, "_LOCALE_CACHE", {})
    window = SimpleNamespace(player_hud=_Hud())
    for _ in range(5):  # five slider steps
        toast_settings_saved(window)
        window.player_hud.toasts.tick(0.1)
    assert window.player_hud.active_toasts() == ["Settings saved"]
    window.player_hud.toasts.tick(2.5)  # gone; a later change says it again
    toast_settings_saved(window)
    assert window.player_hud.active_toasts() == ["Settings saved"]


def test_a_game_finds_the_engines_interface_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``tr`` looked for locales/ in the game's own folder only, so every menu message showed its raw key."""
    from engine import paths

    monkeypatch.setattr(paths, "get_content_roots", lambda: [tmp_path])
    import engine.i18n as i18n

    monkeypatch.setattr(i18n, "_LOCALE_CACHE", {})
    assert i18n.tr("UI_SETTINGS_SAVED") == "Settings saved"
    (tmp_path / "locales").mkdir()  # a game with its own text keeps it
    (tmp_path / "locales" / "en.json").write_text('{"UI_SETTINGS_SAVED": "Saved!"}', encoding="utf-8")
    monkeypatch.setattr(i18n, "_LOCALE_CACHE", {})
    assert i18n.tr("UI_SETTINGS_SAVED") == "Saved!"


@pytest.mark.parametrize("menu_module", ["pause_menu", "main_menu_overlay"])
def test_both_menus_save_through_the_once_only_message(menu_module: str) -> None:
    import importlib

    source = Path(importlib.import_module(f"engine.ui_overlays.{menu_module}").__file__ or "").read_text(encoding="utf-8")
    assert "toast_settings_saved(self.window)" in source and 'tr("UI_SETTINGS_SAVED")' not in source


@pytest.mark.parametrize("size", [(640, 480), (800, 600), (1280, 720), (1920, 1080)])
def test_every_settings_row_fits_its_panel_at_any_window_size(size: tuple[int, int]) -> None:
    menu = _pause_menu()
    menu.window.width, menu.window.height = size
    menu._invalidate_layout()
    layout = menu.layout_current_state()
    panel = menu._panel_bounds(height_scale=0.66, min_height=400.0, max_height=520.0)
    for target in layout.hit_targets:
        assert panel.bottom <= target.rect.bottom and target.rect.top <= panel.top, (size, target.action_id)


@pytest.mark.parametrize("size", [(640, 480), (800, 600), (1280, 720), (1920, 1080)])
def test_the_main_menus_settings_cards_fit_above_its_footer(size: tuple[int, int]) -> None:
    """Six settings rows at 640 x 480 ran past the panel and under its footer (since before M21B, which made it
    worse); where they already fitted, nothing moves."""
    from engine.ui_overlays._settings_data import SETTINGS_ROWS
    from engine.ui_overlays.main_menu_overlay import compute_menu_panel_layout

    layout = compute_menu_panel_layout(*size, len(SETTINGS_ROWS), 0)
    assert 0 <= layout.panel.bottom and layout.panel.top <= size[1]
    for card in layout.cards:
        assert card.bottom >= layout.panel.bottom + 40.0 and card.top <= layout.subtitle_y - 20.0, (size, card)
        assert card.top - card.bottom >= 48.0
    if size[1] >= 720:  # room enough: the layout as it was
        assert [round(c.top - c.bottom) for c in layout.cards] == [52] * len(SETTINGS_ROWS)
