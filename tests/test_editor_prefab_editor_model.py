from __future__ import annotations

import pytest

from engine.editor.prefab_editor_model import PrefabEditorModel

pytestmark = [pytest.mark.fast]


class _FakePrefabManager:
    def __init__(self, prefabs: dict[str, dict[str, object]]) -> None:
        self.prefabs = prefabs
        self.load_calls: list[bool] = []

    def load(self, *, force: bool = False) -> None:
        self.load_calls.append(bool(force))


def _manager() -> _FakePrefabManager:
    return _FakePrefabManager(
        {
            "torch_wisp": {
                "id": "torch_wisp",
                "display_name": "Torch Wisp",
                "entity": {
                    "sprite": "assets/placeholder.png",
                    "behaviours": ["EnemyAI"],
                    "behaviour_config": {"Health": {"max": 8}},
                    "encounter_cost": 2,
                },
                "metadata": {"author": "core"},
                "tags": ["enemy", "fire"],
            },
            "controller": {
                "id": "controller",
                "display_name": "Controller",
                "entity": {"sprite": None, "behaviours": ["ActionListRunner"]},
                "tags": ["controller"],
            },
        }
    )


def test_prefab_editor_model_loads_real_prefabs() -> None:
    model = PrefabEditorModel.load()

    assert model.prefab_count > 0
    assert any(prefab.get("id") == "player" for prefab in model.prefabs())


def test_prefab_editor_model_reload_uses_injected_manager() -> None:
    manager = _manager()
    model = PrefabEditorModel.load(manager)

    assert manager.load_calls == [True]
    assert model.prefab_count == 2
    assert model.list_rows()[0] == ("Torch Wisp", "torch_wisp")


def test_prefab_editor_model_selection_mutation() -> None:
    model = PrefabEditorModel.load(_manager())

    assert model.selected_index() == 0
    assert model.set_selected_index(1) is True
    assert model.selected_index() == 1
    assert model.selected_prefab() is not None
    assert model.selected_prefab()["id"] == "controller"
    assert model.set_selected_index(999) is False
    assert model.selected_index() == 1


def test_prefab_editor_model_detail_rows_split_scalar_and_complex_fields() -> None:
    model = PrefabEditorModel.load(_manager())

    assert ("ID", "torch_wisp") in model.scalar_detail_rows()
    assert ("Display name", "Torch Wisp") in model.scalar_detail_rows()
    assert ("Sprite", "assets/placeholder.png") in model.scalar_detail_rows()
    assert ("Encounter cost", "2") in model.scalar_detail_rows()
    assert ("Tags", "enemy, fire") in model.complex_detail_rows()
    assert ("Behaviours", "EnemyAI") in model.complex_detail_rows()
    assert ("Behaviour config", '{"Health":{"max":8}}') in model.complex_detail_rows()
    assert ("Metadata", '{"author":"core"}') in model.complex_detail_rows()


def test_prefab_editor_model_empty_manager_has_no_selection() -> None:
    model = PrefabEditorModel.load(_FakePrefabManager({}))

    assert model.prefab_count == 0
    assert model.selected_index() == 0
    assert model.selected_prefab() is None
    assert model.scalar_detail_rows() == []
    assert model.complex_detail_rows() == []
