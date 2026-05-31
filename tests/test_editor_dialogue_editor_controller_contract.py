from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_dialogue_editor_controller import EditorDialogueEditorController

pytestmark = [pytest.mark.fast]


def _editor(tmp_path: Path, overlay: object | None = None) -> SimpleNamespace:
    feedback_calls: list[tuple[str, str]] = []
    return SimpleNamespace(
        window=SimpleNamespace(dialogue_editor_overlay=overlay),
        feedback=SimpleNamespace(
            error=lambda message: feedback_calls.append(("error", str(message))),
            info=lambda message: feedback_calls.append(("info", str(message))),
        ),
        _get_repo_root=lambda: tmp_path,
        feedback_calls=feedback_calls,
    )


class _SelectedNodeOverlay:
    def __init__(self, node_id: str | None) -> None:
        self._node_id = node_id

    def selected_node_id(self) -> str | None:
        return self._node_id

    def set_selected_node_id(self, node_id: str | None) -> None:
        self._node_id = node_id


def _dialogue(dialogue_id: str = "ep02_intro", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": dialogue_id,
        "schema_version": 1,
        "start_node": "start",
        "script": {
            "start": {"speaker": "Mentor", "text": "Hello.", "choices": [{"next": "end", "text": "OK"}]},
            "end": {"speaker": "Mentor", "text": "Goodbye.", "next": None},
        },
    }
    payload.update(overrides)
    return payload


def test_dialogue_editor_controller_enter_cancel_and_dirty(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path))

    controller.enter_edit_mode(_dialogue())
    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() == "id"
    assert controller.is_dirty() is False

    assert controller.handle_dialogue_editor_text_input("_x") is True
    assert controller.is_dirty() is True

    controller.cancel_edit_mode()
    assert controller.is_edit_mode_active() is False
    assert controller.is_dirty() is False
    assert controller.last_error_message() is None


def test_dialogue_editor_controller_deep_copies_script(tmp_path: Path) -> None:
    source = _dialogue()
    controller = EditorDialogueEditorController(_editor(tmp_path))

    controller.enter_edit_mode(source)
    assert controller.edit_buffer is not None
    controller.edit_buffer["script"]["start"]["text"] = "Changed"

    assert source["script"]["start"]["text"] == "Hello."


def test_dialogue_editor_controller_enter_edit_mode_injects_selected_node_inputs(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))

    controller.enter_edit_mode(_dialogue())

    assert set(controller.text_inputs()) == {
        "id",
        "schema_version",
        "start_node",
        "script.start.speaker",
        "script.start.text",
        "script.start.choices.0.text",
        "script.start.choices.0.next",
    }
    assert controller.text_input("script.start.speaker").text == "Mentor"
    assert controller.text_input("script.start.text").text == "Hello."
    assert controller.text_input("script.start.choices.0.text").text == "OK"
    assert controller.text_input("script.start.choices.0.next").text == "end"


def test_dialogue_editor_controller_no_selected_node_keeps_static_inputs(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay(None)))

    controller.enter_edit_mode(_dialogue())

    assert set(controller.text_inputs()) == {"id", "schema_version", "start_node"}


def test_dialogue_editor_controller_linear_node_injects_no_choice_inputs(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("end")))

    controller.enter_edit_mode(_dialogue())

    assert "script.end.speaker" in controller.text_inputs()
    assert "script.end.text" in controller.text_inputs()
    assert not any(".choices." in field for field in controller.text_inputs())


def test_dialogue_editor_controller_cancel_resets_dynamic_node_inputs(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(_dialogue())

    controller.cancel_edit_mode()

    assert set(controller.text_inputs()) == {"id", "schema_version", "start_node"}


def test_dialogue_editor_controller_escape_cancels_edit_mode(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_dialogue())

    assert controller.handle_dialogue_editor_key(optional_arcade.arcade.key.ESCAPE, 0) is True
    assert controller.is_edit_mode_active() is False


def test_dialogue_editor_controller_node_field_change_marks_dirty(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(_dialogue())

    controller.text_input("script.start.text").text = "Changed line."

    assert controller.is_dirty() is True


def test_dialogue_editor_controller_commit_save_replaces_by_original_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import dialogue_editor_model

    monkeypatch.setattr(dialogue_editor_model, "validate_dialogue_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dialogue_editor_model, "save_dialogues", lambda entries, target: saved.append((entries, target)))
    editor = _editor(tmp_path)
    controller = EditorDialogueEditorController(editor)
    controller.enter_edit_mode(_dialogue("old_id"))
    controller.id_input().text = "new_id"

    ok = controller.commit_save([_dialogue("old_id"), _dialogue("other")], tmp_path / "assets" / "data" / "dialogues.json")

    assert ok is True
    assert controller.is_edit_mode_active() is False
    assert saved[0][0][0]["id"] == "new_id"
    assert saved[0][0][1]["id"] == "other"
    assert editor.feedback_calls[-1] == ("info", "Dialogue saved")


def test_dialogue_editor_controller_commit_save_persists_selected_node_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import dialogue_editor_model

    monkeypatch.setattr(dialogue_editor_model, "validate_dialogue_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dialogue_editor_model, "save_dialogues", lambda entries, target: saved.append((entries, target)))
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)
    controller.text_input("script.start.speaker").text = "Guide"
    controller.text_input("script.start.text").text = "Updated."

    ok = controller.commit_save([source], tmp_path / "assets" / "data" / "dialogues.json")

    assert ok is True
    saved_dialogue = saved[0][0][0]
    assert saved_dialogue["script"]["start"]["speaker"] == "Guide"
    assert saved_dialogue["script"]["start"]["text"] == "Updated."
    assert saved_dialogue["script"]["end"] == source["script"]["end"]
    assert saved_dialogue["id"] == "ep02_intro"


def test_dialogue_editor_controller_commit_save_persists_choice_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import dialogue_editor_model

    monkeypatch.setattr(dialogue_editor_model, "validate_dialogue_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dialogue_editor_model, "save_dialogues", lambda entries, target: saved.append((entries, target)))
    source = _dialogue("ep02_intro")
    source["script"]["start"]["choices"].append({"next": "start", "text": "Again"})
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)
    controller.text_input("script.start.choices.1.text").text = "Loop back."
    controller.text_input("script.start.choices.1.next").text = "end"

    ok = controller.commit_save([source], tmp_path / "assets" / "data" / "dialogues.json")

    assert ok is True
    saved_start = saved[0][0][0]["script"]["start"]
    assert saved_start["speaker"] == "Mentor"
    assert saved_start["text"] == "Hello."
    assert saved_start["choices"][0] == {"next": "end", "text": "OK"}
    assert saved_start["choices"][1] == {"next": "end", "text": "Loop back."}


def test_dialogue_editor_controller_add_choice_appends_and_focuses_new_text(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)

    assert controller._add_choice() is True

    choices = controller.edit_buffer["script"]["start"]["choices"]
    assert choices[-1] == {"next": "", "text": ""}
    assert "script.start.choices.1.text" in controller.text_inputs()
    assert "script.start.choices.1.next" in controller.text_inputs()
    assert controller.focused_field() == "script.start.choices.1.text"


def test_dialogue_editor_controller_add_choice_syncs_existing_edits_before_rebuild(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)
    controller.text_input("script.start.choices.0.text").text = "Keep this edit"

    assert controller._add_choice() is True

    choices = controller.edit_buffer["script"]["start"]["choices"]
    assert choices[0]["text"] == "Keep this edit"
    assert choices[1] == {"next": "", "text": ""}


def test_dialogue_editor_controller_add_choice_linear_node_noop(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("end")))
    controller.enter_edit_mode(source)
    before = json.dumps(controller.edit_buffer, sort_keys=True)

    assert controller._add_choice() is False

    assert json.dumps(controller.edit_buffer, sort_keys=True) == before
    assert not any(".choices." in field for field in controller.text_inputs())


def test_dialogue_editor_controller_add_choice_routes_from_edit_mode_action(tmp_path: Path) -> None:
    class _ChoiceActionOverlay(_SelectedNodeOverlay):
        def choice_action_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return "choice.add"

    source = _dialogue("ep02_intro")
    overlay = _ChoiceActionOverlay("start")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))
    controller.enter_edit_mode(source)

    assert controller.handle_dialogue_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer["script"]["start"]["choices"][1] == {"next": "", "text": ""}


def test_dialogue_editor_controller_add_choice_action_ignored_in_view_mode(tmp_path: Path) -> None:
    class _ChoiceActionOverlay(_SelectedNodeOverlay):
        def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
            return None

        def node_id_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return None

        def choice_action_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return "choice.add"

    overlay = _ChoiceActionOverlay("start")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))

    assert controller.handle_dialogue_editor_mouse_click(10.0, 20.0) is False


def test_dialogue_editor_controller_save_after_add_choice_blocks_on_empty_text(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    target.parent.mkdir(parents=True)
    original = '{"dialogues": []}\n'
    target.write_text(original, encoding="utf-8")
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)

    assert controller._add_choice() is True
    ok = controller.commit_save([source], target)

    assert ok is False
    assert controller.last_error_message() == "entry 'ep02_intro': node 'start' choice 1 text is empty"
    assert target.read_text(encoding="utf-8") == original


def test_dialogue_editor_controller_delete_choice_renumbers_survivor_inputs(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    source["script"]["start"]["choices"].append({"next": "start", "text": "Again"})
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)

    assert controller._delete_choice(0) is True

    choices = controller.edit_buffer["script"]["start"]["choices"]
    assert choices == [{"next": "start", "text": "Again"}]
    assert controller.text_input("script.start.choices.0.text").text == "Again"
    assert controller.text_input("script.start.choices.0.next").text == "start"
    assert "script.start.choices.1.text" not in controller.text_inputs()
    assert "script.start.choices.1.next" not in controller.text_inputs()
    assert controller.focused_field() is None


def test_dialogue_editor_controller_delete_choice_syncs_surviving_edit_before_rebuild(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    source["script"]["start"]["choices"].append({"next": "start", "text": "Again"})
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)
    controller.text_input("script.start.choices.1.text").text = "Keep survivor"

    assert controller._delete_choice(0) is True

    assert controller.edit_buffer["script"]["start"]["choices"] == [{"next": "start", "text": "Keep survivor"}]


def test_dialogue_editor_controller_delete_choice_allows_empty_choice_list(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)

    assert controller._delete_choice(0) is True

    start = controller.edit_buffer["script"]["start"]
    assert start["choices"] == []
    assert not any(".choices." in field for field in controller.text_inputs())
    assert controller.focused_field() is None


def test_dialogue_editor_controller_delete_choice_invalid_indices_noop(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)
    before = json.dumps(controller.edit_buffer, sort_keys=True)

    assert controller._delete_choice(-1) is False
    assert controller._delete_choice(4) is False

    assert json.dumps(controller.edit_buffer, sort_keys=True) == before


def test_dialogue_editor_controller_delete_choice_linear_node_noop(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("end")))
    controller.enter_edit_mode(source)
    before = json.dumps(controller.edit_buffer, sort_keys=True)

    assert controller._delete_choice(0) is False

    assert json.dumps(controller.edit_buffer, sort_keys=True) == before


def test_dialogue_editor_controller_delete_choice_save_persists_survivor(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    source = _dialogue("ep02_intro")
    source["script"]["start"]["choices"].append({"next": "start", "text": "Again"})
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)

    assert controller._delete_choice(0) is True
    ok = controller.commit_save([source], target)

    assert ok is True
    loaded = json.loads(target.read_text(encoding="utf-8"))
    start = loaded["dialogues"][0]["script"]["start"]
    assert start["speaker"] == "Mentor"
    assert start["text"] == "Hello."
    assert start["choices"] == [{"next": "start", "text": "Again"}]


def test_dialogue_editor_controller_delete_choice_routes_from_edit_mode_action(tmp_path: Path) -> None:
    class _ChoiceActionOverlay(_SelectedNodeOverlay):
        def choice_action_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return "choice.1.delete"

    source = _dialogue("ep02_intro")
    source["script"]["start"]["choices"].append({"next": "start", "text": "Again"})
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_ChoiceActionOverlay("start")))
    controller.enter_edit_mode(source)

    assert controller.handle_dialogue_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer["script"]["start"]["choices"] == [{"next": "end", "text": "OK"}]


def test_dialogue_editor_controller_delete_choice_action_ignored_in_view_mode(tmp_path: Path) -> None:
    class _ChoiceActionOverlay(_SelectedNodeOverlay):
        def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
            return None

        def node_id_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return None

        def choice_action_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return "choice.0.delete"

    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_ChoiceActionOverlay("start")))

    assert controller.handle_dialogue_editor_mouse_click(10.0, 20.0) is False


def test_dialogue_editor_controller_add_node_generates_collision_free_ids(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    source["script"]["node_1"] = {"speaker": "A", "text": "Existing.", "next": ""}
    overlay = _SelectedNodeOverlay("start")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))
    controller.enter_edit_mode(source)

    assert controller._add_node() is True

    assert "node_2" in controller.edit_buffer["script"]
    assert overlay.selected_node_id() == "node_2"

    semantic_source = _dialogue("ep02_intro")
    semantic_overlay = _SelectedNodeOverlay("start")
    semantic_controller = EditorDialogueEditorController(_editor(tmp_path, overlay=semantic_overlay))
    semantic_controller.enter_edit_mode(semantic_source)

    assert semantic_controller._add_node() is True
    assert semantic_controller._add_node() is True

    assert {"node_1", "node_2"} <= set(semantic_controller.edit_buffer["script"])


def test_dialogue_editor_controller_add_node_selects_and_focuses_new_node(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    overlay = _SelectedNodeOverlay("start")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))
    controller.enter_edit_mode(source)

    assert controller._add_node() is True

    assert controller.edit_buffer["script"]["node_1"] == {"speaker": "", "text": "", "next": ""}
    assert overlay.selected_node_id() == "node_1"
    assert "script.node_1.speaker" in controller.text_inputs()
    assert "script.node_1.text" in controller.text_inputs()
    assert "script.node_1.next" in controller.text_inputs()
    assert controller.focused_field() == "script.node_1.speaker"


def test_dialogue_editor_controller_add_node_syncs_current_node_edits(tmp_path: Path) -> None:
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)
    controller.text_input("script.start.text").text = "Keep node edit"

    assert controller._add_node() is True

    assert controller.edit_buffer["script"]["start"]["text"] == "Keep node edit"


def test_dialogue_editor_controller_add_node_noop_without_edit_mode_or_script_dict(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))

    assert controller._add_node() is False

    source = _dialogue("ep02_intro", script=[])
    controller.enter_edit_mode(source)

    assert controller._add_node() is False


def test_dialogue_editor_controller_add_node_routes_only_in_edit_mode(tmp_path: Path) -> None:
    class _NodeActionOverlay(_SelectedNodeOverlay):
        def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
            return None

        def node_id_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return None

        def node_action_at(self, x: float, y: float) -> str | None:  # noqa: ARG002
            return "node.add"

    overlay = _NodeActionOverlay("start")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))

    assert controller.handle_dialogue_editor_mouse_click(10.0, 20.0) is False

    controller.enter_edit_mode(_dialogue("ep02_intro"))
    assert controller.handle_dialogue_editor_mouse_click(10.0, 20.0) is True

    assert "node_1" in controller.edit_buffer["script"]


def test_dialogue_editor_controller_add_node_save_persists_empty_terminal_node(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)

    assert controller._add_node() is True
    ok = controller.commit_save([source], target)

    assert ok is True
    loaded = json.loads(target.read_text(encoding="utf-8"))
    script = loaded["dialogues"][0]["script"]
    assert script["node_1"] == {"speaker": "", "text": "", "next": ""}
    assert script["start"] == source["script"]["start"]
    assert script["end"] == source["script"]["end"]


def test_dialogue_editor_controller_commit_save_reports_validation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    from engine.editor import dialogue_editor_model

    monkeypatch.setattr(dialogue_editor_model, "validate_dialogue_entries", lambda *_args, **_kwargs: ["id is required"])
    monkeypatch.setattr(dialogue_editor_model, "save_dialogues", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorDialogueEditorController(editor)
    controller.enter_edit_mode(_dialogue("old_id"))

    ok = controller.commit_save([_dialogue("old_id")], tmp_path / "assets" / "data" / "dialogues.json")

    assert ok is False
    assert controller.last_error_message() == "id is required"
    assert editor.feedback_calls[-1] == ("error", "id is required")
    assert saved == []


def test_dialogue_editor_controller_schema_version_persists_as_int(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine.editor import dialogue_editor_model

    monkeypatch.setattr(dialogue_editor_model, "validate_dialogue_entries", lambda *_args, **_kwargs: [])
    target = tmp_path / "assets" / "data" / "dialogues.json"
    controller = EditorDialogueEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_dialogue())
    controller.text_input("schema_version").text = "2"

    ok = controller.commit_save([_dialogue()], target)

    assert ok is True
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["dialogues"][0]["schema_version"] == 2
    assert isinstance(loaded["dialogues"][0]["schema_version"], int)


def test_dialogue_editor_controller_schema_version_empty_drops_key(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_dialogue())
    record: dict[str, object] = {"id": "x", "schema_version": 1}

    controller._set_field_value(record, "schema_version", "")

    assert "schema_version" not in record


def test_dialogue_editor_controller_schema_version_non_int_stored_as_text(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_dialogue())
    record: dict[str, object] = {"id": "x", "schema_version": 1}

    controller._set_field_value(record, "schema_version", "abc")

    assert record["schema_version"] == "abc"


def test_dialogue_editor_controller_dotted_script_field_round_trips(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path))
    record = _dialogue()

    controller._set_field_value(record, "script.start.text", "Round trip.")

    assert controller._get_field_value(record, "script.start.text") == "Round trip."


def test_dialogue_editor_controller_dotted_choice_field_round_trips(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path))
    record = _dialogue()

    controller._set_field_value(record, "script.start.choices.0.next", "start")

    assert controller._get_field_value(record, "script.start.choices.0.next") == "start"


def test_dialogue_editor_controller_empty_choice_text_blocks_save_and_preserves_file(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    target.parent.mkdir(parents=True)
    original = '{"dialogues": []}\n'
    target.write_text(original, encoding="utf-8")
    source = _dialogue("ep02_intro")
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=_SelectedNodeOverlay("start")))
    controller.enter_edit_mode(source)
    controller.text_input("script.start.choices.0.text").text = ""

    ok = controller.commit_save([source], target)

    assert ok is False
    assert controller.last_error_message() == "entry 'ep02_intro': node 'start' choice 0 text is empty"
    assert target.read_text(encoding="utf-8") == original


def test_dialogue_editor_controller_script_preserved_after_id_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_entries: list[list[dict[str, object]]] = []
    from engine.editor import dialogue_editor_model

    monkeypatch.setattr(dialogue_editor_model, "validate_dialogue_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dialogue_editor_model, "save_dialogues", lambda entries, _target: saved_entries.append(entries))
    controller = EditorDialogueEditorController(_editor(tmp_path))
    source = _dialogue("original_id")
    controller.enter_edit_mode(source)
    controller.id_input().text = "changed_id"

    controller.commit_save([source], tmp_path / "assets" / "data" / "dialogues.json")

    assert saved_entries[0][0]["script"] == source["script"]


def test_dialogue_editor_controller_focus_cycle(tmp_path: Path) -> None:
    controller = EditorDialogueEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_dialogue())

    assert controller.focused_field() == "id"
    for expected in ("schema_version", "start_node", "id"):
        controller.cycle_focus_forward()
        assert controller.focused_field() == expected


def test_dialogue_editor_controller_row_selection_view_mode_returns_true(tmp_path: Path) -> None:
    class _StubOverlay:
        def __init__(self) -> None:
            self.selected_calls: list[int] = []

        def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
            return 1

        def set_selected_index(self, index: int) -> bool:
            self.selected_calls.append(index)
            return True

    overlay = _StubOverlay()
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))

    result = controller.handle_dialogue_editor_mouse_click(10.0, 50.0)

    assert result is True
    assert overlay.selected_calls == [1]


def test_dialogue_editor_controller_edit_mode_does_not_select_rows(tmp_path: Path) -> None:
    class _StubOverlay:
        def __init__(self) -> None:
            self.selected_calls: list[int] = []

        def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
            return 0

        def set_selected_index(self, index: int) -> bool:
            self.selected_calls.append(index)
            return True

        def try_click_widget(self, x: float, y: float) -> None:  # noqa: ARG002
            return None

    overlay = _StubOverlay()
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))
    controller.enter_edit_mode(_dialogue())

    controller.handle_dialogue_editor_mouse_click(10.0, 50.0)

    assert overlay.selected_calls == []


def test_dialogue_editor_controller_edit_button_enters_edit_mode(tmp_path: Path) -> None:
    from engine.ui_overlays.widgets import Rect

    class _StubOverlay:
        def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
            return None

        def selected_dialogue_dict(self) -> dict[str, object]:
            return _dialogue()

        def all_dialogue_dicts(self) -> list[dict[str, object]]:
            return [_dialogue()]

    overlay = _StubOverlay()
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))
    controller.set_button_rects({"edit": Rect(x=0.0, y=40.0, width=100.0, height=20.0)})

    result = controller.handle_dialogue_editor_mouse_click(10.0, 50.0)

    assert result is True
    assert controller.is_edit_mode_active() is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["id"] == "ep02_intro"


def test_dialogue_editor_controller_empty_view_mode_click_returns_false(tmp_path: Path) -> None:
    class _StubOverlay:
        def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
            return None

    overlay = _StubOverlay()
    controller = EditorDialogueEditorController(_editor(tmp_path, overlay=overlay))

    result = controller.handle_dialogue_editor_mouse_click(10.0, 50.0)

    assert result is False
    assert controller.is_edit_mode_active() is False
