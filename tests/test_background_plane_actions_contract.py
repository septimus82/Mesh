"""Contract tests for background plane editor actions."""

from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_actions import get_editor_actions, run_editor_action


class _StubSceneController:
    def __init__(self, payload: dict) -> None:
        self._loaded_scene_data = payload
        self._background_planes = []
        self._background_plane_texture_cache: dict[str, object] = {}


class _StubEditor:
    def __init__(self) -> None:
        self.dirty_calls = 0
        self.undo_stack: list[dict[str, object]] = []
        self.redo_stack: list[dict[str, object]] = []

    def _mark_dirty(self) -> None:
        self.dirty_calls += 1

    def _push_command(self, cmd: dict[str, object]) -> None:
        if "label" not in cmd:
            action_id = cmd.get("action_id") if isinstance(cmd.get("action_id"), str) else ""
            detail = cmd.get("detail") if isinstance(cmd.get("detail"), dict) else None
            if action_id:
                from engine.editor.history_label_model import format_history_entry

                cmd["label"] = format_history_entry(action_id, "", detail)
        self.undo_stack.append(cmd)
        self.redo_stack.clear()


class _StubWindow:
    def __init__(self, payload: dict) -> None:
        self.scene_controller = _StubSceneController(payload)
        self.background_plane_editor_state = SimpleNamespace(selected_plane_id="")
        self.editor_controller = _StubEditor()


def _find_action_ids(prefix: str) -> list[str]:
    return [action.id for action in get_editor_actions(None, None) if action.id.startswith(prefix)]


def test_background_plane_actions_registered_and_stable_order() -> None:
    expected = [
        "editor.background_planes.add",
        "editor.background_planes.duplicate",
        "editor.background_planes.remove",
        "editor.background_planes.move_up",
        "editor.background_planes.move_down",
        "editor.background_planes.move_top",
        "editor.background_planes.move_bottom",
        "editor.background_planes.move_to_index",
        "editor.background_planes.select_prev",
        "editor.background_planes.select_next",
        "editor.background_planes.toggle_repeat_x",
        "editor.background_planes.toggle_repeat_y",
    ]
    assert _find_action_ids("editor.background_planes.") == expected


def test_background_plane_actions_disabled_without_selection() -> None:
    window = _StubWindow({"background_planes": []})
    actions = get_editor_actions(window.editor_controller, window)
    by_id = {action.id: action for action in actions}

    assert by_id["editor.background_planes.add"].enabled(window.editor_controller, window) is True
    assert by_id["editor.background_planes.duplicate"].enabled(window.editor_controller, window) is False
    assert by_id["editor.background_planes.remove"].enabled(window.editor_controller, window) is False
    assert by_id["editor.background_planes.move_up"].enabled(window.editor_controller, window) is False
    assert by_id["editor.background_planes.move_down"].enabled(window.editor_controller, window) is False
    assert by_id["editor.background_planes.select_prev"].enabled(window.editor_controller, window) is False
    assert by_id["editor.background_planes.select_next"].enabled(window.editor_controller, window) is False
    assert by_id["editor.background_planes.toggle_repeat_x"].enabled(window.editor_controller, window) is False
    assert by_id["editor.background_planes.toggle_repeat_y"].enabled(window.editor_controller, window) is False


def test_background_plane_action_shortcuts_stable() -> None:
    actions = get_editor_actions(None, None)
    by_id = {action.id: action for action in actions}

    assert by_id["editor.background_planes.add"].shortcut == "Ctrl+Alt+B"
    assert by_id["editor.background_planes.duplicate"].shortcut == "Ctrl+Alt+D"
    assert by_id["editor.background_planes.remove"].shortcut == "Ctrl+Alt+Backspace"
    assert by_id["editor.background_planes.move_up"].shortcut == "Alt+PageUp"
    assert by_id["editor.background_planes.move_down"].shortcut == "Alt+PageDown"
    assert by_id["editor.background_planes.select_prev"].shortcut == "Ctrl+Alt+PageUp"
    assert by_id["editor.background_planes.select_next"].shortcut == "Ctrl+Alt+PageDown"
    assert by_id["editor.background_planes.toggle_repeat_x"].shortcut == "Ctrl+Alt+X"
    assert by_id["editor.background_planes.toggle_repeat_y"].shortcut == "Ctrl+Alt+Y"


def test_background_plane_action_keywords_searchable() -> None:
    actions = get_editor_actions(None, None)
    by_id = {action.id: action for action in actions}

    for action_id in (
        "editor.background_planes.add",
        "editor.background_planes.duplicate",
        "editor.background_planes.remove",
        "editor.background_planes.move_up",
        "editor.background_planes.move_down",
        "editor.background_planes.select_prev",
        "editor.background_planes.select_next",
    ):
        keywords = set(by_id[action_id].keywords)
        assert "parallax" in keywords
        assert "plane" in keywords

    for action_id in (
        "editor.background_planes.toggle_repeat_x",
        "editor.background_planes.toggle_repeat_y",
    ):
        keywords = set(by_id[action_id].keywords)
        assert "tiling" in keywords
        assert "repeat" in keywords


def test_toggle_tiling_x_y_mutates_flags_deterministically() -> None:
    payload = {
        "background_planes": [
            {"id": "plane_001", "asset_path": "assets/bg.png", "repeat_x": False, "repeat_y": True},
        ]
    }
    window = _StubWindow(payload)
    window.background_plane_editor_state.selected_plane_id = "plane_001"

    assert run_editor_action("editor.background_planes.toggle_repeat_x", window.editor_controller, window) is True
    updated = window.scene_controller._loaded_scene_data
    plane = updated["background_planes"][0]
    assert plane["repeat_x"] is True
    assert plane["repeat_y"] is True

    assert run_editor_action("editor.background_planes.toggle_repeat_y", window.editor_controller, window) is True
    updated = window.scene_controller._loaded_scene_data
    plane = updated["background_planes"][0]
    assert plane["repeat_x"] is True
    assert plane["repeat_y"] is False


def test_add_duplicate_remove_via_actions_calls_model_helpers_correctly() -> None:
    window = _StubWindow({})
    assert run_editor_action("editor.background_planes.add", window.editor_controller, window) is True
    payload = window.scene_controller._loaded_scene_data
    assert len(payload["background_planes"]) == 1
    new_id = payload["background_planes"][0]["id"]
    assert new_id == "plane_001"
    assert window.background_plane_editor_state.selected_plane_id == new_id

    assert run_editor_action("editor.background_planes.duplicate", window.editor_controller, window) is True
    payload = window.scene_controller._loaded_scene_data
    ids = [entry["id"] for entry in payload["background_planes"]]
    assert ids == ["plane_001", "plane_001_copy_001"]
    assert window.background_plane_editor_state.selected_plane_id == "plane_001_copy_001"

    assert run_editor_action("editor.background_planes.remove", window.editor_controller, window) is True
    payload = window.scene_controller._loaded_scene_data
    ids = [entry["id"] for entry in payload["background_planes"]]
    assert ids == ["plane_001"]
    assert window.background_plane_editor_state.selected_plane_id == ""


def test_background_plane_actions_push_labeled_history_entries() -> None:
    payload = {
        "background_planes": [
            {"id": "plane_001", "asset_path": "assets/bg.png", "repeat_x": False, "repeat_y": True},
        ]
    }
    window = _StubWindow(payload)
    window.background_plane_editor_state.selected_plane_id = "plane_001"

    assert run_editor_action("editor.background_planes.toggle_repeat_x", window.editor_controller, window) is True
    assert len(window.editor_controller.undo_stack) == 1
    cmd = window.editor_controller.undo_stack[0]
    assert cmd.get("action_id") == "editor.background_planes.toggle_repeat_x"
    assert isinstance(cmd.get("label"), str)


def test_plane_selection_next_prev_cycles_deterministically() -> None:
    payload = {
        "background_planes": [
            {"id": "b", "asset_path": "b.png", "render_layer": 1},
            {"id": "a", "asset_path": "a.png", "render_layer": 0},
            {"id": "c", "asset_path": "c.png", "render_layer": 1},
        ]
    }
    window = _StubWindow(payload)
    window.background_plane_editor_state.selected_plane_id = "b"

    assert run_editor_action("editor.background_planes.select_next", window.editor_controller, window) is True
    assert window.background_plane_editor_state.selected_plane_id == "c"
    assert window.editor_controller.dirty_calls == 0

    assert run_editor_action("editor.background_planes.select_next", window.editor_controller, window) is True
    assert window.background_plane_editor_state.selected_plane_id == "a"
    assert window.editor_controller.dirty_calls == 0

    assert run_editor_action("editor.background_planes.select_prev", window.editor_controller, window) is True
    assert window.background_plane_editor_state.selected_plane_id == "c"
    assert window.editor_controller.dirty_calls == 0
