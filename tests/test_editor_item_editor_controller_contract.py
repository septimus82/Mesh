from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_item_editor_controller import (
    EFFECT_ADD_ACTION,
    TAG_ADD_ACTION,
    EditorItemEditorController,
    _complex_entry_action_parts,
    _next_effect_key,
)
from engine.editor.item_editor_model import validate_item

pytestmark = [pytest.mark.fast]


def _editor(tmp_path: Path, overlay: object | None = None) -> SimpleNamespace:
    feedback_calls: list[tuple[str, str]] = []
    editor = SimpleNamespace(
        window=SimpleNamespace(item_editor_overlay=overlay),
        feedback=SimpleNamespace(
            error=lambda message: feedback_calls.append(("error", str(message))),
            info=lambda message: feedback_calls.append(("info", str(message))),
            warning=lambda message: feedback_calls.append(("warning", str(message))),
        ),
        _get_repo_root=lambda: tmp_path,
        feedback_calls=feedback_calls,
    )
    return editor


def _item(item_id: str = "healing_potion") -> dict[str, object]:
    return {
        "id": item_id,
        "name": "Healing Potion",
        "description": "Restores HP.",
        "icon": None,
        "stackable": True,
        "max_stack": 5,
        "tags": ["consumable"],
        "effects": {"heal": 25},
    }


def test_item_editor_controller_enter_cancel_and_dirty(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))

    controller.enter_edit_mode(_item())
    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() == "id"
    assert controller.is_dirty() is False

    assert controller.handle_item_editor_text_input("_x") is True
    assert controller.is_dirty() is True

    controller.cancel_edit_mode()
    assert controller.is_edit_mode_active() is False
    assert controller.is_dirty() is False
    assert controller.last_error_message() is None


def test_item_editor_controller_enter_unfocuses_without_saving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[object] = []
    from engine.editor import item_editor_model

    monkeypatch.setattr(item_editor_model, "save_items", lambda *args, **kwargs: saved.append((args, kwargs)))
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    assert controller.handle_item_editor_key(optional_arcade.arcade.key.ENTER, 0) is True

    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() is None
    assert saved == []


def test_item_editor_controller_escape_cancels_edit_mode(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    assert controller.handle_item_editor_key(optional_arcade.arcade.key.ESCAPE, 0) is True

    assert controller.is_edit_mode_active() is False


def test_item_editor_controller_commit_save_replaces_original_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import item_editor_model

    def _save(items: list[dict[str, object]], target: Path) -> None:
        saved.append((items, target))

    monkeypatch.setattr(item_editor_model, "save_items", _save)
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    controller.enter_edit_mode(_item("old_id"))
    controller.id_input().text = "new_id"

    ok = controller.commit_save([_item("old_id"), _item("other")], tmp_path / "assets" / "data" / "items.json")

    assert ok is True
    assert controller.is_edit_mode_active() is False
    assert saved[0][0][0]["id"] == "new_id"
    assert saved[0][0][1]["id"] == "other"
    assert editor.feedback_calls[-1] == ("info", "Item saved")


def test_item_editor_controller_commit_save_reports_validation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[object] = []
    from engine.editor import item_editor_model

    monkeypatch.setattr(item_editor_model, "save_items", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    controller.enter_edit_mode(_item("old_id"))
    controller.id_input().text = ""

    ok = controller.commit_save([_item("old_id")], tmp_path / "assets" / "data" / "items.json")

    assert ok is False
    assert controller.last_error_message() == "id is required"
    assert editor.feedback_calls[-1] == ("error", "id is required")
    assert saved == []


def test_item_editor_controller_tab_switch_keeps_edit_buffer(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())
    controller.handle_item_editor_text_input("_draft")

    assert controller.is_edit_mode_active() is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["id"] == "healing_potion_draft"


def test_item_editor_controller_focus_cycle_forward_wraps(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    assert controller.focused_field() == "id"
    for expected in ("name", "description", "icon", "max_stack", "id"):
        controller.cycle_focus_forward()
        assert controller.focused_field() == expected
        assert controller.text_input(expected).focused is True


def test_item_editor_controller_focus_cycle_backward_wraps(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    controller.cycle_focus_backward()

    assert controller.focused_field() == "max_stack"
    assert controller.text_input("max_stack").focused is True


def test_item_editor_controller_focus_cycle_noops_when_not_editing(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))

    controller.cycle_focus_forward()
    controller.cycle_focus_backward()

    assert controller.focused_field() is None


def test_item_editor_controller_focus_cycle_noops_for_non_cycle_focus(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())
    controller._focused_field = "stackable"

    controller.cycle_focus_forward()

    assert controller.focused_field() == "stackable"


def test_item_editor_controller_text_input_updates_current_focused_field(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())
    controller.cycle_focus_forward()

    assert controller.handle_item_editor_text_input(" X") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["name"] == "Healing Potion X"


def test_item_editor_controller_view_mode_row_click_selects(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: 1,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorItemEditorController(_editor(tmp_path, overlay))

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is True

    assert selected == [1]
    assert controller.is_edit_mode_active() is False


def test_item_editor_controller_view_mode_row_miss_keeps_edit_button_working(tmp_path: Path) -> None:
    from engine.ui_overlays.widgets import Rect

    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        selected_item_dict=lambda: _item("old_id"),
    )
    controller = EditorItemEditorController(_editor(tmp_path, overlay))
    controller.set_button_rects({"edit": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is True

    assert controller.is_edit_mode_active() is True


def test_item_editor_controller_edit_mode_skips_row_selection(tmp_path: Path) -> None:
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
    controller = EditorItemEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_item("old_id"))
    controller.set_button_rects({"cancel": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is True

    assert selected == []
    assert row_hit_calls == []
    assert controller.is_edit_mode_active() is False


def test_item_editor_controller_empty_view_mode_click_falls_through(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorItemEditorController(_editor(tmp_path, overlay))

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is False

    assert selected == []
    assert controller.is_edit_mode_active() is False


def test_item_editor_controller_delete_tag_removes_only_target_and_stays_save_valid(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["description"] = "Keep me"
    item["tags"] = ["consumable", "quest", "rare"]
    item["effects"] = {"heal": 25, "tier": 1}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = dict(controller.edit_buffer)
    before["tags"] = list(controller.edit_buffer["tags"])
    before["effects"] = dict(controller.edit_buffer["effects"])

    assert controller._delete_tag(1) is True

    assert controller.edit_buffer["tags"] == ["consumable", "rare"]
    assert controller.edit_buffer["effects"] == before["effects"]
    for field in ("id", "name", "description", "icon", "stackable", "max_stack"):
        assert controller.edit_buffer[field] == before[field]
    assert validate_item(controller.edit_buffer, [controller.edit_buffer]) == []


def test_item_editor_controller_delete_effect_removes_only_target_and_stays_save_valid(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["tags"] = ["consumable", "quest"]
    item["effects"] = {"heal": 25, "tier": 1, "quest.flag": "done"}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before_tags = list(controller.edit_buffer["tags"])

    assert controller._delete_effect("tier") is True

    assert controller.edit_buffer["effects"] == {"heal": 25, "quest.flag": "done"}
    assert controller.edit_buffer["tags"] == before_tags
    for field in ("id", "name", "description", "icon", "stackable", "max_stack"):
        assert controller.edit_buffer[field] == controller._original_record[field]
    assert validate_item(controller.edit_buffer, [controller.edit_buffer]) == []
    assert validate_item({**controller.edit_buffer, "tags": [], "effects": {}}, [controller.edit_buffer]) == []


def test_item_editor_controller_effect_key_with_dot_routes_through_action(tmp_path: Path) -> None:
    overlay = SimpleNamespace(complex_entry_action_at=lambda _x, _y: "effect.quest.flag.delete")
    controller = EditorItemEditorController(_editor(tmp_path, overlay))
    item = _item()
    item["effects"] = {"quest.flag": "done", "heal": 25}
    controller.enter_edit_mode(item)

    assert controller.handle_item_editor_mouse_click(10.0, 20.0) is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"] == {"heal": 25}


def test_item_editor_controller_complex_entry_action_parser() -> None:
    assert _complex_entry_action_parts("tag.2.delete") == ("tag", 2, "delete")
    assert _complex_entry_action_parts("effect.quest.flag.delete") == ("effect", "quest.flag", "delete")

    for action in ("", "tag.delete", "tag.two.delete", "effect..delete", "unknown.1.delete", "tag.1."):
        assert _complex_entry_action_parts(action) is None


def test_item_editor_controller_complex_delete_guards(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))

    assert controller._delete_tag(0) is False
    assert controller._delete_effect("heal") is False

    controller.enter_edit_mode(_item())

    assert controller._delete_tag(9) is False
    assert controller._delete_effect("missing") is False
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["tags"] == ["consumable"]
    assert controller.edit_buffer["effects"] == {"heal": 25}


def test_item_editor_controller_rebuild_text_inputs_adds_tag_specs(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["tags"] = ["consumable", "potion"]

    controller.enter_edit_mode(item)

    text_inputs = controller.text_inputs()
    assert "tags.0" in text_inputs
    assert "tags.1" in text_inputs
    assert text_inputs["tags.0"].text == "consumable"
    assert text_inputs["tags.1"].text == "potion"

    controller._rebuild_text_inputs({"tags": "not-a-list"})

    assert not any(field.startswith("tags.") for field in controller.text_inputs())


def test_item_editor_controller_tag_value_edit_updates_only_target(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["tags"] = ["consumable", "potion", "rare"]
    item["effects"] = {"heal": 25, "tier": 1}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("tags.1").text = "elixir"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer["tags"] == ["consumable", "elixir", "rare"]
    assert controller.edit_buffer["effects"] == before["effects"]
    for field in ("id", "name", "description", "icon", "stackable", "max_stack"):
        assert controller.edit_buffer[field] == before[field]


def test_item_editor_controller_tag_value_edit_persists_through_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import item_editor_model

    monkeypatch.setattr(item_editor_model, "save_items", lambda items, target: saved.append((items, target)))
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["tags"] = ["consumable", "potion"]
    controller.enter_edit_mode(item)
    controller.text_input("tags.1").text = "elixir"

    assert controller.commit_save([item], tmp_path / "assets" / "data" / "items.json") is True

    assert saved[0][0][0]["tags"] == ["consumable", "elixir"]


def test_item_editor_controller_tag_edit_pollution_keeps_siblings_byte_identical(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["tags"] = ["consumable", "potion", "rare"]
    item["effects"] = {"heal": 25, "tier": 1}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("tags.0").text = "usable"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer["tags"][0] == "usable"
    assert controller.edit_buffer["tags"][1:] == before["tags"][1:]
    assert controller.edit_buffer["effects"] == before["effects"]
    for field in ("id", "name", "description", "icon", "stackable", "max_stack"):
        assert controller.edit_buffer[field] == before[field]


def test_item_editor_controller_rebuild_text_inputs_adds_effect_specs(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"heal": 25, "quest.flag": "done"}

    controller.enter_edit_mode(item)

    text_inputs = controller.text_inputs()
    assert "effects.heal" in text_inputs
    assert "effects.quest.flag" in text_inputs
    assert text_inputs["effects.heal"].text == "25"
    assert text_inputs["effects.quest.flag"].text == "done"


def test_item_editor_controller_rebuild_text_inputs_adds_effect_key_specs(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"heal": 25, "quest.flag": "done"}

    controller.enter_edit_mode(item)

    text_inputs = controller.text_inputs()
    assert "effect_key.heal" in text_inputs
    assert "effect_key.quest.flag" in text_inputs
    assert text_inputs["effect_key.heal"].text == "heal"
    assert text_inputs["effect_key.quest.flag"].text == "quest.flag"


def test_item_editor_controller_effect_value_edit_preserves_int(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"heal": 25}
    controller.enter_edit_mode(item)

    controller.text_input("effects.heal").text = "30"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"]["heal"] == 30
    assert isinstance(controller.edit_buffer["effects"]["heal"], int)
    assert not isinstance(controller.edit_buffer["effects"]["heal"], bool)


def test_item_editor_controller_effect_value_edit_preserves_float(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"speed": 1.25}
    controller.enter_edit_mode(item)

    controller.text_input("effects.speed").text = "2.5"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"]["speed"] == 2.5
    assert isinstance(controller.edit_buffer["effects"]["speed"], float)


def test_item_editor_controller_effect_value_edit_keeps_string(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"quest_flag": "field_supplies_crate"}
    controller.enter_edit_mode(item)

    controller.text_input("effects.quest_flag").text = "supply_cache"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"]["quest_flag"] == "supply_cache"
    assert isinstance(controller.edit_buffer["effects"]["quest_flag"], str)


def test_item_editor_controller_effect_value_dotted_key_addresses_literal_key(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"quest.flag": "old", "quest": "nested"}
    controller.enter_edit_mode(item)

    controller.text_input("effects.quest.flag").text = "new"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"]["quest.flag"] == "new"
    assert controller.edit_buffer["effects"]["quest"] == "nested"


def test_item_editor_controller_effect_key_rename_preserves_value_type_and_focus(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"heal": 25}
    controller.enter_edit_mode(item)

    controller._focus_field("effect_key.heal")
    controller.text_input("effect_key.heal").text = "damage"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"] == {"damage": 25}
    assert isinstance(controller.edit_buffer["effects"]["damage"], int)
    assert "effect_key.damage" in controller.text_inputs()
    assert "effects.damage" in controller.text_inputs()
    assert "effects.heal" not in controller.text_inputs()
    assert controller.focused_field() == "effect_key.damage"


def test_item_editor_controller_effect_key_rename_treats_dotted_key_as_literal(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"quest.flag": "old", "heal": 25}
    controller.enter_edit_mode(item)

    controller.text_input("effect_key.quest.flag").text = "quest.flag.done"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"] == {"quest.flag.done": "old", "heal": 25}
    assert "effect_key.quest.flag.done" in controller.text_inputs()
    assert "effects.quest.flag.done" in controller.text_inputs()


def test_item_editor_controller_duplicate_effect_key_rename_is_rejected(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    item = _item()
    item["effects"] = {"heal": 25, "damage": 4}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("effect_key.heal").text = "damage"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer == before
    assert controller.last_error_message() == "Effect key 'damage' already exists"
    assert editor.feedback_calls[-1] == ("error", "Effect key 'damage' already exists")


def test_item_editor_controller_empty_effect_key_rename_is_rejected(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    item = _item()
    item["effects"] = {"heal": 25}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("effect_key.heal").text = "  "
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer == before
    assert controller.last_error_message() == "Effect key for heal cannot be empty"
    assert editor.feedback_calls[-1] == ("error", "Effect key for heal cannot be empty")


def test_item_editor_controller_unknown_effect_key_warns_but_renames(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    item = _item()
    item["effects"] = {"heal": 25}
    controller.enter_edit_mode(item)

    controller.text_input("effect_key.heal").text = "custom_mod"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"] == {"custom_mod": 25}
    assert controller.last_error_message() is None
    assert editor.feedback_calls[-1] == ("warning", "Unknown item effect key 'custom_mod'")


def test_item_editor_controller_effect_key_rename_pollution_preserves_siblings_and_order(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["name"] = "Keep Name"
    item["tags"] = ["consumable", "potion"]
    item["effects"] = {"heal": 25, "tier": 1, "speed": 1.25}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("effect_key.tier").text = "damage_bonus"
    controller.sync_widgets_to_buffer()

    assert list(controller.edit_buffer["effects"]) == ["heal", "damage_bonus", "speed"]
    assert controller.edit_buffer["effects"]["damage_bonus"] == before["effects"]["tier"]
    assert isinstance(controller.edit_buffer["effects"]["damage_bonus"], int)
    assert controller.edit_buffer["effects"]["heal"] == before["effects"]["heal"]
    assert controller.edit_buffer["effects"]["speed"] == before["effects"]["speed"]
    assert controller.edit_buffer["tags"] == before["tags"]
    for field in ("id", "name", "description", "icon", "stackable", "max_stack"):
        assert controller.edit_buffer[field] == before[field]


def test_item_editor_controller_invalid_numeric_effect_value_is_rejected(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    item = _item()
    item["effects"] = {"heal": 25, "speed": 1.25}
    controller.enter_edit_mode(item)

    controller.text_input("effects.heal").text = "not-a-number"
    controller.text_input("effects.speed").text = "also-not-a-number"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"]["heal"] == 25
    assert isinstance(controller.edit_buffer["effects"]["heal"], int)
    assert controller.edit_buffer["effects"]["speed"] == 1.25
    assert isinstance(controller.edit_buffer["effects"]["speed"], float)
    assert controller.last_error_message() == "Invalid numeric value for effects.speed: also-not-a-number"
    assert editor.feedback_calls[-1] == ("error", "Invalid numeric value for effects.speed: also-not-a-number")


def test_item_editor_controller_effect_edit_pollution_and_existing_tag_delete_paths(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["name"] = "Keep Name"
    item["tags"] = ["consumable", "potion"]
    item["effects"] = {"heal": 25, "damage": 4, "quest.flag": "done"}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    controller.text_input("effects.heal").text = "30"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer["effects"]["heal"] == 30
    assert controller.edit_buffer["effects"]["damage"] == before["effects"]["damage"]
    assert controller.edit_buffer["effects"]["quest.flag"] == before["effects"]["quest.flag"]
    assert controller.edit_buffer["tags"] == before["tags"]
    for field in ("id", "name", "description", "icon", "stackable", "max_stack"):
        assert controller.edit_buffer[field] == before[field]

    controller.text_input("tags.1").text = "elixir"
    controller.sync_widgets_to_buffer()
    assert controller.edit_buffer["tags"] == ["consumable", "elixir"]
    assert controller._delete_effect("damage") is True
    assert "damage" not in controller.edit_buffer["effects"]
    assert controller._delete_tag(0) is True
    assert controller.edit_buffer["tags"] == ["elixir"]


def test_item_editor_controller_add_tag_appends_focuses_widget_and_stays_save_valid(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["tags"] = ["consumable"]
    controller.enter_edit_mode(item)

    assert controller._add_tag() is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["tags"] == ["consumable", "new_tag"]
    assert "tags.1" in controller.text_inputs()
    assert controller.text_input("tags.1").text == "new_tag"
    assert controller.focused_field() == "tags.1"
    assert controller.text_input("tags.1").focused is True
    assert validate_item(controller.edit_buffer, [controller.edit_buffer]) == []


def test_item_editor_controller_add_tag_normalizes_missing_or_non_list_tags(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item.pop("tags")
    controller.enter_edit_mode(item)

    assert controller._add_tag() is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["tags"] == ["new_tag"]

    controller.edit_buffer["tags"] = "not-a-list"
    controller._rebuild_text_inputs(controller.edit_buffer)

    assert controller._add_tag() is True
    assert controller.edit_buffer["tags"] == ["new_tag"]


def test_item_editor_controller_add_effect_adds_unique_int_widget_and_stays_save_valid(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {"heal": 25}
    controller.enter_edit_mode(item)

    assert controller._add_effect() is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["effects"]["new_effect"] == 0
    assert isinstance(controller.edit_buffer["effects"]["new_effect"], int)
    assert "effects.new_effect" in controller.text_inputs()
    assert controller.text_input("effects.new_effect").text == "0"
    assert controller.focused_field() == "effects.new_effect"
    assert validate_item(controller.edit_buffer, [controller.edit_buffer]) == []

    controller.text_input("effects.new_effect").text = "7"
    controller.sync_widgets_to_buffer()

    assert controller.edit_buffer["effects"]["new_effect"] == 7
    assert isinstance(controller.edit_buffer["effects"]["new_effect"], int)


def test_item_editor_controller_added_effect_can_be_renamed_to_runtime_damage_key(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["effects"] = {}
    controller.enter_edit_mode(item)

    assert controller._add_effect() is True
    assert controller.edit_buffer is not None
    controller.text_input("effect_key.new_effect").text = "damage"
    controller.sync_widgets_to_buffer()
    controller.text_input("effects.damage").text = "7"
    controller.sync_widgets_to_buffer()

    effects = controller.edit_buffer["effects"]
    assert effects == {"damage": 7}
    assert float(effects.get("damage", effects.get("attack", 0)) or 0) == 7.0


def test_item_editor_controller_next_effect_key_skips_existing_names() -> None:
    assert _next_effect_key({}) == "new_effect"
    assert _next_effect_key({"new_effect": 0}) == "new_effect_2"
    assert _next_effect_key({"new_effect": 0, "new_effect_2": 1}) == "new_effect_3"


def test_item_editor_controller_add_complex_entries_are_append_only(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    item = _item()
    item["name"] = "Keep Name"
    item["tags"] = ["consumable", "potion"]
    item["effects"] = {"heal": 25, "quest.flag": "done"}
    controller.enter_edit_mode(item)
    assert controller.edit_buffer is not None
    before = copy.deepcopy(controller.edit_buffer)

    assert controller._add_tag() is True
    assert controller._add_effect() is True

    assert controller.edit_buffer["tags"][:-1] == before["tags"]
    assert controller.edit_buffer["tags"][-1] == "new_tag"
    for key, value in before["effects"].items():
        assert controller.edit_buffer["effects"][key] == value
    assert controller.edit_buffer["effects"]["new_effect"] == 0
    for field in ("id", "name", "description", "icon", "stackable", "max_stack"):
        assert controller.edit_buffer[field] == before[field]


def test_item_editor_controller_add_routing_coexists_with_delete_routing(tmp_path: Path) -> None:
    actions = iter([TAG_ADD_ACTION, EFFECT_ADD_ACTION, "tag.0.delete", "effect.heal.delete"])
    overlay = SimpleNamespace(complex_entry_action_at=lambda _x, _y: next(actions))
    controller = EditorItemEditorController(_editor(tmp_path, overlay))
    item = _item()
    item["tags"] = ["consumable"]
    item["effects"] = {"heal": 25}
    controller.enter_edit_mode(item)

    assert controller.handle_item_editor_mouse_click(1.0, 1.0) is True
    assert controller.handle_item_editor_mouse_click(1.0, 1.0) is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["tags"] == ["consumable", "new_tag"]
    assert controller.edit_buffer["effects"] == {"heal": 25, "new_effect": 0}

    assert controller.handle_item_editor_mouse_click(1.0, 1.0) is True
    assert controller.handle_item_editor_mouse_click(1.0, 1.0) is True

    assert controller.edit_buffer["tags"] == ["new_tag"]
    assert controller.edit_buffer["effects"] == {"new_effect": 0}
