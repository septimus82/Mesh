"""Tests for entity and quest state save/restore.

Tests cover:
- SavedEntityState serialization/deserialization
- SavedQuestState serialization/deserialization
- Round-trip determinism for entities and quests
- Migration from v0/v1 to v2
- Unknown field preservation (x_ namespace)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from engine.save_runtime.entity_state import (
    SavedEntityState,
    apply_entities,
    apply_entity_state,
    migrate_entity_state_v0,
    serialize_entities,
    serialize_entity,
)
from engine.save_runtime.quest_state import (
    QUEST_STATE_SCHEMA_VERSION,
    SavedQuestState,
    apply_quests,
    migrate_quest_state_v0,
    serialize_quests,
)
from engine.save_runtime.schema import (
    SAVE_SCHEMA_VERSION,
    SaveValidationError,
    migrate_save,
    validate_save,
)

# --------------------------------------------------------------------------- #
# Test Fixtures
# --------------------------------------------------------------------------- #


@dataclass
class MockSprite:
    """Mock sprite for testing entity serialization."""

    mesh_name: str = ""
    center_x: float = 0.0
    center_y: float = 0.0
    mesh_tag: str | None = None
    mesh_tags: list[str] = field(default_factory=list)
    mesh_entity_data: dict[str, Any] = field(default_factory=dict)
    mesh_animator: Any = None
    mesh_behaviours_runtime: list[Any] = field(default_factory=list)


@dataclass
class MockAnimator:
    """Mock animator for testing animation state."""

    current_animation: str = "idle"

    def play(self, animation: str) -> None:
        self.current_animation = animation


class MockBehaviour:
    """Mock behaviour with saveable state."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self._state = state or {}

    def saveable_state(self) -> dict[str, Any]:
        return dict(self._state)

    def restore_state(self, state: dict[str, Any]) -> None:
        self._state = dict(state)


@dataclass
class MockQuest:
    """Mock quest for testing quest serialization."""

    id: str = ""
    state: str = "inactive"
    current_step: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    timestamp_started: str | None = None
    timestamp_completed: str | None = None


class MockQuestManager:
    """Mock quest manager for testing."""

    def __init__(self) -> None:
        self._quests: dict[str, MockQuest] = {}

    def register_quest(self, data: dict[str, Any]) -> MockQuest:
        quest_id = str(data.get("id", ""))
        quest = MockQuest(
            id=quest_id,
            state=str(data.get("state", "inactive")),
        )
        self._quests[quest_id] = quest
        return quest

    def get_quest(self, quest_id: str) -> MockQuest | None:
        return self._quests.get(quest_id)

    def get_all_quests(self) -> list[MockQuest]:
        return list(self._quests.values())


class MockSceneController:
    """Mock scene controller for testing."""

    def __init__(self) -> None:
        self.all_sprites: list[MockSprite] = []


# --------------------------------------------------------------------------- #
# SavedEntityState Tests
# --------------------------------------------------------------------------- #


class TestSavedEntityState:
    """Tests for SavedEntityState dataclass."""

    def test_to_dict_minimal(self) -> None:
        """Minimal entity has only required fields."""
        state = SavedEntityState(entity_id="entity_1", x=10.0, y=20.0)
        d = state.to_dict()

        assert d["entity_id"] == "entity_1"
        assert d["x"] == 10.0
        assert d["y"] == 20.0
        assert "prefab_id" not in d
        assert "tags" not in d
        assert "animation_state" not in d

    def test_to_dict_full(self) -> None:
        """Full entity has all fields."""
        state = SavedEntityState(
            entity_id="player",
            prefab_id="player_prefab",
            x=100.0,
            y=200.0,
            tags=["player", "friendly"],
            animation_state="walking",
            behaviour_state={"PlayerController": {"facing": "right"}},
            x_extra={"x_custom": "value"},
        )
        d = state.to_dict()

        assert d["entity_id"] == "player"
        assert d["prefab_id"] == "player_prefab"
        assert d["x"] == 100.0
        assert d["y"] == 200.0
        assert d["tags"] == ["friendly", "player"]  # sorted
        assert d["animation_state"] == "walking"
        assert d["behaviour_state"]["PlayerController"]["facing"] == "right"
        assert d["x_custom"] == "value"

    def test_from_dict_minimal(self) -> None:
        """Parse minimal dict."""
        data = {"entity_id": "npc_1", "x": 50, "y": 75}
        state = SavedEntityState.from_dict(data)

        assert state.entity_id == "npc_1"
        assert state.x == 50.0
        assert state.y == 75.0
        assert state.prefab_id is None
        assert state.tags == []

    def test_from_dict_fallback_id(self) -> None:
        """Falls back to 'id' if 'entity_id' missing."""
        data = {"id": "fallback_entity", "x": 0, "y": 0}
        state = SavedEntityState.from_dict(data)

        assert state.entity_id == "fallback_entity"

    def test_from_dict_preserves_x_fields(self) -> None:
        """Unknown x_ fields are preserved."""
        data = {
            "entity_id": "test",
            "x": 0,
            "y": 0,
            "x_custom_field": {"nested": True},
            "x_another": 42,
        }
        state = SavedEntityState.from_dict(data)

        assert state.x_extra["x_custom_field"] == {"nested": True}
        assert state.x_extra["x_another"] == 42

    def test_round_trip(self) -> None:
        """to_dict -> from_dict preserves data."""
        original = SavedEntityState(
            entity_id="round_trip_test",
            prefab_id="test_prefab",
            x=123.456,
            y=789.012,
            tags=["a", "b", "c"],
            animation_state="attack",
            behaviour_state={"TestBehaviour": {"count": 5}},
            x_extra={"x_version": 1},
        )
        d = original.to_dict()
        restored = SavedEntityState.from_dict(d)

        assert restored.entity_id == original.entity_id
        assert restored.prefab_id == original.prefab_id
        assert restored.x == original.x
        assert restored.y == original.y
        assert sorted(restored.tags) == sorted(original.tags)
        assert restored.animation_state == original.animation_state
        assert restored.behaviour_state == original.behaviour_state
        assert restored.x_extra == original.x_extra


class TestSerializeEntity:
    """Tests for serialize_entity function."""

    def test_serialize_basic_sprite(self) -> None:
        """Serialize sprite with basic properties."""
        sprite = MockSprite(
            mesh_name="test_entity",
            center_x=100.0,
            center_y=200.0,
            mesh_tag="enemy",
        )
        state = serialize_entity(sprite)

        assert state is not None
        assert state.entity_id == "test_entity"
        assert state.x == 100.0
        assert state.y == 200.0
        assert "enemy" in state.tags

    def test_serialize_sprite_with_prefab(self) -> None:
        """Serialize sprite with prefab_id."""
        sprite = MockSprite(
            mesh_name="npc_1",
            center_x=50.0,
            center_y=75.0,
            mesh_entity_data={"prefab_id": "npc_vendor"},
        )
        state = serialize_entity(sprite)

        assert state is not None
        assert state.prefab_id == "npc_vendor"

    def test_serialize_sprite_with_animation(self) -> None:
        """Serialize sprite with animation state."""
        sprite = MockSprite(
            mesh_name="animated",
            center_x=0.0,
            center_y=0.0,
            mesh_animator=MockAnimator(current_animation="running"),
        )
        state = serialize_entity(sprite)

        assert state is not None
        assert state.animation_state == "running"

    def test_serialize_sprite_with_behaviour_state(self) -> None:
        """Serialize sprite with saveable behaviour state."""
        behaviour = MockBehaviour({"direction": "north", "speed": 5})
        sprite = MockSprite(
            mesh_name="with_behaviour",
            center_x=10.0,
            center_y=20.0,
            mesh_behaviours_runtime=[behaviour],
        )
        state = serialize_entity(sprite)

        assert state is not None
        assert "MockBehaviour" in state.behaviour_state
        assert state.behaviour_state["MockBehaviour"]["direction"] == "north"

    def test_serialize_sprite_without_name_returns_none(self) -> None:
        """Sprite without mesh_name returns None."""
        sprite = MockSprite(mesh_name="", center_x=0.0, center_y=0.0)
        state = serialize_entity(sprite)

        assert state is None


class TestSerializeEntities:
    """Tests for serialize_entities function."""

    def test_serialize_empty_scene(self) -> None:
        """Empty scene returns empty list."""
        controller = MockSceneController()
        result = serialize_entities(controller)

        assert result == []

    def test_serialize_multiple_entities(self) -> None:
        """Multiple entities are serialized and sorted."""
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="z_entity", center_x=0.0, center_y=0.0),
            MockSprite(mesh_name="a_entity", center_x=10.0, center_y=20.0),
            MockSprite(mesh_name="m_entity", center_x=5.0, center_y=5.0),
        ]
        result = serialize_entities(controller)

        assert len(result) == 3
        # Sorted by entity_id
        assert result[0]["entity_id"] == "a_entity"
        assert result[1]["entity_id"] == "m_entity"
        assert result[2]["entity_id"] == "z_entity"

    def test_serialize_deterministic(self) -> None:
        """Serialization is deterministic across multiple calls."""
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="b", center_x=1.0, center_y=2.0, mesh_tag="tag_b"),
            MockSprite(mesh_name="a", center_x=3.0, center_y=4.0, mesh_tag="tag_a"),
        ]

        result1 = serialize_entities(controller)
        result2 = serialize_entities(controller)

        assert json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)


class TestApplyEntityState:
    """Tests for apply_entity_state function."""

    def test_apply_position(self) -> None:
        """Position is applied to sprite."""
        sprite = MockSprite(mesh_name="test", center_x=0.0, center_y=0.0)
        state = SavedEntityState(entity_id="test", x=100.0, y=200.0)

        result = apply_entity_state(sprite, state)

        assert result is True
        assert sprite.center_x == 100.0
        assert sprite.center_y == 200.0

    def test_apply_tags(self) -> None:
        """Tags are applied to sprite."""
        sprite = MockSprite(mesh_name="test", center_x=0.0, center_y=0.0)
        state = SavedEntityState(entity_id="test", x=0.0, y=0.0, tags=["enemy", "boss"])

        apply_entity_state(sprite, state)

        assert sprite.mesh_tag == "enemy"

    def test_apply_animation_state(self) -> None:
        """Animation state is applied."""
        animator = MockAnimator(current_animation="idle")
        sprite = MockSprite(
            mesh_name="test",
            center_x=0.0,
            center_y=0.0,
            mesh_animator=animator,
        )
        state = SavedEntityState(
            entity_id="test", x=0.0, y=0.0, animation_state="attacking"
        )

        apply_entity_state(sprite, state)

        assert animator.current_animation == "attacking"

    def test_apply_behaviour_state(self) -> None:
        """Behaviour state is restored."""
        behaviour = MockBehaviour({"old": "data"})
        sprite = MockSprite(
            mesh_name="test",
            center_x=0.0,
            center_y=0.0,
            mesh_behaviours_runtime=[behaviour],
        )
        state = SavedEntityState(
            entity_id="test",
            x=0.0,
            y=0.0,
            behaviour_state={"MockBehaviour": {"new": "state", "count": 42}},
        )

        apply_entity_state(sprite, state)

        assert behaviour._state["new"] == "state"
        assert behaviour._state["count"] == 42


class TestApplyEntities:
    """Tests for apply_entities function."""

    def test_apply_to_matching_entities(self) -> None:
        """State is applied to entities with matching IDs."""
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="entity_1", center_x=0.0, center_y=0.0),
            MockSprite(mesh_name="entity_2", center_x=0.0, center_y=0.0),
        ]
        saved = [
            {"entity_id": "entity_1", "x": 100.0, "y": 100.0},
            {"entity_id": "entity_2", "x": 200.0, "y": 200.0},
        ]

        applied, missing = apply_entities(controller, saved)

        assert applied == 2
        assert missing == 0
        assert controller.all_sprites[0].center_x == 100.0
        assert controller.all_sprites[1].center_x == 200.0

    def test_missing_entities_counted(self) -> None:
        """Missing entities are counted."""
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="entity_1", center_x=0.0, center_y=0.0),
        ]
        saved = [
            {"entity_id": "entity_1", "x": 100.0, "y": 100.0},
            {"entity_id": "nonexistent", "x": 200.0, "y": 200.0},
        ]

        applied, missing = apply_entities(controller, saved)

        assert applied == 1
        assert missing == 1


class TestEntityMigration:
    """Tests for entity state migration."""

    def test_migrate_v0_id_to_entity_id(self) -> None:
        """v0 'id' field is migrated to 'entity_id'."""
        data = {"id": "old_entity", "x": 10, "y": 20}
        migrated = migrate_entity_state_v0(data)

        assert migrated["entity_id"] == "old_entity"
        assert "id" not in migrated

    def test_migrate_v0_tag_to_tags(self) -> None:
        """v0 'tag' field is migrated to 'tags'."""
        data = {"entity_id": "test", "tag": "enemy"}
        migrated = migrate_entity_state_v0(data)

        assert migrated["tags"] == ["enemy"]
        assert "tag" not in migrated

    def test_migrate_v0_adds_behaviour_state(self) -> None:
        """v0 gets empty behaviour_state."""
        data = {"entity_id": "test"}
        migrated = migrate_entity_state_v0(data)

        assert migrated["behaviour_state"] == {}


# --------------------------------------------------------------------------- #
# SavedQuestState Tests
# --------------------------------------------------------------------------- #


class TestSavedQuestState:
    """Tests for SavedQuestState dataclass."""

    def test_to_dict_minimal(self) -> None:
        """Minimal quest has only required fields."""
        state = SavedQuestState(quest_id="quest_1", state="active")
        d = state.to_dict()

        assert d["quest_id"] == "quest_1"
        assert d["state"] == "active"
        assert "current_step" not in d  # 0 is default, not included
        assert "counters" not in d

    def test_to_dict_full(self) -> None:
        """Full quest has all fields."""
        state = SavedQuestState(
            quest_id="main_quest",
            state="completed",
            current_step=5,
            counters={"kills": 10, "items": 3},
            timestamp_started="2026-01-01T00:00:00",
            timestamp_completed="2026-01-02T00:00:00",
            x_extra={"x_custom": "data"},
        )
        d = state.to_dict()

        assert d["quest_id"] == "main_quest"
        assert d["state"] == "completed"
        assert d["current_step"] == 5
        assert d["counters"]["kills"] == 10
        assert d["timestamp_started"] == "2026-01-01T00:00:00"
        assert d["timestamp_completed"] == "2026-01-02T00:00:00"
        assert d["x_custom"] == "data"

    def test_from_dict_minimal(self) -> None:
        """Parse minimal dict."""
        data = {"quest_id": "q1", "state": "inactive"}
        state = SavedQuestState.from_dict(data)

        assert state.quest_id == "q1"
        assert state.state == "inactive"
        assert state.current_step == 0
        assert state.counters == {}

    def test_from_dict_normalizes_state(self) -> None:
        """Invalid state is normalized to 'inactive'."""
        data = {"quest_id": "q1", "state": "INVALID_STATE"}
        state = SavedQuestState.from_dict(data)

        assert state.state == "inactive"

    def test_round_trip(self) -> None:
        """to_dict -> from_dict preserves data."""
        original = SavedQuestState(
            quest_id="round_trip",
            state="active",
            current_step=3,
            counters={"a": 1, "b": 2},
            timestamp_started="2026-01-01",
            x_extra={"x_test": True},
        )
        d = original.to_dict()
        restored = SavedQuestState.from_dict(d)

        assert restored.quest_id == original.quest_id
        assert restored.state == original.state
        assert restored.current_step == original.current_step
        assert restored.counters == original.counters
        assert restored.timestamp_started == original.timestamp_started
        assert restored.x_extra == original.x_extra


class TestSerializeQuests:
    """Tests for serialize_quests function."""

    def test_serialize_empty_manager(self) -> None:
        """Empty manager returns empty quests."""
        manager = MockQuestManager()
        result = serialize_quests(manager)

        assert result["schema_version"] == QUEST_STATE_SCHEMA_VERSION
        assert result["quests"] == {}

    def test_serialize_multiple_quests(self) -> None:
        """Multiple quests are serialized."""
        manager = MockQuestManager()
        manager.register_quest({"id": "quest_a", "state": "active"})
        manager.register_quest({"id": "quest_b", "state": "completed"})

        result = serialize_quests(manager)

        assert len(result["quests"]) == 2
        assert "quest_a" in result["quests"]
        assert "quest_b" in result["quests"]

    def test_serialize_deterministic(self) -> None:
        """Serialization is deterministic."""
        manager = MockQuestManager()
        manager.register_quest({"id": "z_quest", "state": "active"})
        manager.register_quest({"id": "a_quest", "state": "inactive"})

        result1 = serialize_quests(manager)
        result2 = serialize_quests(manager)

        assert json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)


class TestApplyQuests:
    """Tests for apply_quests function."""

    def test_apply_to_existing_quests(self) -> None:
        """State is applied to existing quests."""
        manager = MockQuestManager()
        quest = manager.register_quest({"id": "q1", "state": "inactive"})

        saved = {
            "schema_version": 1,
            "quests": {"q1": {"quest_id": "q1", "state": "completed"}},
        }

        applied, created = apply_quests(manager, saved)

        assert applied == 1
        assert created == 0
        assert quest.state == "completed"

    def test_creates_new_quests(self) -> None:
        """New quests are created if manager supports it."""
        manager = MockQuestManager()

        saved = {
            "schema_version": 1,
            "quests": {"new_quest": {"quest_id": "new_quest", "state": "active"}},
        }

        applied, created = apply_quests(manager, saved)

        assert applied == 0
        assert created == 1
        assert manager.get_quest("new_quest") is not None


class TestQuestMigration:
    """Tests for quest state migration."""

    def test_migrate_v0_adds_schema_version(self) -> None:
        """v0 gets schema_version."""
        data = {"quests": {}}
        migrated = migrate_quest_state_v0(data)

        assert migrated["schema_version"] == QUEST_STATE_SCHEMA_VERSION

    def test_migrate_v0_id_to_quest_id(self) -> None:
        """v0 'id' field is migrated to 'quest_id'."""
        data = {"quests": {"q1": {"id": "q1", "state": "active"}}}
        migrated = migrate_quest_state_v0(data)

        assert migrated["quests"]["q1"]["quest_id"] == "q1"

    def test_migrate_v0_status_to_state(self) -> None:
        """v0 'status' field is migrated to 'state'."""
        data = {"quests": {"q1": {"quest_id": "q1", "status": "completed"}}}
        migrated = migrate_quest_state_v0(data)

        assert migrated["quests"]["q1"]["state"] == "completed"
        assert "status" not in migrated["quests"]["q1"]


# --------------------------------------------------------------------------- #
# Schema Migration Tests
# --------------------------------------------------------------------------- #


class TestSchemaMigration:
    """Tests for save schema migration."""

    def test_schema_version_is_2(self) -> None:
        """Current schema version is 2."""
        assert SAVE_SCHEMA_VERSION == 2

    def test_migrate_v0_to_v2(self) -> None:
        """v0 save is migrated to v2."""
        data = {"flags": ["flag_a", "flag_b"]}
        migrated = migrate_save(data)

        assert migrated["save_schema_version"] == 2
        assert migrated["flags"] == {"flag_a": True, "flag_b": True}
        assert "saved_entities" in migrated
        assert "saved_quests" in migrated

    def test_migrate_v1_to_v2(self) -> None:
        """v1 save is migrated to v2."""
        data = {
            "save_schema_version": 1,
            "flags": {"test": True},
        }
        migrated = migrate_save(data)

        assert migrated["save_schema_version"] == 2
        assert migrated["saved_entities"]["schema_version"] == 1
        assert migrated["saved_entities"]["entities"] == []
        assert migrated["saved_quests"]["schema_version"] == 1
        assert migrated["saved_quests"]["quests"] == {}

    def test_v2_is_not_modified(self) -> None:
        """v2 save is not modified."""
        data = {
            "save_schema_version": 2,
            "flags": {"test": True},
            "saved_entities": {"schema_version": 1, "entities": [{"entity_id": "e1"}]},
            "saved_quests": {"schema_version": 1, "quests": {"q1": {}}},
        }
        migrated = migrate_save(dict(data))

        assert migrated["save_schema_version"] == 2
        assert migrated["saved_entities"]["entities"] == [{"entity_id": "e1"}]


class TestSchemaValidation:
    """Tests for save validation."""

    def test_validate_saved_entities_dict(self) -> None:
        """saved_entities must be a dict."""
        data = {
            "save_schema_version": 2,
            "saved_entities": "not a dict",
        }

        with pytest.raises(SaveValidationError) as exc_info:
            validate_save(data)

        assert "saved_entities" in exc_info.value.path

    def test_validate_saved_entities_list(self) -> None:
        """saved_entities.entities must be a list."""
        data = {
            "save_schema_version": 2,
            "saved_entities": {"schema_version": 1, "entities": "not a list"},
        }

        with pytest.raises(SaveValidationError) as exc_info:
            validate_save(data)

        assert "saved_entities.entities" in exc_info.value.path

    def test_validate_saved_quests_dict(self) -> None:
        """saved_quests must be a dict."""
        data = {
            "save_schema_version": 2,
            "saved_quests": [],
        }

        with pytest.raises(SaveValidationError) as exc_info:
            validate_save(data)

        assert "saved_quests" in exc_info.value.path


# --------------------------------------------------------------------------- #
# Round-Trip Determinism Tests
# --------------------------------------------------------------------------- #


class TestEntityRoundTripDeterminism:
    """Tests for entity state round-trip determinism."""

    def test_serialize_apply_preserves_position(self) -> None:
        """Position is preserved through serialize/apply cycle."""
        # Setup
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="player", center_x=123.456, center_y=789.012),
            MockSprite(mesh_name="npc", center_x=100.0, center_y=200.0),
        ]

        # Serialize
        saved = serialize_entities(controller)

        # Reset positions
        for sprite in controller.all_sprites:
            sprite.center_x = 0.0
            sprite.center_y = 0.0

        # Apply
        apply_entities(controller, saved)

        # Verify
        player = next(s for s in controller.all_sprites if s.mesh_name == "player")
        npc = next(s for s in controller.all_sprites if s.mesh_name == "npc")

        assert player.center_x == 123.456
        assert player.center_y == 789.012
        assert npc.center_x == 100.0
        assert npc.center_y == 200.0

    def test_serialize_apply_preserves_tags(self) -> None:
        """Tags are preserved through serialize/apply cycle."""
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="entity", mesh_tag="enemy"),
        ]

        saved = serialize_entities(controller)
        controller.all_sprites[0].mesh_tag = None

        apply_entities(controller, saved)

        assert controller.all_sprites[0].mesh_tag == "enemy"

    def test_serialize_apply_preserves_animation(self) -> None:
        """Animation state is preserved through serialize/apply cycle."""
        animator = MockAnimator(current_animation="attacking")
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="entity", mesh_animator=animator),
        ]

        saved = serialize_entities(controller)
        animator.current_animation = "idle"

        apply_entities(controller, saved)

        assert animator.current_animation == "attacking"

    def test_serialize_apply_preserves_behaviour_state(self) -> None:
        """Behaviour state is preserved through serialize/apply cycle."""
        behaviour = MockBehaviour({"counter": 42, "direction": "north"})
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(mesh_name="entity", mesh_behaviours_runtime=[behaviour]),
        ]

        saved = serialize_entities(controller)
        behaviour._state = {"counter": 0, "direction": "reset"}

        apply_entities(controller, saved)

        assert behaviour._state["counter"] == 42
        assert behaviour._state["direction"] == "north"

    def test_deterministic_json_output(self) -> None:
        """JSON output is deterministic across multiple serializations."""
        controller = MockSceneController()
        controller.all_sprites = [
            MockSprite(
                mesh_name="z_entity",
                center_x=1.0,
                center_y=2.0,
                mesh_tag="tag_z",
            ),
            MockSprite(
                mesh_name="a_entity",
                center_x=3.0,
                center_y=4.0,
                mesh_tag="tag_a",
            ),
        ]

        json1 = json.dumps(serialize_entities(controller), sort_keys=True)
        json2 = json.dumps(serialize_entities(controller), sort_keys=True)
        json3 = json.dumps(serialize_entities(controller), sort_keys=True)

        assert json1 == json2 == json3


class TestQuestRoundTripDeterminism:
    """Tests for quest state round-trip determinism."""

    def test_serialize_apply_preserves_state(self) -> None:
        """Quest state is preserved through serialize/apply cycle."""
        manager = MockQuestManager()
        quest = manager.register_quest({"id": "main", "state": "active"})
        quest.current_step = 5
        quest.counters = {"enemies": 10}

        saved = serialize_quests(manager)
        quest.state = "inactive"
        quest.current_step = 0
        quest.counters = {}

        apply_quests(manager, saved)

        assert quest.state == "active"
        assert quest.current_step == 5
        assert quest.counters["enemies"] == 10

    def test_deterministic_json_output(self) -> None:
        """JSON output is deterministic across multiple serializations."""
        manager = MockQuestManager()
        manager.register_quest({"id": "z_quest", "state": "active"})
        manager.register_quest({"id": "a_quest", "state": "completed"})

        json1 = json.dumps(serialize_quests(manager), sort_keys=True)
        json2 = json.dumps(serialize_quests(manager), sort_keys=True)
        json3 = json.dumps(serialize_quests(manager), sort_keys=True)

        assert json1 == json2 == json3


# --------------------------------------------------------------------------- #
# Integration Tests
# --------------------------------------------------------------------------- #


class TestFullSaveRestoreCycle:
    """Integration tests for full save/restore cycle."""

    def test_full_cycle_with_entities_and_quests(self) -> None:
        """Full save/restore preserves all state."""
        # Setup scene with entities
        scene = MockSceneController()
        behaviour = MockBehaviour({"health": 100})
        scene.all_sprites = [
            MockSprite(
                mesh_name="player",
                center_x=500.0,
                center_y=300.0,
                mesh_tag="player",
                mesh_animator=MockAnimator("walking"),
                mesh_behaviours_runtime=[behaviour],
            ),
            MockSprite(
                mesh_name="enemy",
                center_x=700.0,
                center_y=400.0,
                mesh_tag="enemy",
            ),
        ]

        # Setup quests
        quest_manager = MockQuestManager()
        quest_manager.register_quest({"id": "main_quest", "state": "active"})
        quest_manager.register_quest({"id": "side_quest", "state": "completed"})

        # Serialize
        entity_snapshot = serialize_entities(scene)
        quest_snapshot = serialize_quests(quest_manager)

        # Create save payload
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "saved_entities": {"schema_version": 1, "entities": entity_snapshot},
            "saved_quests": quest_snapshot,
        }

        # Reset state
        for sprite in scene.all_sprites:
            sprite.center_x = 0.0
            sprite.center_y = 0.0
            sprite.mesh_tag = None
        behaviour._state = {}
        for quest in quest_manager.get_all_quests():
            quest.state = "inactive"

        # Restore
        apply_entities(scene, payload["saved_entities"]["entities"])
        apply_quests(quest_manager, payload["saved_quests"])

        # Verify entities
        player = next(s for s in scene.all_sprites if s.mesh_name == "player")
        enemy = next(s for s in scene.all_sprites if s.mesh_name == "enemy")

        assert player.center_x == 500.0
        assert player.center_y == 300.0
        assert player.mesh_tag == "player"
        assert behaviour._state.get("health") == 100

        assert enemy.center_x == 700.0
        assert enemy.center_y == 400.0
        assert enemy.mesh_tag == "enemy"

        # Verify quests
        main = quest_manager.get_quest("main_quest")
        side = quest_manager.get_quest("side_quest")

        assert main is not None
        assert main.state == "active"
        assert side is not None
        assert side.state == "completed"

    def test_migration_preserves_existing_data(self) -> None:
        """Migration from v1 preserves existing data."""
        v1_payload = {
            "save_schema_version": 1,
            "flags": {"boss_defeated": True},
            "game_state": {
                "counters": {"gold": 1000},
                "flags": {"tutorial_done": True},
            },
        }

        migrated = migrate_save(v1_payload)

        assert migrated["save_schema_version"] == 2
        assert migrated["flags"]["boss_defeated"] is True
        assert migrated["game_state"]["counters"]["gold"] == 1000
        assert migrated["saved_entities"]["entities"] == []
        assert migrated["saved_quests"]["quests"] == {}
