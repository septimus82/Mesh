from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.editor.editor_prefab_editor_controller as prefab_controller_module
import engine.optional_arcade as optional_arcade
from engine.editor.editor_prefab_editor_controller import (
    EditorPrefabEditorController,
    _complex_dict_action_parts,
    _complex_dict_add_action,
    _complex_list_action_parts,
    _complex_list_add_action,
    _get_path,
    _next_metadata_key,
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


def _prefab_with_behaviour_config() -> dict[str, object]:
    prefab = _prefab()
    entity = prefab["entity"]
    assert isinstance(entity, dict)
    entity["behaviour_config"] = {
        "DialogueRunner": {"script": {"start": {}}, "start_node": "start"},
        "Health": {"enabled": True, "hp": 4.5, "max": 8, "none": None},
        "TriggerVolume": {"target_tags": ["player"]},
    }
    return prefab


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


def test_prefab_editor_complex_list_add_action_parser_accepts_and_rejects_actions() -> None:
    assert _complex_list_add_action("entity.behaviours#add") == "entity.behaviours"
    assert _complex_list_add_action("tags#add") == "tags"
    assert _complex_list_action_parts("entity.behaviours#add") is None

    for action in (
        None,
        "",
        "tags.add",
        "tags#0#add",
        "metadata#add",
        "entity.behaviour_config#add",
        "entity.behaviours#delete",
    ):
        assert _complex_list_add_action(action) is None


def test_prefab_editor_complex_dict_add_action_parser_accepts_metadata_only() -> None:
    assert _complex_dict_add_action("metadata#add") == "metadata"

    for action in (
        None,
        "",
        "metadata.add",
        "metadata#author#add",
        "tags#add",
        "entity.behaviour_config#add",
        "unknown#add",
        "metadata#delete",
    ):
        assert _complex_dict_add_action(action) is None


def test_prefab_editor_complex_dict_action_parser_round_trips_metadata_delete() -> None:
    assert _complex_dict_action_parts("metadata#author#delete") == ("metadata", "author", "delete")


def test_prefab_editor_complex_dict_action_parser_round_trips_behaviour_config_delete() -> None:
    assert _complex_dict_action_parts("entity.behaviour_config#Health#max#delete") == (
        "entity.behaviour_config",
        "Health#max",
        "delete",
    )


def test_prefab_editor_complex_dict_action_parser_preserves_digit_like_and_special_keys() -> None:
    assert _complex_dict_action_parts("metadata#123#delete") == ("metadata", "123", "delete")
    assert _complex_dict_action_parts("metadata#a#b.c key#delete") == ("metadata", "a#b.c key", "delete")
    assert _complex_list_action_parts("metadata#123#delete") is None

    for action in (
        None,
        "",
        "metadata#author",
        "metadata##delete",
        "metadata#author#",
        "tags#author#delete",
    ):
        assert _complex_dict_action_parts(action) is None


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


def test_prefab_editor_controller_delete_dict_entry_removes_target_metadata_key(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"author": "core", "source": "test"}
    controller.enter_edit_mode(prefab)

    assert controller._delete_dict_entry("metadata", "author") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"source": "test"}


def test_prefab_editor_controller_delete_dict_entry_guards_invalid_cases(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))

    assert controller._delete_dict_entry("metadata", "author") is False

    controller.enter_edit_mode(_prefab())
    assert controller._delete_dict_entry("metadata", "missing") is False
    assert controller.edit_buffer is not None
    controller.edit_buffer["metadata"] = "not-a-dict"
    assert controller._delete_dict_entry("metadata", "author") is False


def test_prefab_editor_controller_delete_behaviour_config_entry_removes_target_scalar(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab_with_behaviour_config())
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    assert controller._delete_behaviour_config_entry("Health", "max") is True

    config = controller.edit_buffer["entity"]["behaviour_config"]
    assert config["Health"] == {
        "enabled": before["entity"]["behaviour_config"]["Health"]["enabled"],
        "hp": before["entity"]["behaviour_config"]["Health"]["hp"],
        "none": before["entity"]["behaviour_config"]["Health"]["none"],
    }
    assert config["DialogueRunner"] == before["entity"]["behaviour_config"]["DialogueRunner"]
    assert config["TriggerVolume"] == before["entity"]["behaviour_config"]["TriggerVolume"]
    for key in ("id", "display_name", "tags", "require_flags", "forbid_flags", "metadata"):
        assert controller.edit_buffer[key] == before[key]
    assert "entity.behaviour_config.Health.max" not in controller.text_inputs()


def test_prefab_editor_controller_delete_last_behaviour_config_key_leaves_empty_config_save_valid(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["entity"]["behaviour_config"] = {"Health": {"max": 8}}
    controller.enter_edit_mode(prefab)
    controller.sync_widgets_to_buffer()

    assert controller._delete_behaviour_config_entry("Health", "max") is True

    assert controller.edit_buffer["entity"]["behaviour_config"] == {"Health": {}}
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_delete_behaviour_config_entry_guards_invalid_cases(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    assert controller._delete_behaviour_config_entry("Health", "max") is False

    controller.enter_edit_mode(_prefab_with_behaviour_config())
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    assert controller._delete_behaviour_config_entry("Missing", "max") is False
    assert controller._delete_behaviour_config_entry("Health", "missing") is False
    assert controller._delete_behaviour_config_entry("DialogueRunner", "script") is False
    assert controller._delete_behaviour_config_entry("Health", "none") is False
    controller.edit_buffer["entity"]["behaviour_config"]["Health"] = "not-a-dict"
    assert controller._delete_behaviour_config_entry("Health", "max") is False
    assert controller.edit_buffer["entity"]["behaviour_config"]["DialogueRunner"] == before["entity"]["behaviour_config"][
        "DialogueRunner"
    ]
    assert controller.edit_buffer["entity"]["behaviour_config"]["TriggerVolume"] == before["entity"]["behaviour_config"][
        "TriggerVolume"
    ]


def test_prefab_editor_controller_routes_behaviour_config_delete_action_before_flat_dict_delete(
    tmp_path: Path,
) -> None:
    overlay = SimpleNamespace(complex_entry_action_at=lambda _x, _y: "entity.behaviour_config#Health#max#delete")
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_prefab_with_behaviour_config())

    assert controller.handle_prefab_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer is not None
    assert "max" not in controller.edit_buffer["entity"]["behaviour_config"]["Health"]
    assert "Health" in controller.edit_buffer["entity"]["behaviour_config"]


def test_prefab_editor_controller_delete_dict_entry_preserves_siblings_and_empty_save_valid(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"author": "core"}
    controller.enter_edit_mode(prefab)
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    assert controller._delete_dict_entry("metadata", "author") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {}
    for key, value in before.items():
        if key != "metadata":
            assert controller.edit_buffer[key] == value
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_rebuild_text_inputs_adds_metadata_key_specs(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"zeta": "last", "author": "core"}

    controller.enter_edit_mode(prefab)

    text_inputs = controller.text_inputs()
    assert {"metadata.author", "metadata.zeta"} <= set(text_inputs)
    assert {"metadata_key.author", "metadata_key.zeta"} <= set(text_inputs)
    assert text_inputs["metadata_key.author"].text == "author"
    assert text_inputs["metadata_key.zeta"].text == "zeta"
    assert text_inputs["metadata.author"].text == "core"
    assert text_inputs["metadata.zeta"].text == "last"


def test_prefab_editor_controller_metadata_key_field_value_is_literal_suffix(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))

    assert controller._get_field_value({"metadata": {"a.b": "value"}}, "metadata_key.a.b") == "a.b"


def test_prefab_editor_controller_metadata_key_rename_preserves_value_type_order_and_focus(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"author": "core", "count": 3, "blob": "kept"}
    controller.enter_edit_mode(prefab)

    controller.text_input("metadata_key.count").text = "rank"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert list(controller.edit_buffer["metadata"]) == ["author", "rank", "blob"]
    assert controller.edit_buffer["metadata"]["rank"] == 3
    assert isinstance(controller.edit_buffer["metadata"]["rank"], int)
    assert controller.edit_buffer["metadata"]["blob"] == "kept"
    assert "metadata_key.rank" in controller.text_inputs()
    assert "metadata.rank" in controller.text_inputs()
    assert "metadata_key.count" not in controller.text_inputs()
    assert "metadata.count" not in controller.text_inputs()
    assert controller.focused_field() == "metadata_key.rank"


def test_prefab_editor_controller_metadata_key_dotted_old_key_is_literal(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"a.b": "literal", "other": "same"}
    controller.enter_edit_mode(prefab)

    controller.text_input("metadata_key.a.b").text = "c.d"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"c.d": "literal", "other": "same"}
    assert "a" not in controller.edit_buffer["metadata"]
    assert "metadata_key.c.d" in controller.text_inputs()
    assert "metadata.c.d" in controller.text_inputs()


def test_prefab_editor_controller_duplicate_metadata_key_rename_is_rejected(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"author": "core", "source": "test"}
    controller.enter_edit_mode(prefab)
    controller.sync_widgets_to_buffer()
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("metadata_key.author").text = "source"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer == before
    assert controller.last_error_message() == "Metadata key 'source' already exists"
    assert "metadata_key.author" in controller.text_inputs()
    assert "metadata_key.source" in controller.text_inputs()


def test_prefab_editor_controller_empty_metadata_key_rename_is_rejected(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    controller.sync_widgets_to_buffer()
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("metadata_key.author").text = "  "
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer == before
    assert controller.last_error_message() == "Metadata key for author cannot be empty"
    assert "metadata_key.author" in controller.text_inputs()


def test_prefab_editor_controller_metadata_key_rename_does_not_warn(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab())

    controller.text_input("metadata_key.author").text = "custom_metadata_key"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"custom_metadata_key": "core"}
    assert not any(call[0] == "warning" for call in editor.feedback_calls)


def test_prefab_editor_controller_metadata_key_reconciliation_preserves_value_widget_edit(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    controller.text_input("metadata_key.author").text = "designer"
    controller.text_input("metadata.author").text = "ignored-stale"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"designer": "core"}
    assert "metadata.author" not in controller.text_inputs()
    assert "metadata.designer" in controller.text_inputs()
    assert controller.text_input("metadata.designer").text == "core"
    assert controller.focused_field() == "metadata_key.designer"


def test_prefab_editor_controller_metadata_key_rename_pollution_and_save_valid(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"author": "core", "source": "test", "zeta": "last"}
    controller.enter_edit_mode(prefab)
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("metadata_key.source").text = "origin"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"author": "core", "origin": "test", "zeta": "last"}
    for key, value in before.items():
        if key != "metadata":
            assert controller.edit_buffer[key] == value
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_metadata_add_then_rename_keeps_value_widget(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller._add_dict_entry("metadata") is True
    controller.text_input("metadata.new_key").text = "new value"
    controller.sync_widgets_to_buffer()
    controller.text_input("metadata_key.new_key").text = "designer"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"author": "core", "designer": "new value"}
    assert "metadata.designer" in controller.text_inputs()
    assert "metadata_key.designer" in controller.text_inputs()
    assert controller.text_input("metadata.designer").text == "new value"
    assert controller.focused_field() == "metadata_key.designer"


def test_prefab_editor_controller_metadata_value_edit_writes_string_value(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    controller.text_input("metadata.author").text = "designer"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"]["author"] == "designer"


def test_prefab_editor_controller_metadata_dotted_key_is_literal_suffix(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"a.b": "old"}
    controller.enter_edit_mode(prefab)

    controller.text_input("metadata.a.b").text = "new"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"a.b": "new"}
    assert "a" not in controller.edit_buffer["metadata"]


def test_prefab_editor_controller_metadata_empty_value_is_allowed(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    controller.text_input("metadata.author").text = ""
    controller.sync_widgets_to_buffer()

    assert controller.last_error_message() is None
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"]["author"] == ""
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_metadata_edit_preserves_siblings_and_lists(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"author": "core", "source": "test"}
    controller.enter_edit_mode(prefab)
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("metadata.author").text = "designer"
    controller.sync_widgets_to_buffer()
    controller.text_input("tags.1").text = "ice"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer["metadata"] == {"author": "designer", "source": "test"}
    assert controller.edit_buffer["tags"] == ["enemy", "ice"]
    for key, value in before.items():
        if key not in {"metadata", "tags"}:
            assert controller.edit_buffer[key] == value
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_next_metadata_key_skips_existing_names() -> None:
    assert _next_metadata_key({}) == "new_key"
    assert _next_metadata_key({"new_key": ""}) == "new_key_2"
    assert _next_metadata_key({"new_key": "", "new_key_2": ""}) == "new_key_3"


def test_prefab_editor_controller_add_dict_entry_initializes_metadata_and_focuses(
    tmp_path: Path,
) -> None:
    for initial in (None, "not-a-dict"):
        controller = EditorPrefabEditorController(_editor(tmp_path))
        prefab = _prefab()
        if initial is None:
            prefab.pop("metadata", None)
        else:
            prefab["metadata"] = initial
        controller.enter_edit_mode(prefab)

        assert controller._add_dict_entry("metadata") is True

        assert controller.edit_buffer is not None
        assert controller.edit_buffer["metadata"] == {"new_key": ""}
        assert controller.focused_field() == "metadata.new_key"
        assert controller.text_input("metadata.new_key").text == ""
        assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_add_dict_entry_inserts_unique_key_and_preserves_siblings(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    prefab["metadata"] = {"new_key": "old", "source": "test"}
    controller.enter_edit_mode(prefab)
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    assert controller._add_dict_entry("metadata") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"] == {"new_key": "old", "source": "test", "new_key_2": ""}
    assert controller.focused_field() == "metadata.new_key_2"
    for key, value in before.items():
        if key != "metadata":
            assert controller.edit_buffer[key] == value
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_add_dict_entry_routes_and_interops_with_edit_delete(
    tmp_path: Path,
) -> None:
    overlay = SimpleNamespace(complex_entry_action_at=lambda _x, _y: "metadata#add")
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["metadata"]["new_key"] == ""
    controller.text_input("metadata.new_key").text = "designer"
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer["metadata"]["new_key"] == "designer"
    assert controller._delete_dict_entry("metadata", "new_key") is True
    assert controller.edit_buffer["metadata"] == {"author": "core"}


def test_prefab_editor_controller_add_dict_entry_guards_non_metadata(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    assert controller._add_dict_entry("metadata") is False

    controller.enter_edit_mode(_prefab())
    assert controller._add_dict_entry("entity.behaviour_config") is False
    assert controller._add_dict_entry("tags") is False


def test_prefab_editor_controller_add_list_entry_appends_seed_for_all_fields(
    tmp_path: Path,
) -> None:
    for field_path, seed in (
        ("tags", "new_tag"),
        ("require_flags", "new_flag"),
        ("forbid_flags", "new_flag"),
        ("entity.behaviours", "NewBehaviour"),
        ("entity.require_flags", "new_flag"),
    ):
        controller = EditorPrefabEditorController(_editor(tmp_path))
        controller.enter_edit_mode(_prefab())
        controller.sync_widgets_to_buffer()
        assert controller.edit_buffer is not None
        before = copy.deepcopy(controller.edit_buffer)
        original = list(_get_path(before, field_path))

        assert controller._add_list_entry(field_path) is True

        assert controller.edit_buffer is not None
        assert _get_path(controller.edit_buffer, field_path) == [*original, seed]
        assert seed
        assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []
        assert controller.focused_field() == f"{field_path}.{len(original)}"
        assert f"{field_path}.{len(original)}" in controller.text_inputs()
        for key, value in before.items():
            if key != field_path.split(".")[0]:
                assert controller.edit_buffer[key] == value


@pytest.mark.parametrize(
    ("field_path", "container_path", "entry_key"),
    [
        ("tags", "", "tags"),
        ("entity.behaviours", "entity", "behaviours"),
        ("entity.require_flags", "entity", "require_flags"),
    ],
)
def test_prefab_editor_controller_add_list_entry_initializes_absent_and_non_list_fields(
    tmp_path: Path,
    field_path: str,
    container_path: str,
    entry_key: str,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    prefab = _prefab()
    if container_path:
        prefab[container_path].pop(entry_key, None)
    else:
        prefab.pop(entry_key, None)
    controller.enter_edit_mode(prefab)

    assert controller._add_list_entry(field_path) is True
    assert isinstance(_get_path(controller.edit_buffer or {}, field_path), list)

    if container_path:
        controller.edit_buffer[container_path][entry_key] = "not-a-list"
    else:
        controller.edit_buffer[entry_key] = "not-a-list"
    assert controller._add_list_entry(field_path) is True
    assert isinstance(_get_path(controller.edit_buffer or {}, field_path), list)


def test_prefab_editor_controller_behaviour_add_seed_does_not_warn_until_real_unknown_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prefab_controller_module, "_known_behaviour_names", lambda: frozenset({"EnemyAI", "Health"}))
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab())

    assert controller._add_list_entry("entity.behaviours") is True
    controller.sync_widgets_to_buffer()

    assert not any(call[0] == "warning" for call in editor.feedback_calls)
    assert controller.edit_buffer is not None
    new_index = len(controller.edit_buffer["entity"]["behaviours"]) - 1
    field_path = f"entity.behaviours.{new_index}"
    controller.text_input(field_path).text = "CustomBehaviour"
    controller.sync_widgets_to_buffer()

    assert editor.feedback_calls[-1] == ("warning", "Unknown prefab behaviour 'CustomBehaviour'")


def test_prefab_editor_controller_add_list_entry_routes_before_delete_parser(tmp_path: Path) -> None:
    overlay = SimpleNamespace(complex_entry_action_at=lambda _x, _y: "entity.require_flags#add")
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["require_flags"] == ["entity_ready", "entity_done", "new_flag"]


def test_prefab_editor_controller_add_edit_delete_interop(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller._add_list_entry("tags") is True
    assert controller.edit_buffer is not None
    added_index = len(controller.edit_buffer["tags"]) - 1
    controller.text_input(f"tags.{added_index}").text = "edited_tag"
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer["tags"][-1] == "edited_tag"

    assert controller._delete_list_entry("tags", added_index) is True
    assert controller.edit_buffer["tags"] == ["enemy", "fire"]


def test_prefab_editor_controller_move_action_parser_and_routing(tmp_path: Path) -> None:
    assert _complex_list_action_parts("entity.behaviours#1#move_up") == ("entity.behaviours", 1, "move_up")
    assert _complex_list_action_parts("entity.behaviours#0#move_down") == ("entity.behaviours", 0, "move_down")

    overlay = SimpleNamespace(complex_entry_action_at=lambda _x, _y: "entity.behaviours#1#move_up")
    controller = EditorPrefabEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["behaviours"] == ["Health", "EnemyAI"]


def test_prefab_editor_controller_move_behaviour_down_swaps_and_focuses_target(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller._move_list_entry("entity.behaviours", 0, 1) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["behaviours"] == ["Health", "EnemyAI"]
    assert controller.focused_field() == "entity.behaviours.1"
    assert controller.text_input("entity.behaviours.0").text == "Health"
    assert controller.text_input("entity.behaviours.1").text == "EnemyAI"


def test_prefab_editor_controller_move_behaviour_up_swaps_and_focuses_target(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller._move_list_entry("entity.behaviours", 1, -1) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["behaviours"] == ["Health", "EnemyAI"]
    assert controller.focused_field() == "entity.behaviours.0"


def test_prefab_editor_controller_move_behaviour_boundaries_are_noops(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer["entity"]["behaviours"])

    assert controller._move_list_entry("entity.behaviours", 0, -1) is False
    assert controller._move_list_entry("entity.behaviours", 1, 1) is False

    assert controller.edit_buffer["entity"]["behaviours"] == before


def test_prefab_editor_controller_move_behaviour_preserves_siblings_and_round_trips(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)
    original_behaviours = list(controller.edit_buffer["entity"]["behaviours"])

    assert controller._move_list_entry("entity.behaviours", 0, 1) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["behaviours"] == [original_behaviours[1], original_behaviours[0]]
    for key, value in before.items():
        if key != "entity":
            assert controller.edit_buffer[key] == value
    for key, value in before["entity"].items():
        if key != "behaviours":
            assert controller.edit_buffer["entity"][key] == value

    assert controller._move_list_entry("entity.behaviours", 1, -1) is True

    assert controller.edit_buffer["entity"]["behaviours"] == original_behaviours
    assert controller.edit_buffer == before


def test_prefab_editor_controller_move_interops_with_add_edit_and_delete(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller._add_list_entry("entity.behaviours") is True
    assert controller.edit_buffer is not None
    added_index = len(controller.edit_buffer["entity"]["behaviours"]) - 1
    controller.text_input(f"entity.behaviours.{added_index}").text = "PatrolPath"
    controller.sync_widgets_to_buffer()

    assert controller._move_list_entry("entity.behaviours", added_index, -1) is True
    assert controller.edit_buffer["entity"]["behaviours"] == ["EnemyAI", "PatrolPath", "Health"]
    assert controller._delete_list_entry("entity.behaviours", 1) is True
    assert controller.edit_buffer["entity"]["behaviours"] == ["EnemyAI", "Health"]


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


def test_prefab_editor_controller_rebuild_text_inputs_adds_scalar_behaviour_config_specs_only(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab_with_behaviour_config())

    text_inputs = controller.text_inputs()

    assert {
        "entity.behaviour_config.DialogueRunner.start_node",
        "entity.behaviour_config.Health.enabled",
        "entity.behaviour_config.Health.hp",
        "entity.behaviour_config.Health.max",
    } <= set(text_inputs)
    assert "entity.behaviour_config.DialogueRunner.script" not in text_inputs
    assert "entity.behaviour_config.Health.none" not in text_inputs
    assert "entity.behaviour_config.TriggerVolume.target_tags" not in text_inputs
    assert text_inputs["entity.behaviour_config.Health.enabled"].text == "True"


def test_prefab_editor_controller_behaviour_config_scalar_edits_preserve_types_and_save_valid(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab_with_behaviour_config())
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("entity.behaviour_config.Health.max").text = "12"
    controller.text_input("entity.behaviour_config.Health.hp").text = "6.25"
    controller.text_input("entity.behaviour_config.DialogueRunner.start_node").text = ""
    controller.sync_widgets_to_buffer()

    config = controller.edit_buffer["entity"]["behaviour_config"]
    assert config["Health"]["max"] == 12
    assert type(config["Health"]["max"]) is int
    assert config["Health"]["hp"] == 6.25
    assert type(config["Health"]["hp"]) is float
    assert config["DialogueRunner"]["start_node"] == ""
    assert type(config["DialogueRunner"]["start_node"]) is str
    assert config["DialogueRunner"]["script"] == before["entity"]["behaviour_config"]["DialogueRunner"]["script"]
    assert config["Health"]["enabled"] == before["entity"]["behaviour_config"]["Health"]["enabled"]
    assert config["Health"]["none"] is None
    assert config["TriggerVolume"] == before["entity"]["behaviour_config"]["TriggerVolume"]
    assert validate_prefab_entries([controller.edit_buffer], tmp_path / "assets" / "prefabs.json") == []


def test_prefab_editor_controller_behaviour_config_bool_edits_accept_common_literals(
    tmp_path: Path,
) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab_with_behaviour_config())

    for text, expected in (("false", False), ("true", True), ("0", False), ("1", True)):
        controller.text_input("entity.behaviour_config.Health.enabled").text = text
        controller.sync_widgets_to_buffer()
        assert controller.edit_buffer is not None
        value = controller.edit_buffer["entity"]["behaviour_config"]["Health"]["enabled"]
        assert value is expected
        assert type(value) is bool


def test_prefab_editor_controller_invalid_behaviour_config_bool_is_rejected_without_pollution(
    tmp_path: Path,
) -> None:
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab_with_behaviour_config())
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("entity.behaviour_config.Health.enabled").text = "maybe"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer == before
    assert controller.last_error_message() == "Invalid value for entity.behaviour_config.Health.enabled: maybe"
    assert editor.feedback_calls[-1] == (
        "error",
        "Invalid value for entity.behaviour_config.Health.enabled: maybe",
    )


def test_prefab_editor_controller_invalid_behaviour_config_numeric_is_rejected_without_pollution(
    tmp_path: Path,
) -> None:
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab_with_behaviour_config())
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("entity.behaviour_config.Health.max").text = "many"
    controller.text_input("entity.behaviour_config.Health.hp").text = "fast"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer == before
    assert controller.last_error_message() in {
        "Invalid value for entity.behaviour_config.Health.max: many",
        "Invalid value for entity.behaviour_config.Health.hp: fast",
    }
    assert ("error", "Invalid value for entity.behaviour_config.Health.max: many") in editor.feedback_calls
    assert ("error", "Invalid value for entity.behaviour_config.Health.hp: fast") in editor.feedback_calls


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
