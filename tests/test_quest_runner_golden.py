"""Golden tests for QuestRunner determinism and progression.

These tests verify:
1. Deterministic state transitions given same event stream
2. Correct emitted events order and content
3. Save/restore mid-quest continues correctly
4. Counter updates on stage completion
5. Diagnostics provide actionable information
"""
from __future__ import annotations

import copy
import pytest
from typing import Any

from engine.gameplay_event_bus import GameplayEvent
from engine.quest_runtime.runner import (
    QuestRunner,
    QuestRunnerState,
    StepCompletionDiagnostic,
)
from engine.save_runtime.quest_state import SavedQuestState


# ------------------------------------------------------------------
# Test Fixtures - Quest Definitions
# ------------------------------------------------------------------

@pytest.fixture
def simple_quest_def() -> dict[str, Any]:
    """Simple two-stage quest with event triggers."""
    return {
        "schema_version": 1,
        "quests": [
            {
                "id": "simple_quest",
                "title": "Simple Quest",
                "description": "A simple test quest",
                "stages": [
                    {
                        "id": "stage_1",
                        "title": "First Stage",
                        "text": "Complete the first objective",
                        "complete_on": {
                            "type": "objective_complete",
                            "payload": {"objective_id": "obj_1"},
                        },
                    },
                    {
                        "id": "stage_2",
                        "title": "Second Stage",
                        "text": "Complete the second objective",
                        "complete_on": {
                            "type": "objective_complete",
                            "payload": {"objective_id": "obj_2"},
                        },
                    },
                ],
                "reward": {
                    "set_flags": {"simple_quest_complete": True},
                    "inc_counters": {"quests_done": 1},
                },
            }
        ],
    }


@pytest.fixture
def gated_quest_def() -> dict[str, Any]:
    """Quest with start triggers on stages."""
    return {
        "schema_version": 1,
        "quests": [
            {
                "id": "gated_quest",
                "title": "Gated Quest",
                "stages": [
                    {
                        "id": "intro",
                        "title": "Introduction",
                        "start_on_event": {
                            "type": "dialogue_choice",
                            "payload": {"choice_id": "accept_quest"},
                        },
                        "complete_on": {
                            "type": "entered_zone",
                            "payload": {"zone": "quest_area"},
                        },
                    },
                    {
                        "id": "finale",
                        "title": "Finale",
                        "start_on_event": {
                            "type": "item_collected",
                            "payload": {"item": "quest_key"},
                        },
                        "complete_on": {
                            "type": "dialogue_choice",
                            "payload": {"choice_id": "complete_quest"},
                        },
                    },
                ],
            }
        ],
    }


@pytest.fixture
def counter_quest_def() -> dict[str, Any]:
    """Quest that uses payload_field matching."""
    return {
        "schema_version": 1,
        "quests": [
            {
                "id": "counter_quest",
                "title": "Kill Counter Quest",
                "stages": [
                    {
                        "id": "kill_enemies",
                        "title": "Kill Enemies",
                        "complete_on": {
                            "type": "enemy_killed",
                            "payload_field": "enemy_type",
                            "payload_value": "goblin",
                        },
                    },
                ],
            }
        ],
    }


@pytest.fixture
def emit_events_quest_def() -> dict[str, Any]:
    """Quest that emits custom events on completion."""
    return {
        "schema_version": 1,
        "quests": [
            {
                "id": "emit_quest",
                "title": "Emit Events Quest",
                "stages": [
                    {
                        "id": "trigger_stage",
                        "title": "Trigger",
                        "complete_on": {"type": "trigger_complete"},
                        "emit_events_on_complete": [
                            "custom_event_1",
                            {"type": "custom_event_2", "payload": {"key": "value"}},
                        ],
                    },
                ],
            }
        ],
    }


# ------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------

def make_event(event_type: str, sequence: int = 0, **payload: Any) -> GameplayEvent:
    """Create a GameplayEvent for testing."""
    return GameplayEvent(
        event_type=event_type,
        payload=payload,
        sequence=sequence,
        source_entity="",
        source_behaviour="test",
    )


# ------------------------------------------------------------------
# Golden Tests - Deterministic Progression
# ------------------------------------------------------------------

class TestQuestRunnerGoldenProgression:
    """Golden tests for deterministic quest progression."""

    def test_simple_quest_two_stage_progression(self, simple_quest_def):
        """Simple quest progresses through two stages deterministically."""
        runner = QuestRunner()
        errors = runner.load_definitions(simple_quest_def)
        assert errors == []
        
        # Start quest
        assert runner.start_quest("simple_quest")
        
        state = runner.get_quest_state("simple_quest")
        assert state is not None
        assert state.status == "active"
        assert state.current_stage == "stage_1"
        
        # Event for stage 1 completion
        events = [make_event("objective_complete", 1, objective_id="obj_1")]
        emitted = runner.process_events(events)
        
        # Should emit stage_completed then stage_started
        assert len(emitted) >= 2
        assert emitted[0].event_type == "quest_stage_completed"
        assert emitted[0].payload["stage_id"] == "stage_1"
        assert emitted[1].event_type == "quest_stage_started"
        assert emitted[1].payload["stage_id"] == "stage_2"
        
        state = runner.get_quest_state("simple_quest")
        assert state is not None
        assert state.current_stage == "stage_2"
        assert "stage_1" in state.completed_stages
        
        # Event for stage 2 completion
        events = [make_event("objective_complete", 2, objective_id="obj_2")]
        emitted = runner.process_events(events)
        
        # Should emit stage_completed then quest_completed
        assert len(emitted) >= 2
        assert emitted[0].event_type == "quest_stage_completed"
        assert emitted[0].payload["stage_id"] == "stage_2"
        assert emitted[1].event_type == "quest_completed"
        assert emitted[1].payload["quest_id"] == "simple_quest"
        
        state = runner.get_quest_state("simple_quest")
        assert state is not None
        assert state.status == "completed"

    def test_gated_quest_requires_start_trigger(self, gated_quest_def):
        """Gated quest stage requires start trigger before completion."""
        runner = QuestRunner()
        runner.load_definitions(gated_quest_def)
        runner.start_quest("gated_quest")
        
        state = runner.get_quest_state("gated_quest")
        assert state is not None
        # First stage has start trigger, so awaiting
        assert state.awaiting_stage == "intro"
        assert state.current_stage is None
        
        # Wrong event doesn't start stage
        events = [make_event("wrong_event", 1)]
        emitted = runner.process_events(events)
        assert emitted == []
        
        # Correct start event
        events = [make_event("dialogue_choice", 2, choice_id="accept_quest")]
        emitted = runner.process_events(events)
        
        assert len(emitted) == 1
        assert emitted[0].event_type == "quest_stage_started"
        
        state = runner.get_quest_state("gated_quest")
        assert state is not None
        assert state.current_stage == "intro"
        assert state.awaiting_stage is None

    def test_same_events_produce_same_state(self, simple_quest_def):
        """Identical event streams produce identical state transitions."""
        events = [
            make_event("objective_complete", 1, objective_id="obj_1"),
            make_event("objective_complete", 2, objective_id="obj_2"),
        ]
        
        # Run 1
        runner1 = QuestRunner(emit_sequence_start=1000)
        runner1.load_definitions(simple_quest_def)
        runner1.start_quest("simple_quest")
        emitted1 = runner1.process_events(events)
        state1 = runner1.get_state("simple_quest")
        
        # Run 2 (fresh runner)
        runner2 = QuestRunner(emit_sequence_start=1000)
        runner2.load_definitions(simple_quest_def)
        runner2.start_quest("simple_quest")
        emitted2 = runner2.process_events(events)
        state2 = runner2.get_state("simple_quest")
        
        # Same emitted events
        assert len(emitted1) == len(emitted2)
        for e1, e2 in zip(emitted1, emitted2):
            assert e1.event_type == e2.event_type
            assert e1.payload == e2.payload
            assert e1.sequence == e2.sequence
        
        # Same final state
        assert state1 == state2

    def test_payload_field_matching(self, counter_quest_def):
        """Payload field/value matching works correctly."""
        runner = QuestRunner()
        runner.load_definitions(counter_quest_def)
        runner.start_quest("counter_quest")
        
        # Wrong payload value
        events = [make_event("enemy_killed", 1, enemy_type="orc")]
        emitted = runner.process_events(events)
        assert emitted == []
        
        state = runner.get_quest_state("counter_quest")
        assert state is not None
        assert state.current_stage == "kill_enemies"
        
        # Correct payload value
        events = [make_event("enemy_killed", 2, enemy_type="goblin")]
        emitted = runner.process_events(events)
        
        assert len(emitted) >= 1
        assert emitted[0].event_type == "quest_stage_completed"

    def test_emit_events_on_complete(self, emit_events_quest_def):
        """Custom events emitted on stage completion."""
        runner = QuestRunner()
        runner.load_definitions(emit_events_quest_def)
        runner.start_quest("emit_quest")
        
        events = [make_event("trigger_complete", 1)]
        emitted = runner.process_events(events)
        
        # Should emit: stage_completed, custom_event_1, custom_event_2, quest_completed
        event_types = [e.event_type for e in emitted]
        assert "quest_stage_completed" in event_types
        assert "custom_event_1" in event_types
        assert "custom_event_2" in event_types
        assert "quest_completed" in event_types
        
        # Check custom_event_2 payload
        custom_2 = next(e for e in emitted if e.event_type == "custom_event_2")
        assert custom_2.payload.get("key") == "value"


# ------------------------------------------------------------------
# Save/Restore Tests
# ------------------------------------------------------------------

class TestQuestRunnerSaveRestore:
    """Tests for save/restore functionality."""

    def test_save_restore_mid_quest(self, simple_quest_def):
        """Quest state can be saved and restored mid-quest."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Complete first stage
        events = [make_event("objective_complete", 1, objective_id="obj_1")]
        runner.process_events(events)
        
        # Save state
        saved = runner.get_state("simple_quest")
        
        # Create new runner and restore
        runner2 = QuestRunner()
        runner2.load_definitions(simple_quest_def)
        runner2.apply_state(saved)
        
        state = runner2.get_quest_state("simple_quest")
        assert state is not None
        assert state.status == "active"
        assert state.current_stage == "stage_2"
        assert "stage_1" in state.completed_stages
        
        # Continue from restored state
        events = [make_event("objective_complete", 2, objective_id="obj_2")]
        emitted = runner2.process_events(events)
        
        assert any(e.event_type == "quest_completed" for e in emitted)

    def test_save_restore_preserves_counters(self, simple_quest_def):
        """Quest counters are preserved through save/restore."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Manually set counter
        state = runner.get_quest_state("simple_quest")
        assert state is not None
        state.counters["test_counter"] = 42
        
        # Save and restore
        saved = runner.get_state("simple_quest")
        
        runner2 = QuestRunner()
        runner2.load_definitions(simple_quest_def)
        runner2.apply_state(saved)
        
        state2 = runner2.get_quest_state("simple_quest")
        assert state2 is not None
        assert state2.counters.get("test_counter") == 42

    def test_state_roundtrip_with_saved_quest_state(self, simple_quest_def):
        """State roundtrips correctly through SavedQuestState."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Complete first stage
        events = [make_event("objective_complete", 1, objective_id="obj_1")]
        runner.process_events(events)
        
        # Get internal state
        state = runner.get_quest_state("simple_quest")
        assert state is not None
        
        # Convert to SavedQuestState and back
        saved = state.to_saved_state()
        saved_dict = saved.to_dict()
        
        # Deserialize
        restored_saved = SavedQuestState.from_dict(saved_dict)
        restored_state = QuestRunnerState.from_saved_state(restored_saved)
        
        assert restored_state.quest_id == state.quest_id
        assert restored_state.status == state.status
        assert restored_state.completed_stages == state.completed_stages


# ------------------------------------------------------------------
# Diagnostics Tests
# ------------------------------------------------------------------

class TestQuestRunnerDiagnostics:
    """Tests for diagnostic information."""

    def test_diagnostics_recorded_on_mismatch(self, simple_quest_def):
        """Diagnostics are recorded when events don't match."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Send non-matching event
        events = [make_event("wrong_event", 1, some_key="value")]
        runner.process_events(events)
        
        diagnostics = runner.get_diagnostics("simple_quest")
        assert len(diagnostics) > 0
        
        # Check diagnostic content
        diag = diagnostics[-1]
        assert diag.quest_id == "simple_quest"
        assert diag.matched is False
        assert "mismatch" in diag.reason.lower() or "expected" in diag.reason.lower()

    def test_diagnostics_recorded_on_match(self, simple_quest_def):
        """Diagnostics are recorded when events match."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Send matching event
        events = [make_event("objective_complete", 1, objective_id="obj_1")]
        runner.process_events(events)
        
        diagnostics = runner.get_diagnostics("simple_quest")
        
        # Should have at least one match
        matches = [d for d in diagnostics if d.matched]
        assert len(matches) > 0

    def test_get_step_completion_reason(self, simple_quest_def):
        """Can get reason why step did/didn't complete."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Send non-matching event
        events = [make_event("wrong_event", 1)]
        runner.process_events(events)
        
        reason = runner.get_step_completion_reason("simple_quest", "stage_1")
        assert reason is not None
        assert len(reason) > 0


# ------------------------------------------------------------------
# Edge Cases
# ------------------------------------------------------------------

class TestQuestRunnerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_start_nonexistent_quest(self):
        """Starting nonexistent quest returns False."""
        runner = QuestRunner()
        assert runner.start_quest("nonexistent") is False

    def test_start_already_completed_quest(self, simple_quest_def):
        """Cannot restart completed quest."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Complete the quest
        events = [
            make_event("objective_complete", 1, objective_id="obj_1"),
            make_event("objective_complete", 2, objective_id="obj_2"),
        ]
        runner.process_events(events)
        
        assert runner.is_quest_completed("simple_quest")
        assert runner.start_quest("simple_quest") is False

    def test_process_events_empty_list(self, simple_quest_def):
        """Processing empty event list returns empty."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        emitted = runner.process_events([])
        assert emitted == []

    def test_load_invalid_json_file(self, tmp_path):
        """Loading invalid JSON file returns error."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json")
        
        runner = QuestRunner()
        errors = runner.load_definitions(bad_file)
        
        assert len(errors) == 1
        assert errors[0].code == "file.invalid_json"

    def test_load_missing_file(self, tmp_path):
        """Loading missing file returns error."""
        missing = tmp_path / "missing.json"
        
        runner = QuestRunner()
        errors = runner.load_definitions(missing)
        
        assert len(errors) == 1
        assert errors[0].code == "file.not_found"

    def test_events_processed_in_sequence_order(self, simple_quest_def):
        """Events are processed in sequence order, not list order."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        # Events out of sequence order in list
        events = [
            make_event("objective_complete", 2, objective_id="obj_2"),  # Higher sequence
            make_event("objective_complete", 1, objective_id="obj_1"),  # Lower sequence
        ]
        
        # Process all at once
        emitted = runner.process_events(events)
        
        # Stage 1 should complete first (lower sequence processed first)
        completed_stages = [
            e.payload["stage_id"] 
            for e in emitted 
            if e.event_type == "quest_stage_completed"
        ]
        assert completed_stages == ["stage_1", "stage_2"]


# ------------------------------------------------------------------
# Integration with Existing Quest Infrastructure
# ------------------------------------------------------------------

class TestQuestRunnerIntegration:
    """Integration tests with existing quest infrastructure."""

    def test_emitted_events_have_correct_structure(self, simple_quest_def):
        """Emitted events match expected GameplayEvent structure."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        events = [make_event("objective_complete", 1, objective_id="obj_1")]
        emitted = runner.process_events(events)
        
        for event in emitted:
            assert isinstance(event, GameplayEvent)
            assert isinstance(event.event_type, str)
            assert isinstance(event.payload, dict)
            assert isinstance(event.sequence, int)
            assert event.source_behaviour == "QuestRunner"

    def test_quest_completed_event_includes_reward(self, simple_quest_def):
        """Quest completed event includes reward payload."""
        runner = QuestRunner()
        runner.load_definitions(simple_quest_def)
        runner.start_quest("simple_quest")
        
        events = [
            make_event("objective_complete", 1, objective_id="obj_1"),
            make_event("objective_complete", 2, objective_id="obj_2"),
        ]
        emitted = runner.process_events(events)
        
        completed = next(e for e in emitted if e.event_type == "quest_completed")
        assert "reward" in completed.payload
        assert completed.payload["reward"]["set_flags"]["simple_quest_complete"] is True


class TestMultipleQuestsInteraction:
    """Tests for multiple quests running simultaneously."""

    def test_independent_quests_progress_independently(self):
        """Two independent quests progress without interference."""
        data = {
            "schema_version": 1,
            "quests": [
                {
                    "id": "quest_a",
                    "title": "Quest A",
                    "stages": [
                        {"id": "a1", "title": "A1", "complete_on": {"type": "event_a"}},
                    ],
                },
                {
                    "id": "quest_b",
                    "title": "Quest B",
                    "stages": [
                        {"id": "b1", "title": "B1", "complete_on": {"type": "event_b"}},
                    ],
                },
            ],
        }
        
        runner = QuestRunner()
        runner.load_definitions(data)
        runner.start_quest("quest_a")
        runner.start_quest("quest_b")
        
        # Complete quest_a only
        events = [make_event("event_a", 1)]
        runner.process_events(events)
        
        assert runner.is_quest_completed("quest_a")
        assert not runner.is_quest_completed("quest_b")
        assert runner.is_quest_active("quest_b")

    def test_event_affects_multiple_quests(self):
        """Single event can trigger multiple quest progressions."""
        data = {
            "schema_version": 1,
            "quests": [
                {
                    "id": "quest_a",
                    "title": "Quest A",
                    "stages": [
                        {"id": "a1", "title": "A1", "complete_on": {"type": "shared_event"}},
                    ],
                },
                {
                    "id": "quest_b",
                    "title": "Quest B",
                    "stages": [
                        {"id": "b1", "title": "B1", "complete_on": {"type": "shared_event"}},
                    ],
                },
            ],
        }
        
        runner = QuestRunner()
        runner.load_definitions(data)
        runner.start_quest("quest_a")
        runner.start_quest("quest_b")
        
        # Single event completes both
        events = [make_event("shared_event", 1)]
        emitted = runner.process_events(events)
        
        assert runner.is_quest_completed("quest_a")
        assert runner.is_quest_completed("quest_b")
        
        # Should have completion events for both
        completed_quests = [
            e.payload["quest_id"] 
            for e in emitted 
            if e.event_type == "quest_completed"
        ]
        assert "quest_a" in completed_quests
        assert "quest_b" in completed_quests

    @pytest.mark.fast
    def test_shared_event_emits_in_sorted_quest_id_order(self):
        """Quest processing order is sorted by quest id, not definition order."""
        data = {
            "schema_version": 1,
            "quests": [
                {
                    "id": "quest_b",
                    "title": "Quest B",
                    "stages": [
                        {"id": "b1", "title": "B1", "complete_on": {"type": "shared_event"}},
                    ],
                },
                {
                    "id": "quest_a",
                    "title": "Quest A",
                    "stages": [
                        {"id": "a1", "title": "A1", "complete_on": {"type": "shared_event"}},
                    ],
                },
            ],
        }

        runner = QuestRunner(emit_sequence_start=1000)
        runner.load_definitions(data)
        runner.start_quest("quest_a")
        runner.start_quest("quest_b")

        emitted = runner.process_events([make_event("shared_event", 1)])

        assert [(event.event_type, event.payload, event.sequence) for event in emitted] == [
            (
                "quest_stage_completed",
                {"quest_id": "quest_a", "stage_id": "a1", "quest_title": "Quest A", "stage_title": "A1", "text": "A1"},
                1000,
            ),
            ("quest_completed", {"quest_id": "quest_a", "quest_title": "Quest A", "reward": {"set_flags": {}, "inc_counters": {}}}, 1001),
            (
                "quest_stage_completed",
                {"quest_id": "quest_b", "stage_id": "b1", "quest_title": "Quest B", "stage_title": "B1", "text": "B1"},
                1002,
            ),
            ("quest_completed", {"quest_id": "quest_b", "quest_title": "Quest B", "reward": {"set_flags": {}, "inc_counters": {}}}, 1003),
        ]
