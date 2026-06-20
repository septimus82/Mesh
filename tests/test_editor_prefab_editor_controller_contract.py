from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.editor.editor_prefab_editor_controller as prefab_controller_module
import engine.optional_arcade as optional_arcade
from engine.editor.editor_prefab_editor_controller import (
    EditorPrefabEditorController,
    _complex_list_action_parts,
    _get_path,
    _set_path,
)
from engine.editor.prefab_editor_model import validate_prefab_entries

pytestmark = [pytest.mark.fast]


def _editor(tmp_path: Path, overlay: object | None = None) -> SimpleNamespace:
    feedback_calls: list[tuple[str, str]] = []
    editor = SimpleNamespace(
        window=SimpleNamespace(prefab_editor_overlay=overlay),
        feedback=SimpleNamespace(
            error=lambda message: feedback_calls.append(("error", str(message))),
            info=lambda message: feedback_calls.append(("info", str(message))),
            warning=lambda message: feedback_calls.append(("warning", str(message))),
        ),
        _get_repo_root=lambda: tmp_path,
        feedback_calls=feedback_calls,
    )
    return editor


def _prefab(prefab_id: str = "torch_wisp") -> dict[str, object]:
    return {
        "id": prefab_id,
        "display_name": "Torch Wisp",
        "entity": {
            "sprite": "assets/placeholder.png",
            "encounter_cost": 2,
            "behaviours": ["EnemyAI", "Health"],
            "require_flags": ["entity_ready", "entity_done"],
        },
        "tags": ["enemy", "fire"],
        "require_flags": ["flag_a", "flag_b"],
        "forbid_flags": ["flag_c", "flag_d"],
        "metadata": {"author": "core"},
    }


def test_prefab_editor_controller_enter_cancel_and_dirty(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))

    controller.enter_edit_mode(_prefab())
    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() == "id"
    assert controller.is_dirty() is False

    assert controller.handle_prefab_editor_text_input("_x") is True
    assert controller.is_dirty() is True

    controller.cancel_edit_mode()
    assert controller.is_edit_mode_active() is False
    assert controller.is_dirty() is False
    assert controller.last_error_message() is None


def test_prefab_editor_controller_deep_copies_edit_buffer(tmp_path: Path) -> None:
    source = _prefab()
    controller = EditorPrefabEditorController(_editor(tmp_path))

    controller.enter_edit_mode(source)
    assert controller.edit_buffer is not None
    assert isinstance(controller.edit_buffer["entity"], dict)
    controller.edit_buffer["entity"]["sprite"] = "assets/changed.png"

    assert source["entity"]["sprite"] == "assets/placeholder.png"


def test_prefab_editor_path_helpers_handle_nested_and_missing_paths() -> None:
    payload: dict[str, object] = {"id": "torch_wisp", "entity": {"sprite": "old.png"}}

    assert _get_path(payload, "id") == "torch_wisp"
    assert _get_path(payload, "entity.sprite") == "old.png"
    assert _get_path(payload, "entity.missing") is None
    assert _get_path({"entity": "not a dict"}, "entity.sprite") is None
    assert _get_path(payload, "") is None


def test_prefab_editor_path_helpers_create_and_replace_intermediate_dicts() -> None:
    payload: dict[str, object] = {}

    _set_path(payload, "id", "torch_wisp")
    _set_path(payload, "entity.sprite", "assets/placeholder.png")
    assert payload == {"id": "torch_wisp", "entity": {"sprite": "assets/placeholder.png"}}

    payload["entity"] = "not a dict"
    _set_path(payload, "entity.encounter_cost", "2")
    assert payload["entity"] == {"encounter_cost": "2"}

    _set_path(payload, "", "ignored")
    assert "" not in payload


def test_prefab_editor_path_helpers_read_nested_list_elements() -> None:
    payload = {"script": {"n": {"choices": [{"text": "First"}, {"text": "Second"}]}}}

    assert _get_path(payload, "script.n.choices.0.text") == "First"
    assert _get_path(payload, "script.n.choices.5.text") is None
    assert _get_path(payload, "script.n.choices.first.text") is None


def test_prefab_editor_path_helpers_write_nested_list_elements() -> None:
    payload = {
        "script": {
            "n": {
                "choices": [
                    {"next": "a", "text": "First"},
                    {"next": "b", "text": "Second"},
                ]
            }
        }
    }

    _set_path(payload, "script.n.choices.1.next", "done")

    choices = payload["script"]["n"]["choices"]
    assert choices == [{"next": "a", "text": "First"}, {"next": "done", "text": "Second"}]


def test_prefab_editor_path_helpers_preserve_list_intermediary() -> None:
    payload = {"a": {"b": [{"c": "old"}]}}

    _set_path(payload, "a.b.0.c", "new")

    assert isinstance(payload["a"]["b"], list)
    assert len(payload["a"]["b"]) == 1
    assert payload["a"]["b"][0]["c"] == "new"


def test_prefab_editor_path_helpers_out_of_range_list_write_no_ops() -> None:
    payload = {"script": {"n": {"choices": [{"next": "a", "text": "First"}]}}}
    before = {"script": {"n": {"choices": [{"next": "a", "text": "First"}]}}}

    _set_path(payload, "script.n.choices.4.next", "missing")

    assert payload == before


def test_prefab_editor_path_helpers_dict_round_trip_unchanged() -> None:
    payload: dict[str, object] = {}

    _set_path(payload, "a.b.c", "value")

    assert _get_path(payload, "a.b.c") == "value"
    assert payload == {"a": {"b": {"c": "value"}}}


def test_prefab_editor_complex_list_action_parser_round_trips_dotted_field_path() -> None:
    assert _complex_list_action_parts("entity.behaviours#1#delete") == ("entity.behaviours", 1, "delete")
    assert _complex_list_action_parts("tags#0#delete") == ("tags", 0, "delete")


def test_prefab_editor_complex_list_action_parser_rejects_malformed_actions() -> None:
    for action in (
        None,
        "",
        "tags.0.delete",
        "tags#0",
        "tags#x#delete",
        "metadata#0#delete",
        "entity.behaviour_config#0#delete",
        "entity.behaviours#0#",
    ):
        assert _complex_list_action_parts(action) is None


@pytest.mark.parametrize(
    ("field_path", "expected"),
    [
        ("tags", ["enemy"]),
        ("require_flags", ["flag_a"]),
        ("forbid_flags", ["flag_c"]),
        ("entity.behaviours", ["EnemyAI"]),
        ("entity.require_flags", ["entity_ready"]),
    ],
)
def test_prefab_editor_controller_delete_list_entry_removes_target_for_all_list_fields(
    tmp_path: Path,
    field_path: str,
    expected: list[str],
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller._delete_list_entry(field_path, 1) is True

    assert controller.edit_buffer is not None
    assert _get_path(controller.edit_buffer, field_path) == expected


def test_prefab_editor_controller_delete_list_entry_guards_invalid_cases(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))

    assert controller._delete_list_entry("tags", 0) is False

    controller.enter_edit_mode(_prefab())
    assert controller._delete_list_entry("metadata", 0) is False
    assert controller._delete_list_entry("tags", 99) is False
    assert controller.edit_buffer is not None
    controller.edit_buffer["tags"] = "enemy"
    assert controller._delete_list_entry("tags", 0) is False


def test_prefab_editor_controller_mouse_click_routes_complex_list_delete(tmp_path: Path) -> None:
    overlay = SimpleNamespace(complex_entry_action_at=lambda _x, _y: "entity.behaviours#1#delete")
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["behaviours"] == ["EnemyAI"]


def test_prefab_editor_controller_delete_list_entry_preserves_siblings_order_and_save_valid(
    tmp_path: Path,
) -> None:
    prefab = _prefab()
    prefab["tags"] = ["only"]
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(prefab)
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    assert controller._delete_list_entry("tags", 0) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["tags"] == []
    for key in ("id", "display_name", "entity", "require_flags", "forbid_flags", "metadata"):
        assert controller.edit_buffer[key] == before[key]
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_rebuild_text_inputs_adds_list_entry_specs(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    text_inputs = controller.text_inputs()

    assert {
        "tags.0",
        "tags.1",
        "require_flags.0",
        "require_flags.1",
        "forbid_flags.0",
        "forbid_flags.1",
        "entity.behaviours.0",
        "entity.behaviours.1",
        "entity.require_flags.0",
        "entity.require_flags.1",
    } <= set(text_inputs)
    assert text_inputs["entity.behaviours.1"].text == "Health"


@pytest.mark.parametrize(
    ("field_path", "replacement", "expected"),
    [
        ("tags.1", "ice", ["enemy", "ice"]),
        ("require_flags.1", "flag_done", ["flag_a", "flag_done"]),
        ("forbid_flags.1", "flag_blocked", ["flag_c", "flag_blocked"]),
        ("entity.behaviours.1", "Combat", ["EnemyAI", "Combat"]),
        ("entity.require_flags.1", "entity_ready_done", ["entity_ready", "entity_ready_done"]),
    ],
)
def test_prefab_editor_controller_list_entry_edits_round_trip_through_generalized_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_path: str,
    replacement: str,
    expected: list[str],
) -> None:
    monkeypatch.setattr(prefab_controller_module, "_known_behaviour_names", lambda: frozenset({"EnemyAI", "Combat"}))
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    controller.sync_widgets_to_buffer()
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input(field_path).text = replacement
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    parent_path = field_path.rsplit(".", 1)[0]
    assert _get_path(controller.edit_buffer, parent_path) == expected
    changed_root = parent_path.split(".")[0]
    for key, value in before.items():
        if key != changed_root:
            assert controller.edit_buffer[key] == value


def test_prefab_editor_controller_unknown_behaviour_warns_once_and_still_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prefab_controller_module, "_known_behaviour_names", lambda: frozenset({"EnemyAI"}))
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab())

    controller.text_input("entity.behaviours.1").text = "CustomBehaviour"
    controller.sync_widgets_to_buffer()
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["behaviours"] == ["EnemyAI", "CustomBehaviour"]
    assert editor.feedback_calls.count(("warning", "Unknown prefab behaviour 'CustomBehaviour'")) == 1


def test_prefab_editor_controller_known_behaviour_freeform_lists_and_empty_registry_do_not_warn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    monkeypatch.setattr(prefab_controller_module, "_known_behaviour_names", lambda: frozenset({"EnemyAI", "Combat"}))
    controller.enter_edit_mode(_prefab())

    controller.text_input("entity.behaviours.1").text = "Combat"
    controller.text_input("tags.1").text = "custom_tag"
    controller.text_input("require_flags.1").text = "custom_flag"
    controller.text_input("forbid_flags.1").text = "custom_forbid"
    controller.text_input("entity.require_flags.1").text = "custom_entity_flag"
    controller.sync_widgets_to_buffer()

    monkeypatch.setattr(prefab_controller_module, "_known_behaviour_names", lambda: frozenset())
    controller.text_input("entity.behaviours.1").text = "UnknownButRegistryUnavailable"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["behaviours"] == ["EnemyAI", "UnknownButRegistryUnavailable"]
    assert not any(call[0] == "warning" for call in editor.feedback_calls)


def test_prefab_editor_controller_empty_list_entry_is_rejected_without_pollution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prefab_controller_module, "_known_behaviour_names", lambda: frozenset({"EnemyAI", "Health"}))
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab())
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("tags.1").text = ""
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer == before
    assert controller.last_error_message() == "tags.1 cannot be empty"
    assert editor.feedback_calls[-1] == ("error", "tags.1 cannot be empty")
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_enter_unfocuses_without_saving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[object] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda *args, **kwargs: saved.append((args, kwargs)))
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_key(optional_arcade.arcade.key.ENTER, 0) is True

    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() is None
    assert saved == []


def test_prefab_editor_controller_escape_cancels_edit_mode(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_key(optional_arcade.arcade.key.ESCAPE, 0) is True

    assert controller.is_edit_mode_active() is False


def test_prefab_editor_controller_commit_save_replaces_by_original_id_after_id_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])

    def _save(prefabs: list[dict[str, object]], target: Path) -> None:
        saved.append((prefabs, target))

    monkeypatch.setattr(prefab_editor_model, "save_prefabs", _save)
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.id_input().text = "new_id"

    ok = controller.commit_save([_prefab("old_id"), _prefab("other")], tmp_path / "assets" / "prefabs.json")

    assert ok is True
    assert controller.is_edit_mode_active() is False
    assert saved[0][0][0]["id"] == "new_id"
    assert saved[0][0][1]["id"] == "other"
    assert editor.feedback_calls[-1] == ("info", "Prefab saved")


def test_prefab_editor_controller_commit_save_reports_validation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: ["id is required"])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.id_input().text = ""

    ok = controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json")

    assert ok is False
    assert controller.last_error_message() == "id is required"
    assert editor.feedback_calls[-1] == ("error", "id is required")
    assert saved == []


def test_prefab_editor_controller_tab_switch_keeps_edit_buffer(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    controller.handle_prefab_editor_text_input("_draft")

    assert controller.is_edit_mode_active() is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["id"] == "torch_wisp_draft"


def test_prefab_editor_controller_focus_cycle_forward_backward_wraps(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller.focused_field() == "id"
    for expected in ("display_name", "entity.sprite", "entity.encounter_cost", "id"):
        controller.cycle_focus_forward()
        assert controller.focused_field() == expected
        assert controller.text_input(expected).focused is True

    controller.cycle_focus_backward()
    assert controller.focused_field() == "entity.encounter_cost"
    assert controller.text_input("entity.encounter_cost").focused is True


def test_prefab_editor_controller_focus_cycle_noops_when_not_editing(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))

    controller.cycle_focus_forward()
    controller.cycle_focus_backward()

    assert controller.focused_field() is None


def test_prefab_editor_controller_text_input_updates_nested_focused_field(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    controller.cycle_focus_forward()
    controller.cycle_focus_forward()

    assert controller.focused_field() == "entity.sprite"
    assert controller.handle_prefab_editor_text_input("_x") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["sprite"] == "assets/placeholder.png_x"


def test_prefab_editor_controller_commit_save_coerces_encounter_cost_int(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda prefabs, _target: saved.append(prefabs))
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab("old_id"))
    controller.text_input("entity.encounter_cost").text = "7"

    assert controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json") is True

    assert saved[0][0]["entity"]["encounter_cost"] == 7


def test_prefab_editor_controller_commit_save_removes_empty_encounter_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda prefabs, _target: saved.append(prefabs))
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab("old_id"))
    controller.text_input("entity.encounter_cost").text = " "

    assert controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json") is True

    assert "encounter_cost" not in saved[0][0]["entity"]


def test_prefab_editor_controller_commit_save_rejects_invalid_encounter_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.text_input("entity.encounter_cost").text = "abc"

    ok = controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json")

    assert ok is False
    assert controller.last_error_message() == "entity.encounter_cost must be an integer"
    assert editor.feedback_calls[-1] == ("error", "entity.encounter_cost must be an integer")
    assert saved == []


def test_prefab_editor_controller_uses_model_default_path_for_button_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[Path] = []
    from engine.editor import prefab_editor_model
    from engine.ui_overlays.widgets import Rect

    overlay = SimpleNamespace(
        selected_prefab_dict=lambda: _prefab("old_id"),
        all_prefab_dicts=lambda: [_prefab("old_id")],
        reload_model=lambda: None,
    )
    editor = _editor(tmp_path, overlay)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.set_button_rects({"save": Rect(0.0, 0.0, 20.0, 20.0)})
    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda _prefabs, target: saved.append(target))

    assert controller.handle_prefab_editor_mouse_click(10.0, 10.0) is True

    assert saved == [tmp_path / prefab_editor_model.DEFAULT_PREFAB_FILE_PATH]


def test_prefab_editor_controller_view_mode_row_click_selects(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: 1,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))

    assert controller.handle_prefab_editor_mouse_click(10.0, 10.0) is True

    assert selected == [1]
    assert controller.is_edit_mode_active() is False


def test_prefab_editor_controller_view_mode_row_miss_keeps_edit_button_working(tmp_path: Path) -> None:
    from engine.ui_overlays.widgets import Rect

    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        selected_prefab_dict=lambda: _prefab("old_id"),
    )
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))
    controller.set_button_rects({"edit": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_prefab_editor_mouse_click(10.0, 10.0) is True

    assert controller.is_edit_mode_active() is True


def test_prefab_editor_controller_edit_mode_skips_row_selection(tmp_path: Path) -> None:
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
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_prefab("old_id"))
    controller.set_button_rects({"cancel": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_prefab_editor_mouse_click(10.0, 10.0) is True

    assert selected == []
    assert row_hit_calls == []
    assert controller.is_edit_mode_active() is False


def test_prefab_editor_controller_empty_view_mode_click_falls_through(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))

    assert controller.handle_prefab_editor_mouse_click(10.0, 10.0) is False

    assert selected == []
    assert controller.is_edit_mode_active() is False
