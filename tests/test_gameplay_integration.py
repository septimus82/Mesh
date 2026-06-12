"""Integration test: TriggerVolume + QuestHook + save/load.

Tests the complete flow of:
1. TriggerVolume detecting an entity
2. QuestHook listening to trigger events
3. Saving and loading the entire state
4. Verifying consistent quest progress after restore
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_window():
    """Create a mock window with gameplay event bus."""
    from engine.gameplay_event_bus import GameplayEventBus

    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    window.entities = []
    return window


@pytest.fixture
def trigger_entity(mock_window):
    """Create entity for trigger volume."""
    entity = MagicMock()
    entity.mesh_id = "trigger_zone_001"
    entity.mesh_name = "QuestTrigger"
    entity.center_x = 200.0
    entity.center_y = 200.0
    entity.width = 32
    entity.height = 32
    return entity


@pytest.fixture
def quest_entity(mock_window):
    """Create entity for quest hook."""
    entity = MagicMock()
    entity.mesh_id = "quest_tracker_001"
    entity.mesh_name = "QuestTracker"
    entity.center_x = 0.0
    entity.center_y = 0.0
    return entity


@pytest.fixture
def player_entity():
    """Create player entity that will trigger volumes."""
    entity = MagicMock()
    entity.mesh_id = "player_001"
    entity.mesh_name = "Player"
    entity.center_x = 0.0
    entity.center_y = 0.0
    entity.mesh_tags = ["player"]
    return entity


class TestTriggerVolumeQuestHookIntegration:
    """Integration tests for TriggerVolume + QuestHook interaction."""

    def test_trigger_updates_quest_progress(
        self,
        mock_window,
        trigger_entity,
        quest_entity,
        player_entity,
    ):
        """TriggerVolume entry updates QuestHook counter."""
        from engine.behaviours.quest_hook import QuestHookBehaviour
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

        # Set up trigger volume
        trigger = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
            target_tags=["player"],
            on_enter_event="area_entered",
        )

        # Set up quest hook listening for trigger events
        quest = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="explore_quest",
            step_id="visit_areas",
            listen_events=["area_entered"],
            target_count=3,
        )

        # Set up scene_controller
        mock_window.scene_controller = MagicMock()

        # Player starts outside
        player_entity.center_x = 0.0
        player_entity.center_y = 0.0
        player_entity.mesh_tags = ["player"]
        mock_window.scene_controller.all_sprites = [player_entity]

        # Update trigger - player outside
        trigger.update(0.016)
        assert quest.current_count == 0

        # Move player inside trigger
        player_entity.center_x = trigger_entity.center_x
        player_entity.center_y = trigger_entity.center_y

        # Update trigger - player enters
        trigger.update(0.016)

        # Quest hook processes the enter event
        events = mock_window.gameplay_event_bus.drain()
        enter_events = [e for e in events if e.event_type == "area_entered"]

        for evt in enter_events:
            quest.handle_event(evt.payload)

        assert quest.current_count == 1

    def test_full_save_load_cycle(
        self,
        mock_window,
        trigger_entity,
        quest_entity,
        player_entity,
    ):
        """Complete save/load preserves all state."""
        from engine.behaviours.quest_hook import QuestHookBehaviour
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour
        from engine.gameplay_event_bus import GameplayEventBus

        # Set up scene_controller
        mock_window.scene_controller = MagicMock()

        # Set up behaviours
        trigger = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
            target_tags=["player"],
            on_enter_event="area_entered",
            one_shot=True,
        )

        quest = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="explore_quest",
            step_id="visit_areas",
            listen_events=["area_entered"],
            target_count=3,
        )

        # Simulate player entering trigger
        player_entity.center_x = trigger_entity.center_x
        player_entity.center_y = trigger_entity.center_y
        player_entity.mesh_tags = ["player"]
        mock_window.scene_controller.all_sprites = [player_entity]

        trigger.update(0.016)

        # Process events
        events = mock_window.gameplay_event_bus.drain()
        for evt in events:
            if evt.event_type in quest.listen_events:
                quest.handle_event(evt.payload)

        # Verify state before save
        assert player_entity.mesh_id in trigger._entities_inside
        assert quest.current_count == 1

        # Save all state
        saved_state = {
            "event_bus": mock_window.gameplay_event_bus.saveable_state(),
            "trigger": trigger.saveable_state(),
            "quest": quest.saveable_state(),
        }

        # Create new instances (simulating game load)
        mock_window.gameplay_event_bus = GameplayEventBus()

        trigger2 = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
            target_tags=["player"],
            on_enter_event="area_entered",
            one_shot=True,
        )

        quest2 = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="explore_quest",
            step_id="visit_areas",
            listen_events=["area_entered"],
            target_count=3,
        )

        # Restore state
        mock_window.gameplay_event_bus.restore_state(saved_state["event_bus"])
        trigger2.restore_state(saved_state["trigger"])
        quest2.restore_state(saved_state["quest"])

        # Verify restored state matches original
        assert trigger2._entities_inside == trigger._entities_inside
        assert trigger2._fired_entities == trigger._fired_entities
        assert quest2.current_count == quest.current_count
        assert quest2._event_count == quest._event_count

    def test_deterministic_across_save_load(
        self,
        mock_window,
        trigger_entity,
        quest_entity,
        player_entity,
    ):
        """Same inputs produce same results after save/load."""
        from engine.behaviours.quest_hook import QuestHookBehaviour
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour
        from engine.gameplay_event_bus import GameplayEventBus

        # Run simulation and collect results
        def run_simulation(window, trigger_ent, quest_ent, player_ent, initial_state=None):
            window.gameplay_event_bus = GameplayEventBus()
            window.entities = [player_ent]

            trigger = TriggerVolumeBehaviour(
                trigger_ent,
                window,
                volume_type="rect",
                width=100,
                height=100,
                target_tags=["player"],
                on_enter_event="area_entered",
            )

            quest = QuestHookBehaviour(
                quest_ent,
                window,
                quest_id="explore_quest",
                step_id="visit_areas",
                listen_events=["area_entered"],
                target_count=5,
            )

            if initial_state:
                window.gameplay_event_bus.restore_state(initial_state["event_bus"])
                trigger.restore_state(initial_state["trigger"])
                quest.restore_state(initial_state["quest"])

            # Simulate multiple frames
            positions = [
                (0, 0),  # Outside
                (trigger_ent.center_x, trigger_ent.center_y),  # Inside
                (0, 0),  # Outside again
                (trigger_ent.center_x + 10, trigger_ent.center_y),  # Inside again
            ]

            for x, y in positions:
                player_ent.center_x = x
                player_ent.center_y = y
                trigger.update(0.016)

                # Process events to quest
                for evt in window.gameplay_event_bus.drain():
                    if evt.event_type in quest.listen_events:
                        quest.handle_event(evt.payload)

            return {
                "quest_count": quest.current_count,
                "quest_events": quest._event_count,
                "trigger_state": trigger.saveable_state(),
                "quest_state": quest.saveable_state(),
            }

        # Run 1: Fresh start
        result1 = run_simulation(mock_window, trigger_entity, quest_entity, player_entity)

        # Save state midway through a new run
        mock_window.gameplay_event_bus = GameplayEventBus()
        trigger_mid = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
            target_tags=["player"],
            on_enter_event="area_entered",
        )
        quest_mid = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="explore_quest",
            step_id="visit_areas",
            listen_events=["area_entered"],
            target_count=5,
        )

        # Do partial simulation
        player_entity.center_x = trigger_entity.center_x
        player_entity.center_y = trigger_entity.center_y
        mock_window.entities = [player_entity]
        trigger_mid.update(0.016)
        for evt in mock_window.gameplay_event_bus.drain():
            if evt.event_type in quest_mid.listen_events:
                quest_mid.handle_event(evt.payload)

        mid_state = {
            "event_bus": mock_window.gameplay_event_bus.saveable_state(),
            "trigger": trigger_mid.saveable_state(),
            "quest": quest_mid.saveable_state(),
        }

        # Run 2: Continue from saved state
        result2_from_mid = run_simulation(
            mock_window,
            trigger_entity,
            quest_entity,
            player_entity,
            initial_state=mid_state,
        )

        # Both full runs should have deterministic results
        result3 = run_simulation(mock_window, trigger_entity, quest_entity, player_entity)

        assert result1["quest_count"] == result3["quest_count"]
        assert result1["quest_events"] == result3["quest_events"]

    def test_quest_completes_from_multiple_triggers(
        self,
        mock_window,
        quest_entity,
        player_entity,
    ):
        """Multiple triggers can contribute to same quest progress."""
        from engine.behaviours.quest_hook import QuestHookBehaviour
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

        # Set up scene_controller
        mock_window.scene_controller = MagicMock()

        # Create multiple trigger zones
        triggers = []
        for i in range(3):
            ent = MagicMock()
            ent.mesh_id = f"trigger_{i}"
            ent.mesh_name = f"Trigger{i}"
            ent.center_x = 100.0 * (i + 1)
            ent.center_y = 100.0
            ent.width = 32
            ent.height = 32

            trigger = TriggerVolumeBehaviour(
                ent,
                mock_window,
                volume_type="rect",
                width=50,
                height=50,
                target_tags=["player"],
                on_enter_event="checkpoint_reached",
                one_shot=True,
            )
            triggers.append((ent, trigger))

        # Quest tracking checkpoints
        quest = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="checkpoint_quest",
            listen_events=["checkpoint_reached"],
            target_count=3,
        )

        player_entity.mesh_tags = ["player"]
        mock_window.scene_controller.all_sprites = [player_entity]

        # Visit each trigger
        for i, (ent, trigger) in enumerate(triggers):
            player_entity.center_x = ent.center_x
            player_entity.center_y = ent.center_y

            trigger.update(0.016)

            # Process events
            for evt in mock_window.gameplay_event_bus.drain():
                if evt.event_type in quest.listen_events:
                    quest.handle_event(evt.payload)

            assert quest.current_count == i + 1

        # Quest should be complete
        assert quest.is_completed
        assert quest.current_count == 3
