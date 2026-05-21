from __future__ import annotations

import json

import pytest

import engine.inventory as inventory_module
from engine.editor.item_editor_model import save_items
from engine.inventory import load_item_database

pytestmark = [pytest.mark.fast]


def _item(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "healing_potion",
        "name": "Healing Potion",
        "description": "Restores HP.",
        "icon": "assets/items/healing_potion.png",
        "stackable": True,
        "max_stack": 5,
        "tags": ["consumable", "potion"],
        "effects": {"heal": 25},
    }
    payload.update(overrides)
    return payload


def test_save_items_round_trips_all_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(inventory_module, "_ITEM_DB_CACHE", None)
    target = tmp_path / "assets" / "data" / "items.json"
    item = _item()

    save_items([item], target)

    loaded = load_item_database(tmp_path).get("healing_potion")
    assert loaded is not None
    assert loaded.id == "healing_potion"
    assert loaded.name == "Healing Potion"
    assert loaded.description == "Restores HP."
    assert loaded.icon == "assets/items/healing_potion.png"
    assert loaded.stackable is True
    assert loaded.max_stack == 5
    assert loaded.tags == ["consumable", "potion"]
    assert loaded.effects == {"heal": 25}


def test_save_items_invalid_payload_raises_and_does_not_write(tmp_path) -> None:
    target = tmp_path / "assets" / "data" / "items.json"

    with pytest.raises(ValueError, match="id is required"):
        save_items([_item(id="")], target)

    assert not target.exists()


def test_save_items_invalid_payload_leaves_existing_file_unchanged(tmp_path) -> None:
    target = tmp_path / "assets" / "data" / "items.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"items": [{"id": "existing"}]}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="max_stack must be a positive integer"):
        save_items([_item(max_stack="many")], target)

    assert target.read_text(encoding="utf-8") == '{"items": [{"id": "existing"}]}\n'


def test_save_items_rejects_zero_max_stack(tmp_path) -> None:
    target = tmp_path / "assets" / "data" / "items.json"

    with pytest.raises(ValueError, match="max_stack must be a positive integer"):
        save_items([_item(max_stack=0)], target)

    assert not target.exists()


def test_save_items_clears_cached_item_database(tmp_path, monkeypatch) -> None:
    target = tmp_path / "assets" / "data" / "items.json"
    monkeypatch.setattr(inventory_module, "_ITEM_DB_CACHE", object())

    save_items([_item(id="fresh_item", name="Fresh Item")], target)

    assert inventory_module._ITEM_DB_CACHE is None


def test_save_items_output_keeps_trailing_newline_and_normalized_fields(tmp_path) -> None:
    target = tmp_path / "assets" / "data" / "items.json"

    save_items([_item()], target)

    raw = target.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    item_payload = json.loads(raw)["items"][0]
    assert set(item_payload) == {
        "id",
        "name",
        "description",
        "icon",
        "stackable",
        "max_stack",
        "tags",
        "effects",
    }
