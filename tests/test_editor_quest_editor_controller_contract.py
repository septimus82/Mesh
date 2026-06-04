from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_quest_editor_controller import EditorQuestEditorController, _next_stage_id

pytestmark = [pytest.mark.fast]


def _editor(tmp_path: Path, overlay: object | None = None) -> SimpleNamespace:
    feedback_calls: list[tuple[str, str]] = []
    return SimpleNamespace(
        window=SimpleNamespace(quest_editor_overlay=overlay),
        feedback=SimpleNamespace(
            error=lambda message: feedback_calls.append(("error", str(message))),
            info=lambda message: feedback_calls.append(("info", str(message))),
        ),
        _get_repo_root=lambda: tmp_path,
        feedback_calls=feedback_calls,
    )


def _quest(quest_id: str = "showcase_tour", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": quest_id,
        "title": "Tour of the Mesh",
        "description": "Visit the demonstration rooms.",
        "type": "tour",
        "start_toast": "Tour started",
        "complete_toast": "Tour complete",
        "stages": [{"id": "intro", "title": "Talk", "text": "Talk to the guide."}],
        "reward": {"inc_counters": {"developer_badge": 1}},
        "requires_flags": ["intro_complete"],
    }
    payload.update(overrides)
    return payload


def test_quest_editor_controller_enter_cancel_and_dirty(tmp_path: Path) -> None:
    controller = EditorQuestEditorController(_editor(tmp_path))

    controller.enter_edit_mode(_quest())
    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() == "id"
    assert controller.is_dirty() is False

    assert controller.handle_quest_editor_text_input("_x") is True
    assert controller.is_dirty() is True

    controller.cancel_edit_mode()
    assert controller.is_edit_mode_active() is False
    assert controller.is_dirty() is False
    assert controller.last_error_message() is None


def test_quest_editor_controller_deep_copies_nested_complex_fields(tmp_path: Path) -> None:
    source = _quest()
    controller = EditorQuestEditorController(_editor(tmp_path))

    controller.enter_edit_mode(source)
    assert controller.edit_buffer is not None
    controller.edit_buffer["stages"][0]["title"] = "Changed"

    assert source["stages"][0]["title"] == "Talk"


def test_quest_editor_controller_enter_unfocuses_without_saving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[object] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "save_quests", lambda *args, **kwargs: saved.append((args, kwargs)))
    controller = EditorQuestEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_quest())

    assert controller.handle_quest_editor_key(optional_arcade.arcade.key.ENTER, 0) is True

    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() is None
    assert saved == []


def test_quest_editor_controller_escape_cancels_edit_mode(tmp_path: Path) -> None:
    controller = EditorQuestEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_quest())

    assert controller.handle_quest_editor_key(optional_arcade.arcade.key.ESCAPE, 0) is True

    assert controller.is_edit_mode_active() is False


def test_quest_editor_controller_commit_save_replaces_by_original_id_after_id_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "validate_quest_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(quest_editor_model, "save_quests", lambda quests, target: saved.append((quests, target)))
    editor = _editor(tmp_path)
    controller = EditorQuestEditorController(editor)
    controller.enter_edit_mode(_quest("old_id"))
    controller.id_input().text = "new_id"

    ok = controller.commit_save([_quest("old_id"), _quest("other")], tmp_path / "assets" / "data" / "quests.json")

    assert ok is True
    assert controller.is_edit_mode_active() is False
    assert saved[0][0][0]["id"] == "new_id"
    assert saved[0][0][1]["id"] == "other"
    assert editor.feedback_calls[-1] == ("info", "Quest saved")


def test_quest_editor_controller_commit_save_reports_validation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "validate_quest_entries", lambda *_args, **_kwargs: ["title is required"])
    monkeypatch.setattr(quest_editor_model, "save_quests", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorQuestEditorController(editor)
    controller.enter_edit_mode(_quest("old_id"))
    controller.text_input("title").text = ""

    ok = controller.commit_save([_quest("old_id")], tmp_path / "assets" / "data" / "quests.json")

    assert ok is False
    assert controller.last_error_message() == "title is required"
    assert editor.feedback_calls[-1] == ("error", "title is required")
    assert saved == []


def test_quest_editor_controller_focus_cycle_forward_backward_wraps(tmp_path: Path) -> None:
    controller = EditorQuestEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_quest())

    assert controller.focused_field() == "id"
    for expected in ("title", "description", "type", "start_toast", "complete_toast", "id"):
        controller.cycle_focus_forward()
        assert controller.focused_field() == expected
        assert controller.text_input(expected).focused is True

    controller.cycle_focus_backward()
    assert controller.focused_field() == "complete_toast"
    assert controller.text_input("complete_toast").focused is True


def test_quest_editor_controller_focus_cycle_noops_when_not_editing(tmp_path: Path) -> None:
    controller = EditorQuestEditorController(_editor(tmp_path))

    controller.cycle_focus_forward()
    controller.cycle_focus_backward()

    assert controller.focused_field() is None


def test_quest_editor_controller_text_input_updates_focused_field(tmp_path: Path) -> None:
    controller = EditorQuestEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_quest())
    controller.cycle_focus_forward()

    assert controller.focused_field() == "title"
    assert controller.handle_quest_editor_text_input("_x") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["title"] == "Tour of the Mesh_x"


@pytest.mark.parametrize("field", ("description", "type", "start_toast", "complete_toast"))
def test_quest_editor_controller_strips_empty_optional_fields_on_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "validate_quest_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(quest_editor_model, "save_quests", lambda quests, _target: saved.append(quests))
    controller = EditorQuestEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_quest("old_id"))
    controller.text_input(field).text = " "

    assert controller.commit_save([_quest("old_id")], tmp_path / "assets" / "data" / "quests.json") is True

    assert field not in saved[0][0]


def test_quest_editor_controller_dirty_compare_treats_empty_optional_as_omitted(tmp_path: Path) -> None:
    source = _quest(description="")
    source.pop("description")
    controller = EditorQuestEditorController(_editor(tmp_path))

    controller.enter_edit_mode(source)
    controller.text_input("description").text = ""

    assert controller.is_dirty() is False


def test_quest_editor_controller_required_empty_title_stays_for_validator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_candidate: list[list[dict[str, object]]] = []
    from engine.editor import quest_editor_model

    def _validate(quests: list[dict[str, object]], _target: Path) -> list[str]:
        saved_candidate.append(quests)
        return ["title is required"]

    monkeypatch.setattr(quest_editor_model, "validate_quest_entries", _validate)
    monkeypatch.setattr(quest_editor_model, "save_quests", lambda *_args, **_kwargs: None)
    controller = EditorQuestEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_quest("old_id"))
    controller.text_input("title").text = ""

    assert controller.commit_save([_quest("old_id")], tmp_path / "assets" / "data" / "quests.json") is False
    assert saved_candidate[0][0]["title"] == ""


def test_quest_editor_controller_uses_model_default_path_for_button_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[Path] = []
    from engine.editor import quest_editor_model
    from engine.ui_overlays.widgets import Rect

    overlay = SimpleNamespace(
        selected_quest_dict=lambda: _quest("old_id"),
        all_quest_dicts=lambda: [_quest("old_id")],
        reload_model=lambda: None,
    )
    editor = _editor(tmp_path, overlay)
    controller = EditorQuestEditorController(editor)
    controller.enter_edit_mode(_quest("old_id"))
    controller.set_button_rects({"save": Rect(0.0, 0.0, 20.0, 20.0)})
    monkeypatch.setattr(quest_editor_model, "validate_quest_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(quest_editor_model, "save_quests", lambda _quests, target: saved.append(target))

    assert controller.handle_quest_editor_mouse_click(10.0, 10.0) is True

    assert saved == [tmp_path / quest_editor_model.DEFAULT_QUESTS_FILE_PATH]


def test_quest_editor_controller_view_mode_row_click_selects(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: 1,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))

    assert controller.handle_quest_editor_mouse_click(10.0, 10.0) is True

    assert selected == [1]
    assert controller.is_edit_mode_active() is False


def test_quest_editor_controller_view_mode_row_miss_keeps_edit_button_working(tmp_path: Path) -> None:
    from engine.ui_overlays.widgets import Rect

    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        selected_quest_dict=lambda: _quest("old_id"),
    )
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.set_button_rects({"edit": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_quest_editor_mouse_click(10.0, 10.0) is True

    assert controller.is_edit_mode_active() is True


def test_quest_editor_controller_edit_mode_skips_row_selection(tmp_path: Path) -> None:
    from engine.ui_overlays.widgets import Rect

    selected: list[int] = []
    row_hit_calls: list[tuple[float, float]] = []

    def _row_index_at(x: float, y: float) -> int:
        row_hit_calls.append((x, y))
        return 1

    overlay = SimpleNamespace(
        row_index_at=_row_index_at,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest("old_id"))
    controller.set_button_rects({"cancel": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_quest_editor_mouse_click(10.0, 10.0) is True

    assert selected == []
    assert row_hit_calls == []
    assert controller.is_edit_mode_active() is False


def test_quest_editor_controller_empty_view_mode_click_falls_through(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))

    assert controller.handle_quest_editor_mouse_click(10.0, 10.0) is False

    assert selected == []
    assert controller.is_edit_mode_active() is False


def test_quest_editor_controller_routes_stage_clicks_only_in_view_mode(tmp_path: Path) -> None:
    selected_stages: list[str] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        stage_id_at=lambda _x, _y: "stage_a",
        set_selected_stage_id=lambda stage_id: selected_stages.append(stage_id),
    )
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))

    assert controller.handle_quest_editor_mouse_click(10.0, 10.0) is True
    assert selected_stages == ["stage_a"]

    controller.enter_edit_mode(_quest("old_id"))
    assert controller.handle_quest_editor_mouse_click(10.0, 10.0) is False
    assert selected_stages == ["stage_a"]


def test_quest_editor_controller_stage_title_edit_updates_buffer(tmp_path: Path) -> None:
    overlay = SimpleNamespace(selected_stage_id=lambda: "intro")
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest())

    controller.text_input("stages.0.title").text = "Updated Talk"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["stages"][0]["title"] == "Updated Talk"


def test_quest_editor_controller_stage_text_edit_updates_buffer(tmp_path: Path) -> None:
    overlay = SimpleNamespace(selected_stage_id=lambda: "intro")
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest())

    controller.text_input("stages.0.text").text = "Updated directions."
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["stages"][0]["text"] == "Updated directions."


def test_quest_editor_controller_stage_title_and_text_edit_persist_through_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "save_quests", lambda quests, _target: saved.append(quests))
    overlay = SimpleNamespace(selected_stage_id=lambda: "intro")
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest("old_id"))
    controller.text_input("stages.0.title").text = "Updated Talk"
    controller.text_input("stages.0.text").text = "Updated directions."

    assert controller.commit_save([_quest("old_id")], tmp_path / "assets" / "data" / "quests.json") is True

    assert saved[0][0]["stages"][0]["title"] == "Updated Talk"
    assert saved[0][0]["stages"][0]["text"] == "Updated directions."


def test_quest_editor_controller_no_edit_save_preserves_stage_dicts_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "validate_quest_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(quest_editor_model, "save_quests", lambda quests, _target: saved.append(quests))
    structured_stage = {
        "id": "intro",
        "title": "Talk",
        "text": "Talk to the guide.",
        "complete_on": {"type": "dialogue_choice", "payload": {"choice_id": "done"}},
        "start_on_event": {"type": "scene_loaded"},
        "requirements": {"counters": {"visits": 1}},
        "emit_events_on_complete": [{"type": "quest_stage_done"}],
    }
    textless_stage = {"id": "followup", "title": "Follow Up", "complete_on": {"type": "talked"}}
    quest = _quest("old_id", stages=[copy.deepcopy(structured_stage), copy.deepcopy(textless_stage)])
    original_stages = copy.deepcopy(quest["stages"])
    overlay = SimpleNamespace(selected_stage_id=lambda: "followup")
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(quest)

    assert controller.commit_save([quest], tmp_path / "assets" / "data" / "quests.json") is True

    assert saved[0][0]["stages"] == original_stages
    assert "text" not in saved[0][0]["stages"][1]


def test_quest_editor_controller_empty_stage_title_blocks_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "save_quests", lambda *args, **kwargs: saved.append((args, kwargs)))
    overlay = SimpleNamespace(selected_stage_id=lambda: "intro")
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest("old_id"))
    controller.text_input("stages.0.title").text = ""

    assert controller.commit_save([_quest("old_id")], tmp_path / "assets" / "data" / "quests.json") is False

    assert "must have a 'title'" in (controller.last_error_message() or "")
    assert saved == []


def test_quest_editor_controller_empty_stage_text_is_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "save_quests", lambda quests, _target: saved.append(quests))
    overlay = SimpleNamespace(selected_stage_id=lambda: "intro")
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest("old_id"))
    controller.text_input("stages.0.text").text = ""

    assert controller.commit_save([_quest("old_id")], tmp_path / "assets" / "data" / "quests.json") is True

    assert saved[0][0]["stages"][0]["text"] == ""


def test_quest_editor_controller_add_stage_appends_valid_stage_and_focuses_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    selected_stages: list[str | None] = []
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "save_quests", lambda quests, _target: saved.append(quests))
    overlay = SimpleNamespace(
        selected_stage_id=lambda: selected_stages[-1] if selected_stages else "intro",
        set_selected_stage_id=lambda stage_id: selected_stages.append(stage_id),
    )
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    quest = _quest("old_id")
    controller.enter_edit_mode(quest)

    assert controller._add_stage() is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["stages"][-1] == {"id": "stage_1", "title": "New stage", "text": ""}
    assert selected_stages == ["stage_1"]
    assert controller.focused_field() == "stages.1.title"
    assert "stages.1.text" in controller.text_inputs()

    assert controller.commit_save([quest], tmp_path / "assets" / "data" / "quests.json") is True

    assert saved[0][0]["stages"][-1]["id"] == "stage_1"
    assert saved[0][0]["stages"][-1]["title"] == "New stage"


def test_quest_editor_controller_next_stage_id_skips_explicit_and_fallback_collisions() -> None:
    stages: list[object] = [
        {"id": "stage_1", "title": "Explicit"},
        {"title": "Fallback stage one"},
        {"id": "custom", "title": "Custom"},
        {"title": "Fallback stage three"},
    ]

    assert _next_stage_id(stages) == "stage_2"


def test_quest_editor_controller_delete_stage_reconciles_to_next_then_previous(tmp_path: Path) -> None:
    selected_stages: list[str | None] = ["beta"]
    overlay = SimpleNamespace(
        selected_stage_id=lambda: selected_stages[-1],
        set_selected_stage_id=lambda stage_id: selected_stages.append(stage_id),
    )
    stages = [
        {"id": "alpha", "title": "First"},
        {"id": "beta", "title": "Second"},
        {"id": "gamma", "title": "Third"},
    ]
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest("old_id", stages=copy.deepcopy(stages)))

    assert controller._delete_stage() is True

    assert controller.edit_buffer is not None
    assert [stage["id"] for stage in controller.edit_buffer["stages"]] == ["alpha", "gamma"]
    assert selected_stages[-1] == "gamma"

    selected_stages.append("gamma")
    assert controller._delete_stage() is True

    assert [stage["id"] for stage in controller.edit_buffer["stages"]] == ["alpha"]
    assert selected_stages[-1] == "alpha"


def test_quest_editor_controller_delete_last_stage_leaves_save_blocked_by_validator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    selected_stages: list[str | None] = ["intro"]
    from engine.editor import quest_editor_model

    monkeypatch.setattr(quest_editor_model, "save_quests", lambda *args, **kwargs: saved.append((args, kwargs)))
    overlay = SimpleNamespace(
        selected_stage_id=lambda: selected_stages[-1],
        set_selected_stage_id=lambda stage_id: selected_stages.append(stage_id),
    )
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    quest = _quest("old_id")
    controller.enter_edit_mode(quest)

    assert controller._delete_stage() is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["stages"] == []
    assert selected_stages[-1] is None
    assert controller.commit_save([quest], tmp_path / "assets" / "data" / "quests.json") is False
    assert "must have at least one stage" in (controller.last_error_message() or "")
    assert saved == []


def test_quest_editor_controller_stage_add_and_delete_leave_siblings_byte_identical(tmp_path: Path) -> None:
    selected_stages: list[str | None] = ["alpha"]
    overlay = SimpleNamespace(
        selected_stage_id=lambda: selected_stages[-1],
        set_selected_stage_id=lambda stage_id: selected_stages.append(stage_id),
    )
    alpha = {
        "id": "alpha",
        "title": "First",
        "text": "First text.",
        "complete_on": {"type": "dialogue_choice", "payload": {"choice_id": "done"}},
        "start_on_event": {"type": "scene_loaded"},
        "requirements": {"counters": {"visits": 1}},
        "emit_events_on_complete": [{"type": "quest_stage_done"}],
    }
    beta = {"id": "beta", "title": "Second", "complete_on": {"type": "talked"}}
    controller = EditorQuestEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_quest("old_id", stages=[copy.deepcopy(alpha), copy.deepcopy(beta)]))

    assert controller._add_stage() is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["stages"][0] == alpha
    assert controller.edit_buffer["stages"][1] == beta

    selected_stages.append("stage_1")
    assert controller._delete_stage() is True

    assert controller.edit_buffer["stages"] == [alpha, beta]
