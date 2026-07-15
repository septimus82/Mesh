from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.game_runtime import tick
from engine.ui_overlays.main_menu_overlay import MainMenuOverlay

pytestmark = [pytest.mark.fast]


class _SpyCamera:
    def __init__(self, calls: list[str], name: str) -> None:
        self._calls = calls
        self._name = name

    def use(self) -> None:
        self._calls.append(f"{self._name}.use")


class _CameraControllerSpy:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self.gui_camera = _SpyCamera(calls, "gui")

    def initialize_window_cameras(self) -> None:
        self._calls.append("camera.initialize")

    def sync_gui_camera_to_window(self) -> None:
        self._calls.append("camera.sync_gui")

    def use_gui_camera(self) -> None:
        self._calls.append("camera.use_gui")
        self.gui_camera.use()


class _DrawSpy:
    active = False

    def __init__(self, calls: list[str], name: str) -> None:
        self._calls = calls
        self._name = name

    def draw(self) -> None:
        self._calls.append(f"{self._name}.draw")

    def draw_world(self) -> None:
        self._calls.append(f"{self._name}.draw_world")

    def draw_overlay(self) -> None:
        self._calls.append(f"{self._name}.draw_overlay")


class _RenderQueueSpy:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def begin_frame(self) -> None:
        self._calls.append("render_queue.begin_frame")

    def finalize(self, _perf_stats: Any) -> None:
        self._calls.append("render_queue.finalize")


class _PostProcessSpy:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def begin(self, _window: Any) -> None:
        self._calls.append("post_process.begin")

    def end(self, _window: Any) -> None:
        self._calls.append("post_process.end")


def _window(calls: list[str], *, menu_visible: bool) -> SimpleNamespace:
    editor = _DrawSpy(calls, "editor")
    editor.active = False
    return SimpleNamespace(
        clear=lambda: calls.append("window.clear"),
        camera=_SpyCamera(calls, "world"),
        camera_controller=_CameraControllerSpy(calls),
        render_queue=None,
        perf_stats=None,
        lighting=None,
        scene_controller=_DrawSpy(calls, "scene"),
        particle_manager=_DrawSpy(calls, "particles"),
        editor_controller=editor,
        fog_overlay=None,
        post_process_pipeline=None,
        show_debug=False,
        ui_controller=_DrawSpy(calls, "ui"),
        ai_debug_overlay_enabled=False,
        engine_config=SimpleNamespace(debug_mode=False),
        main_menu_overlay=SimpleNamespace(visible=menu_visible),
    )


def test_main_menu_visible_suppresses_world_draws_and_fog_lifecycle_stays_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    window = _window(calls, menu_visible=True)
    window.render_queue = _RenderQueueSpy(calls)
    window.post_process_pipeline = _PostProcessSpy(calls)
    window.fog_overlay = _DrawSpy(calls, "fog")

    monkeypatch.setattr(tick, "_apply_editor_sprite_ghosting", lambda _window: (["snapshot"], {"sprite": object()}))
    monkeypatch.setattr(
        tick,
        "_restore_editor_sprite_ghosting",
        lambda snapshots, sprites: calls.append(f"ghost.restore:{bool(snapshots)}:{bool(sprites)}"),
    )

    tick.on_draw(window)

    assert "scene.draw" not in calls
    assert "particles.draw" not in calls
    assert "editor.draw_world" not in calls
    assert "fog.draw_world" not in calls
    assert calls == [
        "camera.sync_gui",
        "post_process.begin",
        "window.clear",
        "world.use",
        "render_queue.begin_frame",
        "ghost.restore:True:True",
        "render_queue.finalize",
        "post_process.end",
        "camera.use_gui",
        "gui.use",
        "ui.draw",
        "editor.draw_overlay",
    ]


def test_main_menu_hidden_preserves_world_draw_order() -> None:
    calls: list[str] = []
    window = _window(calls, menu_visible=False)

    tick.on_draw(window)

    assert calls == [
        "camera.sync_gui",
        "window.clear",
        "world.use",
        "scene.draw",
        "particles.draw",
        "editor.draw_world",
        "camera.use_gui",
        "gui.use",
        "ui.draw",
        "editor.draw_overlay",
    ]


def test_ui_still_draws_while_main_menu_is_visible() -> None:
    calls: list[str] = []
    window = _window(calls, menu_visible=True)

    tick.on_draw(window)

    assert "ui.draw" in calls
    assert "scene.draw" not in calls


def test_main_menu_draws_full_screen_cover_before_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.ui_overlays.main_menu_overlay as main_menu_module

    rects: list[dict[str, Any]] = []
    outlines: list[tuple[Any, ...]] = []
    text_calls: list[dict[str, Any]] = []

    class _TextSpy:
        def __init__(self, **kwargs: Any) -> None:
            text_calls.append(kwargs)

        def draw(self) -> None:
            return

    monkeypatch.setattr(main_menu_module, "_draw_rectangle_filled", lambda **kwargs: rects.append(kwargs))
    monkeypatch.setattr(main_menu_module, "_draw_tb_rectangle_outline", lambda *args, **_kwargs: outlines.append(args))
    monkeypatch.setattr(main_menu_module.optional_arcade.arcade, "Text", _TextSpy)

    window = SimpleNamespace(width=1280, height=720, paused=False)
    overlay = MainMenuOverlay(window)
    overlay.visible = True
    overlay.state = "project_browser"
    overlay._cache_valid = True
    overlay._text_lines = []

    overlay.draw()

    assert rects[0] == {
        "center_x": 640.0,
        "center_y": 360.0,
        "width": 1280,
        "height": 720,
        "color": (8, 10, 14, 255),
    }
    assert rects[1]["width"] == 720.0
    assert rects[1]["height"] > 0.0
    assert rects[1]["color"] == (22, 28, 36, 245)
    assert outlines
    assert any(call["text"] == "MESH" for call in text_calls)
