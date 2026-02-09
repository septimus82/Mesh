"""
Integration tests for scene transition policy wiring.
"""
from types import SimpleNamespace

from engine.game_runtime import scene_flow


class DummySceneController:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.current_scene_path = "scenes/a.json"

    def request_scene_change(self, scene_path: str) -> None:
        self.calls.append(("request", scene_path))

    def queue_scene_change(self, scene_path: str, spawn_id: str | None = None) -> None:
        self.calls.append(("queue", scene_path, spawn_id))


class DummyEditor:
    def __init__(self, *, active: bool, dirty: bool) -> None:
        self.active = active
        self.dirty_state = SimpleNamespace(is_dirty=dirty)
        self.confirm_calls: list[str] = []

    def confirm_unsaved_changes(self, reason: str, action) -> bool:  # noqa: ANN001
        self.confirm_calls.append(reason)
        return True


class DummyWindow:
    def __init__(self, editor=None) -> None:
        self.scene_controller = DummySceneController()
        if editor is not None:
            self.editor_controller = editor


def test_runtime_path_ignores_editor_checks():
    window = DummyWindow()
    scene_flow.request_scene_change(window, "scenes/b.json")
    assert window.scene_controller.calls == [("request", "scenes/b.json")]


def test_editor_dirty_blocks_scene_change():
    editor = DummyEditor(active=True, dirty=True)
    window = DummyWindow(editor=editor)
    scene_flow.request_scene_change(window, "scenes/b.json")
    assert editor.confirm_calls == ["Switch Scene"]
    assert window.scene_controller.calls == []


def test_editor_clean_allows_scene_change():
    editor = DummyEditor(active=True, dirty=False)
    window = DummyWindow(editor=editor)
    scene_flow.request_scene_change(window, "scenes/b.json")
    assert editor.confirm_calls == []
    assert window.scene_controller.calls == [("request", "scenes/b.json")]


def test_queue_scene_change_respects_policy():
    editor = DummyEditor(active=True, dirty=True)
    window = DummyWindow(editor=editor)
    scene_flow.queue_scene_change(window, "scenes/b.json", spawn_id="default")
    assert editor.confirm_calls == ["Switch Scene"]
    assert window.scene_controller.calls == []
