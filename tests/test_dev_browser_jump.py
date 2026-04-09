import types
from unittest.mock import MagicMock

import engine.optional_arcade as optional_arcade

from engine.game import GameWindow
from engine.ui import DevBrowserOverlay
from tests._typing import as_any


class _StubSceneIndex:
    def __init__(
        self,
        *,
        id_match: bool = False,
        zone_match: bool = False,
        mesh_match: bool = False,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self._id_match = id_match
        self._zone_match = zone_match
        self._mesh_match = mesh_match

    def get_by_id(self, value: str):
        self.calls.append(("id", value))
        return object() if self._id_match else None

    def get_by_zone_id(self, value: str):
        self.calls.append(("zone_id", value))
        return object() if self._zone_match else None

    def get_first_by_mesh_name(self, value: str):
        self.calls.append(("mesh_name", value))
        return object() if self._mesh_match else None


def _stub_window(*, idx: _StubSceneIndex | None, scene_loaded: bool = True):
    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())
    window.set_next_spawn_point = MagicMock()
    window.request_reload_current_scene = MagicMock()
    window.request_scene_change = MagicMock()

    if scene_loaded:
        controller = types.SimpleNamespace()
        controller.current_scene_path = "packs/core_regions/scenes/Ridge Outpost_hub.json"
        controller._ensure_scene_index = (lambda: idx) if idx is not None else (lambda: None)
        window.scene_controller = controller
    else:
        window.scene_controller = None

    return window


def test_jump_mode_toggles_with_slash_only_in_scenes_mode() -> None:
    window = _stub_window(idx=_StubSceneIndex(id_match=True))
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True

    overlay.mode = "worlds"
    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    assert overlay.jump_mode is False

    overlay.mode = "scenes"
    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    assert overlay.jump_mode is True


def test_jump_input_does_not_touch_filter_and_esc_exits_jump_mode() -> None:
    window = _stub_window(idx=_StubSceneIndex(id_match=True))
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"
    overlay.filter_text = "filter"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.on_text("/")  # if emitted, it must not become part of jump_text
    overlay.on_text("A")
    overlay.on_text("B")

    assert overlay.filter_text == "filter"
    assert overlay.jump_text == "AB"

    overlay.on_key_press(optional_arcade.arcade.key.ESCAPE, 0)
    assert overlay.visible is True
    assert overlay.jump_mode is False


def test_jump_success_uses_resolution_order_and_requests_reload_and_toast_once() -> None:
    idx = _StubSceneIndex(zone_match=True)
    window = _stub_window(idx=idx)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.jump_text = "  Zone42  "
    overlay.on_key_press(optional_arcade.arcade.key.ENTER, 0)

    assert idx.calls == [("id", "Zone42"), ("zone_id", "Zone42")]

    window.set_next_spawn_point.assert_called_once_with("zone42")
    window.request_reload_current_scene.assert_called_once_with()
    window.request_scene_change.assert_not_called()
    window.player_hud.enqueue_toast.assert_called_once()
    assert window.player_hud.enqueue_toast.call_args.args[0] == "Jumped to: zone42"


def test_jump_success_prefers_id_then_zone_then_mesh() -> None:
    idx = _StubSceneIndex(id_match=True, zone_match=True, mesh_match=True)
    window = _stub_window(idx=idx)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.jump_text = "  Thing  "
    overlay.on_key_press(optional_arcade.arcade.key.ENTER, 0)

    assert idx.calls == [("id", "Thing")]


def test_jump_not_found_stays_in_jump_mode_and_does_not_reload() -> None:
    idx = _StubSceneIndex()
    window = _stub_window(idx=idx)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.jump_text = "Nope"
    overlay.on_key_press(optional_arcade.arcade.key.ENTER, 0)

    window.set_next_spawn_point.assert_not_called()
    window.request_reload_current_scene.assert_not_called()
    window.request_scene_change.assert_not_called()
    window.player_hud.enqueue_toast.assert_called_once()
    assert window.player_hud.enqueue_toast.call_args.args[0] == "Jump target not found: Nope"
    assert overlay.jump_mode is True


def test_jump_unavailable_no_scene_loaded_toasts_and_does_nothing() -> None:
    window = _stub_window(idx=_StubSceneIndex(id_match=True), scene_loaded=False)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.jump_text = "Anything"
    overlay.on_key_press(optional_arcade.arcade.key.ENTER, 0)

    window.set_next_spawn_point.assert_not_called()
    window.request_reload_current_scene.assert_not_called()
    window.request_scene_change.assert_not_called()
    window.player_hud.enqueue_toast.assert_called_once()
    assert window.player_hud.enqueue_toast.call_args.args[0] == "Jump unavailable (no scene loaded)"


def test_game_window_request_reload_current_scene_delegates() -> None:
    calls: list[bool] = []

    class Dummy:
        def request_scene_reload(self, clear_assets: bool = False) -> None:
            calls.append(clear_assets)

    dummy = Dummy()
    GameWindow.request_reload_current_scene(as_any(dummy))
    GameWindow.request_reload_current_scene(as_any(dummy), clear_assets=True)
    assert calls == [False, True]

