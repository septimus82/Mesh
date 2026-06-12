"""
Determinism tests for replay-grade world state verification.

These tests verify that:
1. World digest computation is stable and deterministic
2. Same initial state + same inputs = same digest sequence
3. DigestTracker correctly records and compares runs
4. Entity and quest state normalization is consistent
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.save_runtime.digest import (
    DigestTracker,
    compute_entity_digest,
    compute_quest_digest,
    compute_world_digest,
    normalize_entity_state,
    normalize_quest_state,
)

# ============================================================================
# Mock objects for testing
# ============================================================================


@dataclass
class MockSprite:
    """Mock sprite/entity for testing."""

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
    """Mock animator for testing."""

    current_animation: str = "idle"


class MockSaveableBehaviour:
    """Mock behaviour with saveable state."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self._state = state or {}

    def saveable_state(self) -> dict[str, Any]:
        return dict(self._state)

    def restore_state(self, state: dict[str, Any]) -> None:
        self._state = dict(state)


class MockSceneController:
    """Mock scene controller with all_sprites."""

    def __init__(self) -> None:
        self.all_sprites: list[MockSprite] = []


class MockQuestManager:
    """Mock quest manager."""

    def __init__(self) -> None:
        self._quests: list[Any] = []

    def get_all_quests(self) -> list[Any]:
        return self._quests


# ============================================================================
# Entity normalization tests
# ============================================================================


class TestEntityNormalization:
    """Tests for normalize_entity_state()."""

    def test_basic_normalization(self) -> None:
        """Basic entity normalizes correctly."""
        entity = {
            "entity_id": "player",
            "x": 100.0,
            "y": 200.0,
        }
        result = normalize_entity_state(entity)
        assert result["entity_id"] == "player"
        assert result["x"] == 100.0
        assert result["y"] == 200.0

    def test_float_precision_normalization(self) -> None:
        """Float precision is normalized."""
        entity = {
            "entity_id": "test",
            "x": 100.123456789,
            "y": 200.987654321,
        }
        result = normalize_entity_state(entity)
        # Should be rounded to 6 decimal places
        assert result["x"] == 100.123457
        assert result["y"] == 200.987654

    def test_tags_sorted(self) -> None:
        """Tags are sorted for determinism."""
        entity = {
            "entity_id": "test",
            "x": 0.0,
            "y": 0.0,
            "tags": ["zzz", "aaa", "mmm"],
        }
        result = normalize_entity_state(entity)
        assert result["tags"] == ["aaa", "mmm", "zzz"]

    def test_behaviour_state_sorted(self) -> None:
        """Behaviour state dict keys are sorted."""
        entity = {
            "entity_id": "test",
            "x": 0.0,
            "y": 0.0,
            "behaviour_state": {
                "Health": {"hp": 100, "max_hp": 100},
                "Armor": {"value": 50},
            },
        }
        result = normalize_entity_state(entity)
        # Keys should be sorted
        keys = list(result["behaviour_state"].keys())
        assert keys == sorted(keys)

    def test_missing_optional_fields(self) -> None:
        """Missing optional fields don't appear in output."""
        entity = {
            "entity_id": "test",
            "x": 0.0,
            "y": 0.0,
        }
        result = normalize_entity_state(entity)
        assert "tags" not in result
        assert "prefab_id" not in result
        assert "behaviour_state" not in result


# ============================================================================
# Quest normalization tests
# ============================================================================


class TestQuestNormalization:
    """Tests for normalize_quest_state()."""

    def test_basic_normalization(self) -> None:
        """Basic quest normalizes correctly."""
        quest = {
            "quest_id": "main_quest",
            "state": "active",
            "current_step": 2,
        }
        result = normalize_quest_state(quest)
        assert result["quest_id"] == "main_quest"
        assert result["state"] == "active"
        assert result["current_step"] == 2

    def test_counters_sorted(self) -> None:
        """Quest counters are sorted by key."""
        quest = {
            "quest_id": "test",
            "state": "active",
            "current_step": 0,
            "counters": {"z_counter": 3, "a_counter": 1, "m_counter": 2},
        }
        result = normalize_quest_state(quest)
        keys = list(result["counters"].keys())
        assert keys == sorted(keys)

    def test_timestamps_excluded(self) -> None:
        """Timestamps are excluded from normalized output."""
        quest = {
            "quest_id": "test",
            "state": "completed",
            "current_step": 5,
            "timestamp_started": "2024-01-01T00:00:00",
            "timestamp_completed": "2024-01-02T00:00:00",
        }
        result = normalize_quest_state(quest)
        assert "timestamp_started" not in result
        assert "timestamp_completed" not in result


# ============================================================================
# Digest computation tests
# ============================================================================


class TestDigestComputation:
    """Tests for digest computation functions."""

    def test_empty_entities_digest(self) -> None:
        """Empty entity list produces consistent digest."""
        digest1 = compute_entity_digest([])
        digest2 = compute_entity_digest([])
        assert digest1 == digest2
        assert len(digest1) == 64  # SHA-256 hex

    def test_empty_quests_digest(self) -> None:
        """Empty quest list produces consistent digest."""
        digest1 = compute_quest_digest([])
        digest2 = compute_quest_digest([])
        assert digest1 == digest2

    def test_entity_order_independence(self) -> None:
        """Entity order doesn't affect digest."""
        entities_a = [
            {"entity_id": "a", "x": 0.0, "y": 0.0},
            {"entity_id": "b", "x": 1.0, "y": 1.0},
        ]
        entities_b = [
            {"entity_id": "b", "x": 1.0, "y": 1.0},
            {"entity_id": "a", "x": 0.0, "y": 0.0},
        ]
        assert compute_entity_digest(entities_a) == compute_entity_digest(entities_b)

    def test_quest_order_independence(self) -> None:
        """Quest order doesn't affect digest."""
        quests_a = [
            {"quest_id": "q1", "state": "active", "current_step": 0},
            {"quest_id": "q2", "state": "inactive", "current_step": 0},
        ]
        quests_b = [
            {"quest_id": "q2", "state": "inactive", "current_step": 0},
            {"quest_id": "q1", "state": "active", "current_step": 0},
        ]
        assert compute_quest_digest(quests_a) == compute_quest_digest(quests_b)

    def test_different_entities_different_digest(self) -> None:
        """Different entity states produce different digests."""
        entities_a = [{"entity_id": "a", "x": 0.0, "y": 0.0}]
        entities_b = [{"entity_id": "a", "x": 1.0, "y": 0.0}]
        assert compute_entity_digest(entities_a) != compute_entity_digest(entities_b)

    def test_world_digest_with_frame(self) -> None:
        """World digest includes frame number."""
        entities = [{"entity_id": "a", "x": 0.0, "y": 0.0}]
        digest_f0 = compute_world_digest(entities, frame=0)
        digest_f1 = compute_world_digest(entities, frame=1)
        assert digest_f0 != digest_f1

    def test_world_digest_without_frame(self) -> None:
        """World digest can exclude frame number."""
        entities = [{"entity_id": "a", "x": 0.0, "y": 0.0}]
        digest_f0 = compute_world_digest(entities, frame=0, include_frame=False)
        digest_f1 = compute_world_digest(entities, frame=1, include_frame=False)
        assert digest_f0 == digest_f1


# ============================================================================
# DigestTracker tests
# ============================================================================


class TestDigestTracker:
    """Tests for DigestTracker class."""

    def test_record_and_get(self) -> None:
        """Record and retrieve digests."""
        tracker = DigestTracker(seed=12345)
        tracker.record(0, "digest_0")
        tracker.record(1, "digest_1")
        tracker.record(2, "digest_2")

        assert tracker.get(0) == "digest_0"
        assert tracker.get(1) == "digest_1"
        assert tracker.get(2) == "digest_2"
        assert tracker.get(99) is None

    def test_compare_identical(self) -> None:
        """Identical trackers have no mismatches."""
        tracker1 = DigestTracker(seed=12345)
        tracker2 = DigestTracker(seed=12345)

        for i in range(10):
            digest = f"digest_{i}"
            tracker1.record(i, digest)
            tracker2.record(i, digest)

        mismatches = tracker1.compare(tracker2)
        assert mismatches == []

    def test_compare_different(self) -> None:
        """Different trackers report mismatches."""
        tracker1 = DigestTracker()
        tracker2 = DigestTracker()

        tracker1.record(0, "same")
        tracker2.record(0, "same")

        tracker1.record(1, "different_a")
        tracker2.record(1, "different_b")

        tracker1.record(2, "same_again")
        tracker2.record(2, "same_again")

        mismatches = tracker1.compare(tracker2)
        assert len(mismatches) == 1
        assert mismatches[0] == (1, "different_a", "different_b")

    def test_compare_missing_frames(self) -> None:
        """Missing frames are reported as mismatches."""
        tracker1 = DigestTracker()
        tracker2 = DigestTracker()

        tracker1.record(0, "digest_0")
        tracker1.record(1, "digest_1")
        # tracker1 doesn't have frame 2

        tracker2.record(0, "digest_0")
        # tracker2 doesn't have frame 1
        tracker2.record(2, "digest_2")

        mismatches = tracker1.compare(tracker2)
        assert len(mismatches) == 2  # frame 1 and frame 2

    def test_serialization_roundtrip(self) -> None:
        """Tracker survives serialization round-trip."""
        tracker = DigestTracker(seed=42)
        tracker.record(0, "a")
        tracker.record(5, "b")
        tracker.record(10, "c")

        data = tracker.to_dict()
        restored = DigestTracker.from_dict(data)

        assert restored.seed == tracker.seed
        assert restored.digests == tracker.digests


# ============================================================================
# Determinism simulation tests
# ============================================================================


class TestDeterminismSimulation:
    """Tests simulating deterministic gameplay runs."""

    def test_identical_runs_same_digest(self) -> None:
        """Two identical simulation runs produce same digests."""

        def simulate_run(seed: int) -> DigestTracker:
            """Simulate a deterministic run."""
            tracker = DigestTracker(seed=seed)

            # Simulate entities with deterministic movement
            entities: list[dict[str, Any]] = [
                {"entity_id": "player", "x": 0.0, "y": 0.0},
                {"entity_id": "enemy", "x": 100.0, "y": 100.0},
            ]

            quests: list[dict[str, Any]] = [
                {"quest_id": "main", "state": "active", "current_step": 0},
            ]

            for frame in range(10):
                # Deterministic update (fixed dt, no randomness)
                dt = 1.0 / 60.0
                for entity in entities:
                    entity["x"] = entity["x"] + 10.0 * dt
                    entity["y"] = entity["y"] + 5.0 * dt

                digest = compute_world_digest(entities, quests, frame=frame)
                tracker.record(frame, digest)

            return tracker

        run1 = simulate_run(seed=12345)
        run2 = simulate_run(seed=12345)

        mismatches = run1.compare(run2)
        assert mismatches == [], f"Expected no mismatches, got: {mismatches}"

    def test_different_seeds_different_path(self) -> None:
        """Runs with different seeds may diverge (if seed affects behavior)."""
        # This test documents that seed can be used to distinguish runs

        tracker1 = DigestTracker(seed=111)
        tracker2 = DigestTracker(seed=222)

        # Same state, but different seeds
        entities = [{"entity_id": "a", "x": 0.0, "y": 0.0}]
        digest = compute_world_digest(entities, frame=0)

        tracker1.record(0, digest)
        tracker2.record(0, digest)

        # Digests are same (state is same), but seeds differ
        assert tracker1.seed != tracker2.seed
        assert tracker1.digests == tracker2.digests

    def test_float_precision_determinism(self) -> None:
        """Float precision issues don't cause false divergence."""
        # Simulate potential float precision issues
        entities1 = [{"entity_id": "a", "x": 0.1 + 0.2, "y": 0.0}]
        entities2 = [{"entity_id": "a", "x": 0.3, "y": 0.0}]

        # 0.1 + 0.2 != 0.3 in float, but should normalize to same
        digest1 = compute_entity_digest(entities1)
        digest2 = compute_entity_digest(entities2)

        assert digest1 == digest2

    def test_behaviour_state_determinism(self) -> None:
        """Behaviour state changes are reflected in digest."""
        entities_before = [
            {
                "entity_id": "enemy",
                "x": 0.0,
                "y": 0.0,
                "behaviour_state": {"Health": {"hp": 100}},
            }
        ]
        entities_after = [
            {
                "entity_id": "enemy",
                "x": 0.0,
                "y": 0.0,
                "behaviour_state": {"Health": {"hp": 50}},
            }
        ]

        digest_before = compute_entity_digest(entities_before)
        digest_after = compute_entity_digest(entities_after)

        assert digest_before != digest_after


# ============================================================================
# Replay verification tests
# ============================================================================


class TestReplayVerification:
    """Tests for replay verification scenario."""

    def test_replay_matches_recording(self) -> None:
        """Recorded digests match replay digests."""
        # Record original run
        recording = DigestTracker(seed=999)

        entities = [{"entity_id": "hero", "x": 0.0, "y": 0.0}]
        quests = [{"quest_id": "tutorial", "state": "active", "current_step": 0}]

        for frame in range(20):
            # Simulate fixed-timestep update
            entities[0]["x"] += 1.0
            if frame == 10:
                quests[0]["current_step"] = 1
            if frame == 15:
                quests[0]["state"] = "completed"

            digest = compute_world_digest(entities, quests, frame=frame)
            recording.record(frame, digest)

        # Replay (same logic, same inputs)
        replay = DigestTracker(seed=999)

        entities = [{"entity_id": "hero", "x": 0.0, "y": 0.0}]
        quests = [{"quest_id": "tutorial", "state": "active", "current_step": 0}]

        for frame in range(20):
            entities[0]["x"] += 1.0
            if frame == 10:
                quests[0]["current_step"] = 1
            if frame == 15:
                quests[0]["state"] = "completed"

            digest = compute_world_digest(entities, quests, frame=frame)
            replay.record(frame, digest)

        # Verify match
        mismatches = recording.compare(replay)
        assert mismatches == []

    def test_replay_detects_divergence(self) -> None:
        """Replay verification catches state divergence."""
        recording = DigestTracker()
        replay = DigestTracker()

        # Recording: entity moves right
        for frame in range(10):
            entities = [{"entity_id": "a", "x": float(frame), "y": 0.0}]
            recording.record(frame, compute_world_digest(entities, frame=frame))

        # Replay: entity moves left (bug!)
        for frame in range(10):
            entities = [{"entity_id": "a", "x": float(-frame), "y": 0.0}]
            replay.record(frame, compute_world_digest(entities, frame=frame))

        # Should detect divergence at frame 1
        mismatches = recording.compare(replay)
        assert len(mismatches) > 0
        # Frame 0 might match (both at x=0), divergence starts at frame 1
        diverge_frame = mismatches[0][0]
        assert diverge_frame <= 1
