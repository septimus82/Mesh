"""Tests for quest definition validation and migration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.quest_runtime.validation import (
    QUEST_DEFINITION_SCHEMA_VERSION,
    QuestValidationError,
    migrate_quest_definition,
    sort_quest_validation_errors,
    validate_quest_definition,
    validate_quest_file,
)
from tests._typing import as_any


class TestQuestValidationError:
    """Test QuestValidationError dataclass."""

    def test_str_full_context(self):
        """Error string includes all context."""
        err = QuestValidationError(
            file_path="assets/data/quests.json",
            json_path="quests[0].stages[1].id",
            code="stage.id.required",
            message="Stage must have an id",
            hint="Add a unique identifier",
        )
        s = str(err)
        assert "stage.id.required" in s
        assert "assets/data/quests.json" in s
        assert "quests[0].stages[1].id" in s
        assert "Stage must have an id" in s
        assert "Add a unique identifier" in s

    def test_str_minimal(self):
        """Error string works with minimal context."""
        err = QuestValidationError(
            file_path="",
            json_path="",
            code="test.code",
            message="Test message",
        )
        s = str(err)
        assert "test.code" in s
        assert "Test message" in s


class TestValidateQuestDefinition:
    """Test validate_quest_definition function."""

    def test_valid_minimal_quest(self):
        """Minimal valid quest passes validation."""
        quest = {
            "id": "test_quest",
            "title": "Test Quest",
            "stages": [
                {"id": "stage_1", "title": "First Stage"}
            ],
        }
        errors = validate_quest_definition(quest)
        assert errors == []

    def test_valid_full_quest(self):
        """Full quest with all fields passes validation."""
        quest = {
            "id": "full_quest",
            "title": "Full Quest",
            "description": "A complete quest with all fields",
            "auto_start": True,
            "requires_flags": ["prereq_flag"],
            "blocks_flags": ["blocker_flag"],
            "stages": [
                {
                    "id": "intro",
                    "title": "Introduction",
                    "text": "Talk to the guide",
                    "start_on_event": {"type": "scene_loaded"},
                    "complete_on": {
                        "type": "dialogue_choice",
                        "payload": {"choice_id": "accept"},
                    },
                },
                {
                    "id": "collect",
                    "title": "Collect Items",
                    "requirements": {
                        "counters": {"items_collected": 5},
                        "flags": {"area_unlocked": True},
                    },
                },
            ],
            "reward": {
                "set_flags": {"quest_complete": True},
                "inc_counters": {"gold": 100},
            },
        }
        errors = validate_quest_definition(quest)
        assert errors == []

    def test_missing_id(self):
        """Missing quest id produces error."""
        quest = {"title": "No ID Quest", "stages": [{"id": "s1", "title": "S1"}]}
        errors = validate_quest_definition(quest)
        assert len(errors) == 1
        assert errors[0].code == "quest.id.required"

    def test_empty_id(self):
        """Empty quest id produces error."""
        quest = {"id": "", "title": "Empty ID", "stages": [{"id": "s1", "title": "S1"}]}
        errors = validate_quest_definition(quest)
        assert len(errors) == 1
        assert errors[0].code == "quest.id.required"

    def test_invalid_id_format(self):
        """Invalid characters in id produce error."""
        quest = {"id": "bad id!", "title": "Bad ID", "stages": [{"id": "s1", "title": "S1"}]}
        errors = validate_quest_definition(quest)
        assert any(e.code == "quest.id.format" for e in errors)

    def test_missing_title(self):
        """Missing title produces error."""
        quest = {"id": "no_title", "stages": [{"id": "s1", "title": "S1"}]}
        errors = validate_quest_definition(quest)
        assert len(errors) == 1
        assert errors[0].code == "quest.title.required"

    def test_missing_stages(self):
        """Missing stages array produces error."""
        quest = {"id": "no_stages", "title": "No Stages"}
        errors = validate_quest_definition(quest)
        assert len(errors) == 1
        assert errors[0].code == "quest.stages.required"

    def test_empty_stages(self):
        """Empty stages array produces error."""
        quest = {"id": "empty_stages", "title": "Empty Stages", "stages": []}
        errors = validate_quest_definition(quest)
        assert len(errors) == 1
        assert errors[0].code == "quest.stages.empty"

    def test_stages_not_array(self):
        """Non-array stages produces error."""
        quest = {"id": "bad_stages", "title": "Bad Stages", "stages": "not_array"}
        errors = validate_quest_definition(quest)
        assert len(errors) == 1
        assert errors[0].code == "quest.stages.type"

    def test_stage_missing_id(self):
        """Stage without id produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"title": "No ID Stage"}],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "stage.id.required" for e in errors)

    def test_stage_duplicate_id(self):
        """Duplicate stage ids produce error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [
                {"id": "dup", "title": "First"},
                {"id": "dup", "title": "Second"},
            ],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "stage.id.duplicate" for e in errors)

    def test_stage_missing_title(self):
        """Stage without title produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"id": "s1"}],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "stage.title.required" for e in errors)

    def test_event_trigger_string_valid(self):
        """String event trigger is valid."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [
                {"id": "s1", "title": "S1", "complete_on": "collectible_picked"}
            ],
        }
        errors = validate_quest_definition(quest)
        assert errors == []

    def test_event_trigger_string_empty(self):
        """Empty string event trigger produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"id": "s1", "title": "S1", "complete_on": ""}],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "trigger.complete.empty" for e in errors)

    def test_event_trigger_object_missing_type(self):
        """Object trigger without type produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [
                {"id": "s1", "title": "S1", "complete_on": {"payload": {"x": 1}}}
            ],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "trigger.complete.type.required" for e in errors)

    def test_event_trigger_payload_not_dict(self):
        """Non-dict payload produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [
                {"id": "s1", "title": "S1", "complete_on": {"type": "test", "payload": "bad"}}
            ],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "trigger.complete.payload.type" for e in errors)

    def test_requirements_counters_non_numeric(self):
        """Non-numeric counter target produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [
                {
                    "id": "s1",
                    "title": "S1",
                    "requirements": {"counters": {"count": "five"}},
                }
            ],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "stage.requirements.counters.value.type" for e in errors)

    def test_reward_set_flags_non_bool(self):
        """Non-boolean flag value in reward produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"id": "s1", "title": "S1"}],
            "reward": {"set_flags": {"flag": "yes"}},
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "reward.set_flags.value.type" for e in errors)

    def test_reward_inc_counters_non_numeric(self):
        """Non-numeric counter value in reward produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"id": "s1", "title": "S1"}],
            "reward": {"inc_counters": {"gold": "lots"}},
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "reward.inc_counters.value.type" for e in errors)

    def test_requires_flags_not_array(self):
        """Non-array requires_flags produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"id": "s1", "title": "S1"}],
            "requires_flags": "bad",
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "quest.requires_flags.type" for e in errors)

    def test_blocks_flags_item_not_string(self):
        """Non-string item in blocks_flags produces error."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"id": "s1", "title": "S1"}],
            "blocks_flags": [123],
        }
        errors = validate_quest_definition(quest)
        assert any(e.code == "quest.blocks_flags.item.type" for e in errors)

    def test_strict_mode_description(self):
        """Strict mode requires description."""
        quest = {
            "id": "quest",
            "title": "Quest",
            "stages": [{"id": "s1", "title": "S1"}],
        }
        errors = validate_quest_definition(quest, strict=True)
        assert any(e.code == "quest.description.recommended" for e in errors)


class TestValidateQuestFile:
    """Test validate_quest_file function."""

    def test_valid_file(self):
        """Valid quest file passes validation."""
        data = {
            "schema_version": 1,
            "quests": [
                {"id": "q1", "title": "Quest 1", "stages": [{"id": "s1", "title": "S1"}]}
            ],
        }
        errors = validate_quest_file(Path("test.json"), data)
        assert errors == []

    def test_not_dict(self):
        """Non-dict root produces error."""
        errors = validate_quest_file(Path("test.json"), [])
        assert len(errors) == 1
        assert errors[0].code == "file.root.type"

    def test_missing_quests_key(self):
        """Missing quests key produces error."""
        errors = validate_quest_file(Path("test.json"), {})
        assert len(errors) == 1
        assert errors[0].code == "file.quests.required"

    def test_quests_not_array(self):
        """Non-array quests produces error."""
        errors = validate_quest_file(Path("test.json"), {"quests": {}})
        assert len(errors) == 1
        assert errors[0].code == "file.quests.type"

    def test_duplicate_quest_ids(self):
        """Duplicate quest ids produce error."""
        data = {
            "quests": [
                {"id": "dup", "title": "First", "stages": [{"id": "s1", "title": "S1"}]},
                {"id": "dup", "title": "Second", "stages": [{"id": "s1", "title": "S1"}]},
            ],
        }
        errors = validate_quest_file(Path("test.json"), data)
        assert any(e.code == "file.quests.id.duplicate" for e in errors)

    def test_invalid_schema_version(self):
        """Invalid schema_version produces error."""
        data = {
            "schema_version": "bad",
            "quests": [{"id": "q1", "title": "Q1", "stages": [{"id": "s1", "title": "S1"}]}],
        }
        errors = validate_quest_file(Path("test.json"), data)
        assert any(e.code == "file.schema_version.invalid" for e in errors)


class TestMigrateQuestDefinition:
    """Test migrate_quest_definition function."""

    def test_migrate_v0_to_v1(self):
        """V0 definitions get schema_version field."""
        data = {
            "quests": [{"id": "q1", "title": "Q1", "stages": []}],
        }
        result = migrate_quest_definition(data)
        assert result["schema_version"] == 1

    def test_migrate_dict_quests_to_list(self):
        """Dict-style quests converted to list."""
        data = {
            "quests": {"q1": {"id": "q1", "title": "Q1"}},
        }
        result = migrate_quest_definition(data)
        assert isinstance(result["quests"], list)
        assert len(result["quests"]) == 1

    def test_migrate_dict_stages_to_list(self):
        """Dict-style stages converted to list."""
        data = {
            "quests": [
                {"id": "q1", "title": "Q1", "stages": {"s1": {"id": "s1", "title": "S1"}}}
            ],
        }
        result = migrate_quest_definition(data)
        assert isinstance(result["quests"][0]["stages"], list)

    def test_already_current_version(self):
        """Already current version is unchanged."""
        data = {
            "schema_version": QUEST_DEFINITION_SCHEMA_VERSION,
            "quests": [{"id": "q1", "title": "Q1", "stages": []}],
        }
        result = migrate_quest_definition(data)
        assert result["schema_version"] == QUEST_DEFINITION_SCHEMA_VERSION

    def test_future_version_raises(self):
        """Future version raises ValueError."""
        data = {"schema_version": 999, "quests": []}
        with pytest.raises(ValueError, match="newer game version"):
            migrate_quest_definition(data)

    def test_non_dict_returns_empty(self):
        """Non-dict input returns empty structure."""
        result = migrate_quest_definition(as_any([]))
        assert result["schema_version"] == QUEST_DEFINITION_SCHEMA_VERSION
        assert result["quests"] == []


class TestSortQuestValidationErrors:
    """Test sort_quest_validation_errors function."""

    def test_sorts_by_file_then_path(self):
        """Errors sorted by file path then JSON path."""
        errors = [
            QuestValidationError("b.json", "quests[1]", "code", "msg"),
            QuestValidationError("a.json", "quests[0]", "code", "msg"),
            QuestValidationError("a.json", "quests[1]", "code", "msg"),
        ]
        sorted_errors = sort_quest_validation_errors(errors)
        assert sorted_errors[0].file_path == "a.json"
        assert sorted_errors[0].json_path == "quests[0]"
        assert sorted_errors[1].file_path == "a.json"
        assert sorted_errors[1].json_path == "quests[1]"
        assert sorted_errors[2].file_path == "b.json"


class TestQuestInspectorIntegration:
    """Test quest inspector integration with QuestManager."""

    def test_get_inspector_state_returns_summary(self):
        """get_inspector_state returns comprehensive summary."""
        # Create mock window
        mock_window = MagicMock()
        mock_window.game_state.values = {"quests": {}}

        # Create QuestManager with mock data path
        with patch("engine.quests.resolve_path") as mock_resolve:
            mock_resolve.return_value = Path("nonexistent.json")

            from engine.quests import QuestManager
            manager = QuestManager(mock_window)

            # Manually inject a definition for testing
            manager._definitions = {
                "test_quest": {
                    "id": "test_quest",
                    "title": "Test Quest",
                    "stages": [
                        {"id": "s1", "title": "Stage 1"},
                        {"id": "s2", "title": "Stage 2"},
                    ],
                    "stage_lookup": {
                        "s1": {"id": "s1", "title": "Stage 1"},
                        "s2": {"id": "s2", "title": "Stage 2"},
                    },
                    "requires_flags": [],
                    "blocks_flags": [],
                },
            }

            # Set up state
            mock_window.game_state.values["quests"] = {
                "test_quest": {
                    "status": "active",
                    "current_stage": "s1",
                    "awaiting_stage": None,
                    "completed_stages": [],
                }
            }

            result = manager.get_inspector_state()

            assert result["total_quests"] == 1
            assert result["active_count"] == 1
            assert result["completed_count"] == 0
            assert result["inactive_count"] == 0
            assert len(result["quests"]) == 1

            quest_info = result["quests"][0]
            assert quest_info["id"] == "test_quest"
            assert quest_info["status"] == "active"
            assert quest_info["progress"] == "0/2"
            assert quest_info["current_stage"]["id"] == "s1"


class TestGoldenQuestsFileValidation:
    """Test validation against the actual quests.json file."""

    def test_existing_quests_file_validates(self):
        """The existing quests.json file should pass validation.
        
        Note: Test/placeholder quests with empty stages are filtered out
        by the normalize step, so we only validate quests that would
        actually be loaded at runtime.
        """
        quests_path = Path("assets/data/quests.json")
        if not quests_path.exists():
            pytest.skip("quests.json not found")

        with open(quests_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Migrate first (may not have schema_version)
        data = migrate_quest_definition(data)

        # Validate
        errors = validate_quest_file(quests_path, data)

        # Filter out errors for quests that are known test/placeholder entries
        # These are skipped by the normalizer anyway (empty stages)
        real_errors = [
            err for err in errors
            if not (
                err.code in ("quest.stages.empty", "quest.stages.required")
                and "test_quest" in err.message
            )
        ]

        # Print any errors for debugging
        for err in real_errors:
            print(f"Validation error: {err}")

        # Should have no real errors
        assert real_errors == [], f"Existing quests.json has {len(real_errors)} validation errors"

