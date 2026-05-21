from __future__ import annotations

import json

import pytest

from engine.editor.item_editor_model import ItemEditorModel, validate_item

pytestmark = [pytest.mark.fast]


def _write_items(tmp_path, entries: list[dict[str, object]]) -> None:
    data_dir = tmp_path / "assets" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "items.json").write_text(json.dumps({"items": entries}), encoding="utf-8")


def test_item_editor_model_loads_real_database() -> None:
    model = ItemEditorModel.load()

    assert model.item_count > 0
    assert model.selected_item is not None
    assert any(item.id == "healing_potion" for item in model.items)


def test_item_editor_model_normalizes_missing_optional_fields(tmp_path) -> None:
    _write_items(tmp_path, [{"id": "plain_rock"}])

    model = ItemEditorModel.load(tmp_path)
    item = model.selected_item

    assert item is not None
    assert item.id == "plain_rock"
    assert item.name == "plain_rock"
    assert item.description == ""
    assert item.icon is None
    assert item.stackable is False
    assert item.max_stack == 1
    assert item.tags == []
    assert item.effects == {}


def test_item_editor_model_duplicate_id_raises(tmp_path) -> None:
    _write_items(tmp_path, [{"id": "potion"}, {"id": "potion"}])

    with pytest.raises(ValueError, match="Duplicate item id 'potion'"):
        ItemEditorModel.load(tmp_path)


def test_item_editor_model_skips_missing_id_entries(tmp_path) -> None:
    _write_items(tmp_path, [{"name": "Missing"}, {"id": "valid_item", "name": "Valid"}])

    model = ItemEditorModel.load(tmp_path)

    assert [item.id for item in model.items] == ["valid_item"]


def test_item_editor_model_selection_and_detail_rows(tmp_path) -> None:
    _write_items(
        tmp_path,
        [
            {"id": "coin", "name": "Coin", "stackable": True, "max_stack": 99, "tags": ["currency"]},
            {"id": "sword", "name": "Sword", "effects": {"damage": 3, "tier": 1}},
        ],
    )

    model = ItemEditorModel.load(tmp_path)

    assert model.list_rows() == ["Coin (coin)", "Sword (sword)"]
    assert model.select_index(1) is True
    assert model.selected_item is not None
    assert model.selected_item.id == "sword"
    assert ("Effects", "damage=3, tier=1") in model.selected_detail_rows()


def test_item_editor_model_detail_rows_skip_empty_default_fields(tmp_path) -> None:
    _write_items(tmp_path, [{"id": "plain_key", "name": "Plain Key"}])

    model = ItemEditorModel.load(tmp_path)

    assert model.selected_detail_rows() == [
        ("ID", "plain_key"),
        ("Name", "Plain Key"),
    ]


def test_validate_item_rejects_empty_id() -> None:
    errors = validate_item({"id": "", "max_stack": 1}, [{"id": "", "max_stack": 1}])

    assert "id is required" in errors


def test_validate_item_rejects_duplicate_id() -> None:
    items = [{"id": "potion", "max_stack": 1}, {"id": "potion", "max_stack": 1}]

    errors = validate_item(items[0], items)

    assert "id 'potion' is already used" in errors


def test_validate_item_rejects_non_numeric_max_stack() -> None:
    errors = validate_item({"id": "potion", "max_stack": "many"}, [{"id": "potion", "max_stack": "many"}])

    assert "max_stack must be a positive integer" in errors


def test_validate_item_rejects_zero_max_stack() -> None:
    errors = validate_item({"id": "potion", "max_stack": 0}, [{"id": "potion", "max_stack": 0}])

    assert "max_stack must be a positive integer" in errors


def test_validate_item_accepts_valid_item() -> None:
    item = {"id": "potion", "max_stack": 1}

    assert validate_item(item, [item]) == []
