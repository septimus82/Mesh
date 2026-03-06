"""Integration tests for QuestRunner with TriggerVolume, ActionListRunner, and QuestHook.

Tests the complete flow:
1. TriggerVolume emits event when player enters
2. ActionListRunner can emit quest-related events  
3. QuestRunner processes events and advances quest state
4. QuestRunner emits progress events that QuestHook can receive
"""
from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import MagicMock

from engine.gameplay_event_bus import GameplayEvent, GameplayEventBus
from engine.quest_runtime.runner import QuestRunner


@pytest.fixture
def mock_window():
    """Create a mock window with gameplay event bus."""
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    window.entities = []
    return window


@pytest.fixture
def integration_quest_def() -> dict[str, Any]:
    """Quest definition for integration testing.
    
    Uses 'on_enter' event with 'zone' field matching the TriggerVolume's 
    mesh_id to detect when the player enters specific trigger volumes.
    """
    return {
        "schema_version": 1,
        "quests": [
            {
                "id": "exploration_quest",
                "title": "Explore the Area",
                "description": "Visit all landmarks",
                "stages": [
                    {
                        "id": "visit_landmark_1",
                        "title": "Visit First Landmark",
                        "text": "Find the ancient ruins",
                        "complete_on": {
                            "type": "on_enter",
                            "payload_field": "zone",
                            "payload_value": "landmark_trigger_1",
                        },
                    },
                    {
                        "id": "visit_landmark_2",
                        "title": "Visit Second Landmark",
                        "text": "Find the hidden cave",
                        "complete_on": {
                            "type": "on_enter",
                            "payload_field": "zone",
                            "payload_value": "landmark_trigger_2",
                        },
                    },
                ],
                "reward": {
                    "set_flags": {"exploration_complete": True},
                    "inc_counters": {"landmarks_found": 2},
                },
            }
        ],
    }


class TestQuestRunnerTriggerVolumeIntegration:
    """Integration tests for QuestRunner with TriggerVolume events."""

    def test_trigger_volume_event_advances_quest(
        self, mock_window, integration_quest_def
    ):
        """TriggerVolume enter event advances quest through QuestRunner."""
        # Set up QuestRunner
        runner = QuestRunner()
        runner.load_definitions(integration_quest_def)
        runner.start_quest("exploration_quest")
        
        # Verify initial state
        state = runner.get_quest_state("exploration_quest")
        assert state is not None
        assert state.status == "active"
        assert state.current_stage == "visit_landmark_1"
        
        # Simulate TriggerVolume emitting an enter event
        # TriggerVolume emits with zone=mesh_id of the trigger entity
        mock_window.gameplay_event_bus.emit(
            "on_enter",
            zone="landmark_trigger_1",
            zone_name="Landmark Trigger 1",
            entity="player_001",
            entity_name="Player",
            source_entity="landmark_trigger_1",
            source_behaviour="TriggerVolume",
        )
        
        # Drain events and process through QuestRunner
        events = mock_window.gameplay_event_bus.drain()
        emitted = runner.process_events(events)
        
        # Should have completed stage 1 and started stage 2
        state = runner.get_quest_state("exploration_quest")
        assert state is not None
        assert state.current_stage == "visit_landmark_2"
        assert "visit_landmark_1" in state.completed_stages
        
        # Should have emitted stage completed and started events
        event_types = [e.event_type for e in emitted]
        assert "quest_stage_completed" in event_types
        assert "quest_stage_started" in event_types

    def test_quest_completes_after_all_stages(
        self, mock_window, integration_quest_def
    ):
        """Quest completes after all stages completed."""
        runner = QuestRunner()
        runner.load_definitions(integration_quest_def)
        runner.start_quest("exploration_quest")
        
        # Complete stage 1
        mock_window.gameplay_event_bus.emit("on_enter", zone="landmark_trigger_1")
        runner.process_events(mock_window.gameplay_event_bus.drain())
        
        # Complete stage 2
        mock_window.gameplay_event_bus.emit("on_enter", zone="landmark_trigger_2")
        emitted = runner.process_events(mock_window.gameplay_event_bus.drain())
        
        # Quest should be completed
        state = runner.get_quest_state("exploration_quest")
        assert state is not None
        assert state.status == "completed"
        
        # Should have quest_completed event
        completed_events = [e for e in emitted if e.event_type == "quest_completed"]
        assert len(completed_events) == 1
        assert completed_events[0].payload["quest_id"] == "exploration_quest"

    def test_emitted_events_can_feed_back_to_bus(
        self, mock_window, integration_quest_def
    ):
        """QuestRunner emitted events can be re-emitted to event bus."""
        runner = QuestRunner()
        runner.load_definitions(integration_quest_def)
        runner.start_quest("exploration_quest")
        
        # Simulate trigger event
        mock_window.gameplay_event_bus.emit("on_enter", zone="landmark_trigger_1")
        events = mock_window.gameplay_event_bus.drain()
        
        # Process and get emitted quest events
        emitted = runner.process_events(events)
        
        # Re-emit to bus (this is what QuestManager does)
        for event in emitted:
            mock_window.gameplay_event_bus.emit_event(event)
        
        # Verify events are in the bus
        pending = mock_window.gameplay_event_bus.peek()
        quest_events = [e for e in pending if e.source_behaviour == "QuestRunner"]
        assert len(quest_events) > 0


class TestQuestRunnerQuestHookIntegration:
    """Tests for QuestRunner emitted events being received by QuestHook."""

    def test_quest_hook_receives_progress_events(self, mock_window, integration_quest_def):
        """QuestHook can listen to quest_stage_completed events."""
        from engine.behaviours.quest_hook import QuestHookBehaviour
        
        runner = QuestRunner()
        runner.load_definitions(integration_quest_def)
        runner.start_quest("exploration_quest")
        
        # Set up QuestHook that listens for stage completion
        entity = MagicMock()
        entity.mesh_id = "hook_entity"
        quest_hook = QuestHookBehaviour(
            entity,
            mock_window,
            quest_id="exploration_quest",
            step_id="track_progress",
            listen_events=["quest_stage_completed"],
            target_count=2,
        )
        
        # Complete stage 1
        mock_window.gameplay_event_bus.emit("on_enter", zone="landmark_trigger_1")
        events = mock_window.gameplay_event_bus.drain()
        emitted = runner.process_events(events)
        
        # Feed emitted events to QuestHook
        for event in emitted:
            if event.event_type in quest_hook.listen_events:
                quest_hook.handle_event(event.payload)
        
        # QuestHook should have counted the completion
        assert quest_hook.current_count == 1

    def test_full_integration_trigger_runner_hook(self, mock_window, integration_quest_def):
        """Full integration: TriggerVolume -> QuestRunner -> QuestHook."""
        from engine.behaviours.quest_hook import QuestHookBehaviour
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour
        
        # Set up QuestRunner
        runner = QuestRunner()
        runner.load_definitions(integration_quest_def)
        runner.start_quest("exploration_quest")
        
        # Set up TriggerVolume entity
        trigger_entity = MagicMock()
        trigger_entity.mesh_id = "landmark_trigger_1"
        trigger_entity.mesh_name = "Landmark Trigger 1"
        trigger_entity.center_x = 100.0
        trigger_entity.center_y = 100.0
        trigger_entity.width = 32
        trigger_entity.height = 32
        
        trigger = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=50,
            height=50,
            target_tags=["player"],
            on_enter_event="on_enter",
        )
        
        # Set up QuestHook listening for quest progress
        hook_entity = MagicMock()
        hook_entity.mesh_id = "hook_001"
        quest_hook = QuestHookBehaviour(
            hook_entity,
            mock_window,
            quest_id="exploration_quest",
            step_id="track_landmarks",
            listen_events=["quest_stage_completed"],
            target_count=2,
        )
        
        # Set up player
        player = MagicMock()
        player.mesh_id = "player_001"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 100.0  # Inside trigger
        player.center_y = 100.0
        
        # Set up scene
        mock_window.scene_controller = MagicMock()
        mock_window.scene_controller.all_sprites = [player]
        
        # Player enters trigger zone
        trigger.update(0.016)
        
        # Get trigger events
        trigger_events = mock_window.gameplay_event_bus.drain()
        enter_events = [e for e in trigger_events if e.event_type == "on_enter"]
        assert len(enter_events) == 1
        assert enter_events[0].payload.get("zone") == "landmark_trigger_1"
        
        # Process through QuestRunner
        emitted = runner.process_events(trigger_events)
        
        # Quest should have advanced
        state = runner.get_quest_state("exploration_quest")
        assert state is not None
        assert state.current_stage == "visit_landmark_2"
        
        # Feed emitted events to QuestHook
        for event in emitted:
            if event.event_type in quest_hook.listen_events:
                quest_hook.handle_event(event.payload)
        
        # QuestHook should have counted
        assert quest_hook.current_count == 1


class TestQuestRunnerSaveRestoreIntegration:
    """Integration tests for save/restore with QuestRunner."""

    def test_save_restore_continues_quest_progression(
        self, mock_window, integration_quest_def
    ):
        """Quest progression continues correctly after save/restore."""
        # Initial runner
        runner1 = QuestRunner()
        runner1.load_definitions(integration_quest_def)
        runner1.start_quest("exploration_quest")
        
        # Complete stage 1
        mock_window.gameplay_event_bus.emit("on_enter", zone="landmark_trigger_1")
        runner1.process_events(mock_window.gameplay_event_bus.drain())
        
        # Save state
        saved_state = runner1.get_state()
        
        # Create new runner (simulating game load)
        runner2 = QuestRunner()
        runner2.load_definitions(integration_quest_def)
        runner2.apply_state(saved_state)
        
        # Verify state restored correctly
        state = runner2.get_quest_state("exploration_quest")
        assert state is not None
        assert state.status == "active"
        assert state.current_stage == "visit_landmark_2"
        assert "visit_landmark_1" in state.completed_stages
        
        # Continue progression
        mock_window.gameplay_event_bus.emit("on_enter", zone="landmark_trigger_2")
        emitted = runner2.process_events(mock_window.gameplay_event_bus.drain())
        
        # Should complete the quest
        state = runner2.get_quest_state("exploration_quest")
        assert state is not None
        assert state.status == "completed"
        
        # Should have completion event
        assert any(e.event_type == "quest_completed" for e in emitted)


class TestDeterminismAcrossRestarts:
    """Tests for deterministic behavior across game restarts."""

    def test_same_events_same_result_after_restart(
        self, mock_window, integration_quest_def
    ):
        """Same event sequence produces same result after simulated restart."""
        # First run
        runner1 = QuestRunner(emit_sequence_start=5000)
        runner1.load_definitions(integration_quest_def)
        runner1.start_quest("exploration_quest")
        
        events1 = [
            GameplayEvent("on_enter", {"zone": "landmark_trigger_1"}, 1, "", ""),
            GameplayEvent("on_enter", {"zone": "landmark_trigger_2"}, 2, "", ""),
        ]
        emitted1 = runner1.process_events(events1)
        final_state1 = runner1.get_state()
        
        # Second run (fresh runner, same events)
        runner2 = QuestRunner(emit_sequence_start=5000)
        runner2.load_definitions(integration_quest_def)
        runner2.start_quest("exploration_quest")
        
        events2 = [
            GameplayEvent("on_enter", {"zone": "landmark_trigger_1"}, 1, "", ""),
            GameplayEvent("on_enter", {"zone": "landmark_trigger_2"}, 2, "", ""),
        ]
        emitted2 = runner2.process_events(events2)
        final_state2 = runner2.get_state()
        
        # Emitted events should be identical
        assert len(emitted1) == len(emitted2)
        for e1, e2 in zip(emitted1, emitted2):
            assert e1.event_type == e2.event_type
            assert e1.payload == e2.payload
            assert e1.sequence == e2.sequence
        
        # Final states should be identical
        assert final_state1 == final_state2
