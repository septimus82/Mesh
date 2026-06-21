from __future__ import annotations

import pytest

from engine.editor.prefab_editor_model import (
    PrefabEditorModel,
    behaviour_config_inner_rows,
    behaviour_config_scalar_value_paths,
    complex_detail_rows_for_prefab,
    complex_entry_rows,
    validate_prefab_entries,
)

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

    assert ("ID", "torch_wisp", "id") in model.scalar_detail_rows()
    assert ("Display name", "Torch Wisp", "display_name") in model.scalar_detail_rows()
    assert ("Sprite", "assets/placeholder.png", "entity.sprite") in model.scalar_detail_rows()
    assert ("Encounter cost", "2", "entity.encounter_cost") in model.scalar_detail_rows()
    assert ("Tags", "enemy, fire") in model.complex_detail_rows()
    assert ("Behaviours", "EnemyAI") in model.complex_detail_rows()
    assert ("Behaviour config", '{"Health":{"max":8}}') in model.complex_detail_rows()
    assert ("Metadata", '{"author":"core"}') in model.complex_detail_rows()


def test_prefab_editor_complex_entry_rows_list_family_preserves_order_and_skips_non_strings() -> None:
    prefab = {
        "tags": ["enemy", 3, "fire"],
        "require_flags": ["flag_a"],
        "forbid_flags": ["flag_b"],
        "entity": {
            "behaviours": ["EnemyAI", object(), "Health"],
            "require_flags": ["entity_flag"],
        },
    }

    assert complex_entry_rows(prefab, "tags") == [("Tag 0", "enemy"), ("Tag 2", "fire")]
    assert complex_entry_rows(prefab, "require_flags") == [("Require flag 0", "flag_a")]
    assert complex_entry_rows(prefab, "forbid_flags") == [("Forbid flag 0", "flag_b")]
    assert complex_entry_rows(prefab, "entity.behaviours") == [
        ("Behaviour 0", "EnemyAI"),
        ("Behaviour 2", "Health"),
    ]
    assert complex_entry_rows(prefab, "entity.require_flags") == [("Entity require flag 0", "entity_flag")]


def test_prefab_editor_complex_entry_rows_metadata_are_sorted() -> None:
    prefab = {"metadata": {"zeta": "last", "author": "core"}}

    assert complex_entry_rows(prefab, "metadata") == [("author", "core"), ("zeta", "last")]


def test_prefab_editor_complex_entry_rows_behaviour_config_are_top_level_compact_json() -> None:
    prefab = {
        "entity": {
            "behaviour_config": {
                "Health": {"max": 8, "regen": False},
                "EnemyAI": {"speed": 1.5},
            }
        }
    }

    assert complex_entry_rows(prefab, "entity.behaviour_config") == [
        ("EnemyAI", '{"speed":1.5}'),
        ("Health", '{"max":8,"regen":false}'),
    ]


def test_prefab_editor_behaviour_config_inner_rows_scalars_are_sorted_and_formatted() -> None:
    prefab = {
        "entity": {
            "behaviour_config": {
                "Health": {"max": 8, "regen": False},
                "EnemyAI": {"speed": 1.5},
            }
        }
    }

    assert behaviour_config_inner_rows(prefab) == [
        ("EnemyAI.speed", "1.5"),
        ("Health.max", "8"),
        ("Health.regen", "false"),
    ]


def test_prefab_editor_behaviour_config_inner_rows_compact_structured_values() -> None:
    prefab = {
        "entity": {
            "behaviour_config": {
                "DialogueRunner": {"script": {"start": {"text": "Hello"}}},
                "TriggerVolume": {"target_tags": ["player", "ally"]},
            }
        }
    }

    assert behaviour_config_inner_rows(prefab) == [
        ("DialogueRunner.script", '{"start":{"text":"Hello"}}'),
        ("TriggerVolume.target_tags", '["player","ally"]'),
    ]


def test_prefab_editor_behaviour_config_inner_rows_degrade_on_missing_or_wrong_shapes() -> None:
    assert behaviour_config_inner_rows({}) == []
    assert behaviour_config_inner_rows({"entity": {"behaviour_config": "Health"}}) == []
    assert behaviour_config_inner_rows({"entity": {"behaviour_config": {"Health": "max=8"}}}) == []


def test_prefab_editor_behaviour_config_scalar_value_paths_include_scalars_only() -> None:
    prefab = {
        "entity": {
            "behaviour_config": {
                "DialogueRunner": {"script": {"start": {}}, "start_node": "start"},
                "Health": {"enabled": True, "hp": 4.5, "max": 8, "none": None},
                "TriggerVolume": {"target_tags": ["player"]},
            }
        }
    }

    assert behaviour_config_scalar_value_paths(prefab) == [
        ("entity.behaviour_config.DialogueRunner.start_node", "DialogueRunner.start_node"),
        ("entity.behaviour_config.Health.enabled", "Health.enabled"),
        ("entity.behaviour_config.Health.hp", "Health.hp"),
        ("entity.behaviour_config.Health.max", "Health.max"),
    ]


def test_prefab_editor_behaviour_config_scalar_value_paths_degrade_on_wrong_shapes() -> None:
    assert behaviour_config_scalar_value_paths({}) == []
    assert behaviour_config_scalar_value_paths({"entity": {"behaviour_config": []}}) == []
    assert behaviour_config_scalar_value_paths({"entity": {"behaviour_config": {"Health": None}}}) == []


def test_prefab_editor_complex_entry_rows_degrade_on_empty_missing_or_wrong_shapes() -> None:
    prefab = {
        "tags": "enemy",
        "metadata": [],
        "entity": {
            "behaviours": None,
            "behaviour_config": "Health",
        },
    }

    assert complex_entry_rows(prefab, "tags") == []
    assert complex_entry_rows(prefab, "missing") == []
    assert complex_entry_rows(prefab, "metadata") == []
    assert complex_entry_rows(prefab, "entity.behaviours") == []
    assert complex_entry_rows(prefab, "entity.behaviour_config") == []


def test_prefab_editor_complex_detail_rows_for_prefab_include_field_paths() -> None:
    prefab = {
        "tags": ["enemy"],
        "metadata": {"author": "core"},
        "entity": {"behaviours": ["EnemyAI"]},
    }

    assert complex_detail_rows_for_prefab(prefab) == [
        ("tags", "Tags", "enemy"),
        ("entity.behaviours", "Behaviours", "EnemyAI"),
        ("metadata", "Metadata", '{"author":"core"}'),
    ]


def test_prefab_editor_model_empty_manager_has_no_selection() -> None:
    model = PrefabEditorModel.load(_FakePrefabManager({}))

    assert model.prefab_count == 0
    assert model.selected_index() == 0
    assert model.selected_prefab() is None
    assert model.scalar_detail_rows() == []
    assert model.complex_detail_rows() == []


def test_validate_prefab_entries_reports_duplicate_ids(tmp_path) -> None:
    errors = validate_prefab_entries(
        [
            {"id": "same_id", "entity": {}},
            {"id": "same_id", "entity": {}},
        ],
        tmp_path / "assets" / "prefabs.json",
    )

    assert any("duplicate prefab id 'same_id'" in error for error in errors)


def test_validate_prefab_entries_reports_single_prefab_schema_errors(tmp_path) -> None:
    errors = validate_prefab_entries(
        [{"id": "", "entity": {}}],
        tmp_path / "assets" / "prefabs.json",
    )

    assert any("'id' must be a non-empty string" in error for error in errors)
