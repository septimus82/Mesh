import builtins
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import arcade

import engine.editor.input_router as input_router
from engine.config import EngineConfig
from engine.editor.editor_overlay_controller import EditorOverlayController
from engine.editor_controller import EditorModeController


class MockWindow:
    def __init__(self):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.paused = False
        self.scene_controller = MagicMock()
        self.screen_to_world = MagicMock(return_value=(100, 100))

def test_editor_toggle():
    window = MockWindow()
    controller = EditorModeController(window)

    assert not controller.active
    assert not window.paused

    controller.toggle()
    assert controller.active
    assert window.paused

    controller.toggle()
    assert not controller.active
    assert not window.paused

def test_editor_selection():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True

    # Mock sprite
    sprite = MagicMock(spec=arcade.Sprite)
    sprite.collides_with_point.return_value = True
    sprite.center_x = 100
    sprite.center_y = 100
    sprite.mesh_name = "TestEntity"

    window.scene_controller.all_sprites = [sprite]

    # Click at 100, 100
    controller.handle_mouse_click(100, 100, arcade.MOUSE_BUTTON_LEFT, 0)

    assert controller.selected_entity == sprite

def test_editor_nudge():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True

    sprite = MagicMock(spec=arcade.Sprite)
    sprite.center_x = 100
    sprite.center_y = 100
    controller.selected_entity = sprite

    controller.nudge_selected(10, 0)

    window.scene_controller._apply_entity_mutation.assert_called_with(
        sprite, x=110, y=100
    )

def test_editor_save():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    window.scene_controller.current_scene_path = "test_scene.json"
    window.scene_controller.build_scene_snapshot.return_value = {"entities": []}

    with patch("engine.editor_runtime.ops.json_io.write_json_atomic") as mock_write:
        controller.save_current_scene()
        mock_write.assert_called_with("test_scene.json", {"entities": []})


def test_editor_controller_instantiates_with_creator_mode():
    controller = EditorModeController(MockWindow())

    assert hasattr(controller, "creator_mode")


def test_editor_overlay_draw_inactive_creator_mode_does_not_raise():
    editor = _overlay_editor(creator_active=False)

    EditorOverlayController(editor).draw_overlay()


def test_editor_overlay_draw_creator_mode_renderer_import_failure_does_not_raise(monkeypatch):
    editor = _overlay_editor(creator_active=True)
    original_import = builtins.__import__

    def failing_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "engine.editor.creator_mode.creator_overlay_renderer":
            raise RuntimeError("renderer import failed")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", failing_import)

    EditorOverlayController(editor).draw_overlay()


def test_creator_mode_toggle_key_false_when_f5_missing(monkeypatch):
    monkeypatch.setattr(input_router.optional_arcade, "arcade", SimpleNamespace(key=SimpleNamespace()))

    assert input_router._is_creator_mode_toggle_key(65474, 0) is False


def test_creator_mode_toggle_key_false_when_key_namespace_missing(monkeypatch):
    monkeypatch.setattr(input_router.optional_arcade, "arcade", SimpleNamespace())

    assert input_router._is_creator_mode_toggle_key(65474, 0) is False


def test_creator_mode_toggle_key_false_when_arcade_missing(monkeypatch):
    monkeypatch.setattr(input_router.optional_arcade, "arcade", None)

    assert input_router._is_creator_mode_toggle_key(65474, 0) is False


def test_creator_mode_toggle_key_requires_shift_and_ignores_lock_key_modifiers():
    import engine.optional_arcade as optional_arcade

    key = optional_arcade.arcade.key
    caps = int(getattr(key, "MOD_CAPSLOCK", 0) or 0)
    num = int(getattr(key, "MOD_NUMLOCK", 0) or 0)
    scroll = int(getattr(key, "MOD_SCROLLLOCK", 0) or 0)

    assert input_router._is_creator_mode_toggle_key(key.F5, 0) is False
    assert input_router._is_creator_mode_toggle_key(key.F5, key.MOD_SHIFT) is True
    assert input_router._is_creator_mode_toggle_key(key.F5, key.MOD_SHIFT | caps) is True
    assert input_router._is_creator_mode_toggle_key(key.F5, key.MOD_SHIFT | num) is True
    assert input_router._is_creator_mode_toggle_key(key.F5, key.MOD_SHIFT | scroll) is True
    assert input_router._is_creator_mode_toggle_key(key.F5, key.MOD_SHIFT | caps | num) is True


def test_creator_mode_toggle_key_false_when_ctrl_held():
    import engine.optional_arcade as optional_arcade

    assert (
        input_router._is_creator_mode_toggle_key(
            optional_arcade.arcade.key.F5,
            optional_arcade.arcade.key.MOD_SHIFT | optional_arcade.arcade.key.MOD_CTRL,
        )
        is False
    )


def test_editor_overlay_draw_calls_creator_renderer_when_active(monkeypatch):
    calls: list[object] = []
    editor = _overlay_editor(creator_active=True)
    editor.creator_mode_snapshot = lambda: SimpleNamespace(active=True)

    def _record_draw(ed: object) -> None:
        calls.append(ed)

    monkeypatch.setattr(
        "engine.editor.creator_mode.creator_overlay_renderer.draw_creator_overlay",
        _record_draw,
    )

    EditorOverlayController(editor).draw_overlay()

    assert calls == [editor]


def _overlay_editor(*, creator_active: bool):
    return SimpleNamespace(
        active=True,
        creator_mode=SimpleNamespace(active=creator_active),
        drain_main_thread_dispatcher=lambda: None,
        drain_live_bridge=lambda: None,
        build=SimpleNamespace(tick=lambda: None),
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        _tick_workspace_autosave=lambda: None,
        _update_status=lambda: None,
        debug_overlay=SimpleNamespace(draw_debug_overlay=lambda _text: None),
        _overlay_text_obj=None,
        palette_active=False,
        hierarchy=SimpleNamespace(draw_hierarchy_panel=lambda: None),
        dialogue_panel_active=False,
        animation=SimpleNamespace(draw_animation_panel_if_active=lambda: None),
        tile=SimpleNamespace(draw_tile_panel_if_active=lambda: None),
        unsaved_confirm=SimpleNamespace(is_open=False),
        tour=SimpleNamespace(is_active=False),
        panels=SimpleNamespace(draw_panels=lambda: None),
        window=SimpleNamespace(width=1280, height=720),
    )
