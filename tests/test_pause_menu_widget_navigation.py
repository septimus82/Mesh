from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.input import InputManager
from engine.ui_overlays.pause_menu import PauseMenu
from engine.ui_overlays.widgets import Button, ScrollList, Slider, Toggle
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _StubAudio:
    def __init__(self) -> None:
        self.sounds: list[str] = []
        self.music_calls: list[float] = []
        self.sfx_calls: list[float] = []

    def play_sound(self, path: str) -> None:
        self.sounds.append(path)

    def set_music_volume(self, volume: float) -> None:
        self.music_calls.append(float(volume))

    def set_sfx_volume(self, volume: float) -> None:
        self.sfx_calls.append(float(volume))


class _StubSaveManager:
    def __init__(self, slots: list[str] | None = None) -> None:
        self.slots = list(slots or [])
        self.saved: list[str] = []
        self.loaded: list[str] = []

    def list_saves(self) -> list[str]:
        return list(self.slots)

    def save_game(self, slot: str) -> bool:
        self.saved.append(str(slot))
        if slot not in self.slots:
            self.slots.append(str(slot))
        return True

    def load_game(self, slot: str) -> bool:
        self.loaded.append(str(slot))
        return True


def _window(*, slots: list[str] | None = None) -> SimpleNamespace:
    cfg = SimpleNamespace(
        music_volume=0.5,
        sfx_volume=0.25,
        fog_enabled=False,
        soft_shadows_enabled=False,
    )
    return SimpleNamespace(
        width=800,
        height=600,
        paused=True,
        audio=_StubAudio(),
        engine_config=cfg,
        save_manager=_StubSaveManager(slots),
        runtime_settings_path=None,
    )


@pytest.fixture(autouse=True)
def _arcade_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)


def _click(menu: PauseMenu, action_id: str) -> bool:
    layout = menu.layout_current_state()
    target = next(target for target in layout.hit_targets if target.action_id == action_id)
    return menu.on_mouse_press(target.rect.center_x, target.rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)


def test_main_action_ids_are_stable_unique_and_non_destructive_click_matches_enter(monkeypatch: pytest.MonkeyPatch) -> None:
    close_calls: list[bool] = []
    monkeypatch.setattr(optional_arcade.arcade, "close_window", lambda: close_calls.append(True))

    expected = (
        "pause.main.resume",
        "pause.main.settings",
        "pause.main.save",
        "pause.main.load",
        "pause.main.quit",
    )
    menu = PauseMenu(as_any(_window(slots=["slot_a"])))
    menu.visible = True
    layout = menu.layout_current_state()
    assert layout.action_ids == expected
    assert len(set(layout.action_ids)) == len(expected)

    for index, action_id in enumerate(expected[:-1]):
        by_key = PauseMenu(as_any(_window(slots=["slot_a"])))
        by_key.visible = True
        by_key.selected_index = index
        assert by_key.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True

        by_click = PauseMenu(as_any(_window(slots=["slot_a"])))
        by_click.visible = True
        assert _click(by_click, action_id) is True

        assert (by_click.visible, by_click.state, by_click.selected_index) == (
            by_key.visible,
            by_key.state,
            by_key.selected_index,
        )

    menu.selected_index = 4
    assert menu.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert close_calls == [True]


def test_mouse_before_draw_uses_layout_without_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    menu = PauseMenu(as_any(_window()))
    menu.visible = True
    monkeypatch.setattr(menu, "draw", lambda: (_ for _ in ()).throw(AssertionError("draw called")))
    monkeypatch.setattr(menu, "_draw_widget_instructions", lambda _instructions: (_ for _ in ()).throw(AssertionError("render called")))

    layout = menu.layout_current_state()
    target = next(target for target in layout.hit_targets if target.action_id == "pause.main.settings")
    menu._last_layout = None
    menu._layout_dirty = True
    assert menu.on_mouse_press(target.rect.center_x, target.rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert menu.state == "settings"


def test_state_transition_clears_main_hit_targets() -> None:
    menu = PauseMenu(as_any(_window()))
    menu.visible = True
    assert menu.layout_current_state().hit_targets
    assert _click(menu, "pause.main.settings") is True
    assert menu.state == "settings"
    assert [target.action_id for target in menu.layout_current_state().hit_targets] != [
        "pause.main.resume",
        "pause.main.settings",
        "pause.main.save",
        "pause.main.load",
        "pause.main.quit",
    ]


def test_save_slots_new_save_and_back_are_widget_backed_and_click_matches_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window(slots=["slot_a", "slot_b"])
    menu = PauseMenu(as_any(window))
    menu.visible = True
    _click(menu, "pause.main.save")

    layout = menu.layout_current_state()
    assert any(isinstance(target.widget, ScrollList) for target in layout.hit_targets)
    assert layout.action_ids == ("pause.save.slot.0", "pause.save.slot.1", "pause.save.new", "pause.save.back")

    by_key = PauseMenu(as_any(_window(slots=["slot_a", "slot_b"])))
    by_key.visible = True
    by_key.state = "save"
    by_key.save_slots = ["slot_a", "slot_b"]
    by_key.selected_save_index = 1
    assert by_key.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert by_key.window.save_manager.saved == ["slot_b"]

    by_click = PauseMenu(as_any(_window(slots=["slot_a", "slot_b"])))
    by_click.visible = True
    by_click.state = "save"
    by_click.save_slots = ["slot_a", "slot_b"]
    assert _click(by_click, "pause.save.slot.1") is True
    assert by_click.window.save_manager.saved == ["slot_b"]

    menu.state = "save"
    menu.save_slots = ["slot_a", "slot_b"]
    monkeypatch.setattr(menu, "_new_save_slot_name", lambda: "save_20260714_120000")
    assert _click(menu, "pause.save.new") is True
    assert window.save_manager.saved[-1] == "save_20260714_120000"

    menu.state = "save"
    menu.save_slots = ["slot_a", "slot_b"]
    assert _click(menu, "pause.save.back") is True
    assert menu.state == "main"


def test_save_long_list_is_bounded_and_leaving_clears_stale_targets() -> None:
    menu = PauseMenu(as_any(_window(slots=[f"slot_{i}" for i in range(30)])))
    menu.visible = True
    menu.state = "save"
    menu.save_slots = menu.window.save_manager.list_saves()
    layout = menu.layout_current_state()
    assert len(layout.hit_targets) < 32
    assert menu._save_scroll.visible_capacity < 32
    assert all(target.rect.bottom >= layout.hit_targets[-1].rect.bottom for target in layout.hit_targets)

    first_target = layout.hit_targets[0]
    menu.state = "main"
    menu._invalidate_layout()
    assert menu.on_mouse_press(first_target.rect.center_x, first_target.rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert menu.state == "main"


def test_load_click_matches_keyboard_unsaved_confirmation_and_success_closes() -> None:
    by_key = PauseMenu(as_any(_window(slots=["slot_a", "slot_b"])))
    by_key.visible = True
    by_key.state = "load"
    by_key.save_slots = ["slot_a", "slot_b"]
    by_key.selected_save_index = 1
    assert by_key.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert by_key.window.save_manager.loaded == ["slot_b"]
    assert by_key.visible is False
    assert by_key.window.paused is False

    by_click = PauseMenu(as_any(_window(slots=["slot_a", "slot_b"])))
    by_click.visible = True
    by_click.state = "load"
    by_click.save_slots = ["slot_a", "slot_b"]
    assert _click(by_click, "pause.load.slot.1") is True
    assert by_click.window.save_manager.loaded == ["slot_b"]
    assert by_click.visible is False

    callbacks: list[tuple[str, Any]] = []

    def _confirm(reason: str, action: Any) -> bool:
        callbacks.append((reason, action))
        return True

    with_editor = _window(slots=["slot_a"])
    with_editor.editor_controller = SimpleNamespace(active=True, confirm_unsaved_changes=_confirm)
    menu = PauseMenu(as_any(with_editor))
    menu.visible = True
    menu.state = "load"
    menu.save_slots = ["slot_a"]
    assert menu.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert callbacks and callbacks[0][0] == "Load Game"
    assert with_editor.save_manager.loaded == []


def test_load_no_saves_has_back_and_leaving_clears_stale_targets() -> None:
    menu = PauseMenu(as_any(_window(slots=[])))
    menu.visible = True
    menu.state = "load"
    menu.save_slots = []
    layout = menu.layout_current_state()
    assert layout.action_ids == ("pause.load.back",)
    assert menu.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert menu.state == "main"

    menu.state = "load"
    menu._invalidate_layout()
    target = menu.layout_current_state().hit_targets[0]
    menu.state = "main"
    menu._invalidate_layout()
    assert menu.on_mouse_press(target.rect.center_x, target.rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert menu.state == "main"


def test_settings_widgets_click_keyboard_and_gamepad_apply_and_persist() -> None:
    window = _window()
    saves: list[bool] = []
    menu = PauseMenu(as_any(window))
    menu._save_runtime_settings = lambda: saves.append(True)  # type: ignore[method-assign]
    menu.visible = True
    menu.state = "settings"
    layout = menu.layout_current_state()
    widgets = {target.action_id: target.widget for target in layout.hit_targets}
    assert isinstance(widgets["pause.settings.music_volume"], Slider)
    assert isinstance(widgets["pause.settings.sfx_volume"], Slider)
    assert isinstance(widgets["pause.settings.fog_enabled"], Toggle)
    assert isinstance(widgets["pause.settings.soft_shadows_enabled"], Toggle)
    assert isinstance(widgets["pause.settings.back"], Button)
    assert [target.action_id for target in layout.hit_targets] == [
        "pause.settings.music_volume",
        "pause.settings.sfx_volume",
        "pause.settings.fog_enabled",
        "pause.settings.soft_shadows_enabled",
        "pause.settings.back",
    ]

    music_target = next(target for target in layout.hit_targets if target.action_id == "pause.settings.music_volume")
    assert menu.on_mouse_press(music_target.rect.right - 1.0, music_target.rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.runtime_settings.music_volume > 0.95
    assert window.audio.music_calls[-1] > 0.95
    assert saves

    menu._settings_index = 1
    assert menu.on_key_press(optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.MOD_SHIFT) is True
    assert window.runtime_settings.sfx_volume == pytest.approx(0.15)
    assert window.audio.sfx_calls[-1] == pytest.approx(0.15)

    manager = InputManager()
    window.input = manager
    menu._settings_index = 1
    manager.set_gamepad_state(
        actions_down={"move_right"},
        axis_values={("move_left", "move_right"): 0.0, ("move_down", "move_up"): 0.0},
        supported_actions={"move_down", "move_up", "move_left", "move_right"},
        source_active=True,
    )
    manager.update(0.016)
    menu.update(0.016)
    assert window.runtime_settings.sfx_volume == pytest.approx(0.2)

    menu._settings_index = 2
    assert menu.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert window.runtime_settings.fog_enabled is True
    menu.state = "settings"
    menu._invalidate_layout()
    assert _click(menu, "pause.settings.fog_enabled") is True
    assert window.runtime_settings.fog_enabled is False
    assert _click(menu, "pause.settings.back") is True
    assert menu.state == "main"


def test_resize_rebuilds_geometry_and_old_coordinates_do_not_activate_stale_controls() -> None:
    window = _window()
    menu = PauseMenu(as_any(window))
    menu.visible = True
    old_target = next(target for target in menu.layout_current_state().hit_targets if target.action_id == "pause.main.settings")
    window.width = 1200
    window.height = 900
    menu.on_resize(window.width, window.height)
    new_target = next(target for target in menu.layout_current_state().hit_targets if target.action_id == "pause.main.settings")
    assert (old_target.rect.center_x, old_target.rect.center_y) != (new_target.rect.center_x, new_target.rect.center_y)
    assert menu.on_mouse_press(old_target.rect.center_x, old_target.rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert menu.state == "main"


def test_empty_and_right_clicks_are_modal_noops_and_blocks_input_when_visible() -> None:
    menu = PauseMenu(as_any(_window()))
    assert menu.blocks_input is False
    menu.visible = True
    assert menu.blocks_input is True
    assert menu.on_mouse_press(5.0, 5.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert menu.state == "main"
    assert menu.on_mouse_press(400.0, 300.0, 2, 0) is True
    assert menu.state == "main"
