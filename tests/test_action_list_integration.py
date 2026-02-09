"""Integration test: TriggerVolume → ActionListRunner → QuestHook + Timer.

Tests the complete flow of:
1. TriggerVolume detecting player entry
2. ActionListRunner triggered by volume event
3. ActionListRunner emits quest progress event
4. ActionListRunner starts a timer
5. Timer fires and emits event
6. QuestHook tracks progress
"""

from __future__ import annotations

import pytest
from typing import Any, Dict, List
from unittest.mock import MagicMock


@pytest.fixture
def mock_window():
    """Create a mock window with gameplay event bus and game state."""
    from engine.gameplay_event_bus import GameplayEventBus
    from engine.game_state_controller import GameState
    
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    
    game_state_ctrl = MagicMock()
    game_state_ctrl.state = GameState()
    window.game_state_controller = game_state_ctrl
    
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    
    return window


class TestTriggerActionListIntegration:
    """Integration tests for TriggerVolume + ActionListRunner."""
    
    def test_trigger_fires_action_list_emits_quest_event(self, mock_window):
        """TriggerVolume → ActionListRunner → QuestHook chain."""
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        from engine.behaviours.quest_hook import QuestHookBehaviour
        
        # Create entities
        trigger_entity = MagicMock()
        trigger_entity.mesh_id = "trigger_zone"
        trigger_entity.mesh_name = "TriggerZone"
        trigger_entity.center_x = 100.0
        trigger_entity.center_y = 100.0
        trigger_entity.width = 32
        trigger_entity.height = 32
        
        action_entity = MagicMock()
        action_entity.mesh_id = "action_runner"
        action_entity.mesh_name = "ActionRunner"
        action_entity.mesh_tags = []
        action_entity.behaviours = []
        
        quest_entity = MagicMock()
        quest_entity.mesh_id = "quest_tracker"
        quest_entity.mesh_name = "QuestTracker"
        
        player = MagicMock()
        player.mesh_id = "player"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 0.0
        player.center_y = 0.0
        
        # Set up scene
        mock_window.scene_controller.all_sprites = [player, trigger_entity, action_entity]
        
        # Create behaviours
        trigger = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=50,
            height=50,
            target_tags=["player"],
            on_enter_event="zone_entered",
        )
        
        action_runner = ActionListRunnerBehaviour(
            action_entity,
            mock_window,
            listen_events=["zone_entered"],
            actions=[
                {"type": "emit_event", "event_type": "checkpoint_reached", "payload": {"zone": "zone_1"}},
                {"type": "set_flag", "flag": "visited_zone_1"},
            ],
        )
        
        quest_hook = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="explore",
            listen_events=["checkpoint_reached"],
            target_count=3,
        )
        
        # Move player into trigger
        player.center_x = trigger_entity.center_x
        player.center_y = trigger_entity.center_y
        
        # Update trigger - should emit zone_entered
        trigger.update(0.016)
        
        # Process events - action runner listens
        for evt in mock_window.gameplay_event_bus.drain():
            if evt.event_type in action_runner.listen_events:
                action_runner.handle_event(evt.event_type, evt.payload)
        
        # Update action runner - should execute actions
        action_runner.update(0.016)
        
        # Process events - quest hook listens
        for evt in mock_window.gameplay_event_bus.drain():
            if evt.event_type in quest_hook.listen_events:
                quest_hook.handle_event(evt.payload)
        
        # Verify results
        assert quest_hook.current_count == 1
        assert mock_window.game_state_controller.state.flags.get("visited_zone_1") is True
    
    def test_action_list_starts_timer(self, mock_window):
        """ActionListRunner can start a timer behaviour."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        from engine.behaviours.timer import TimerBehaviour
        
        # Create entities
        action_entity = MagicMock()
        action_entity.mesh_id = "action_runner"
        action_entity.mesh_name = "ActionRunner"
        action_entity.mesh_tags = []
        
        # Create timer behaviour (initially not running)
        timer = TimerBehaviour(
            action_entity,
            mock_window,
            duration=1.0,
            auto_start=False,
            timer_event="timer_done",
            timer_id="my_timer",
        )
        
        action_entity.behaviours = [timer]
        
        # Create action runner that starts the timer
        action_runner = ActionListRunnerBehaviour(
            action_entity,
            mock_window,
            listen_events=["start_countdown"],
            actions=[
                {"type": "start_timer", "target": "self", "timer_id": "my_timer"},
            ],
        )
        
        # Timer should not be running
        assert timer._running is False
        
        # Trigger action list
        action_runner.handle_event("start_countdown", {})
        action_runner.update(0.016)
        
        # Timer should now be running
        assert timer._running is True
    
    def test_full_chain_with_save_restore(self, mock_window):
        """Complete chain survives save/restore."""
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        from engine.behaviours.quest_hook import QuestHookBehaviour
        from engine.gameplay_event_bus import GameplayEventBus
        
        # Create entities
        trigger_entity = MagicMock()
        trigger_entity.mesh_id = "trigger"
        trigger_entity.mesh_name = "Trigger"
        trigger_entity.center_x = 100.0
        trigger_entity.center_y = 100.0
        trigger_entity.width = 32
        trigger_entity.height = 32
        
        action_entity = MagicMock()
        action_entity.mesh_id = "runner"
        action_entity.mesh_name = "Runner"
        action_entity.mesh_tags = []
        action_entity.behaviours = []
        
        quest_entity = MagicMock()
        quest_entity.mesh_id = "quest"
        quest_entity.mesh_name = "Quest"
        
        player = MagicMock()
        player.mesh_id = "player"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 0.0
        player.center_y = 0.0
        
        mock_window.scene_controller.all_sprites = [player]
        
        # Create behaviours
        trigger = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=50,
            height=50,
            target_tags=["player"],
            on_enter_event="entered",
        )
        
        action_runner = ActionListRunnerBehaviour(
            action_entity,
            mock_window,
            listen_events=["entered"],
            actions=[
                {"type": "emit_event", "event_type": "progress"},
                {"type": "delay", "duration": 1.0},
                {"type": "emit_event", "event_type": "delayed_progress"},
            ],
        )
        
        quest = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="test",
            listen_events=["progress", "delayed_progress"],
            target_count=2,
        )
        
        # Move player into trigger
        player.center_x = trigger_entity.center_x
        player.center_y = trigger_entity.center_y
        
        # Update trigger
        trigger.update(0.016)
        
        # Process trigger events
        for evt in mock_window.gameplay_event_bus.drain():
            if evt.event_type in action_runner.listen_events:
                action_runner.handle_event(evt.event_type, evt.payload)
        
        # Action runner executes first action and delay
        action_runner.update(0.016)
        action_runner.update(0.3)  # Mid-delay
        
        # Process first progress event
        for evt in mock_window.gameplay_event_bus.drain():
            if evt.event_type in quest.listen_events:
                quest.handle_event(evt.payload)
        
        assert quest.current_count == 1
        
        # Save all states
        saved = {
            "trigger": trigger.saveable_state(),
            "action_runner": action_runner.saveable_state(),
            "quest": quest.saveable_state(),
            "event_bus": mock_window.gameplay_event_bus.saveable_state(),
        }
        
        # "Reload" - fresh event bus
        mock_window.gameplay_event_bus = GameplayEventBus()
        
        # Create new behaviours
        trigger2 = TriggerVolumeBehaviour(
            trigger_entity,
            mock_window,
            volume_type="rect",
            width=50,
            height=50,
            target_tags=["player"],
            on_enter_event="entered",
        )
        
        action_runner2 = ActionListRunnerBehaviour(
            action_entity,
            mock_window,
            listen_events=["entered"],
            actions=[
                {"type": "emit_event", "event_type": "progress"},
                {"type": "delay", "duration": 1.0},
                {"type": "emit_event", "event_type": "delayed_progress"},
            ],
        )
        
        quest2 = QuestHookBehaviour(
            quest_entity,
            mock_window,
            quest_id="test",
            listen_events=["progress", "delayed_progress"],
            target_count=2,
        )
        
        # Restore states
        trigger2.restore_state(saved["trigger"])
        action_runner2.restore_state(saved["action_runner"])
        quest2.restore_state(saved["quest"])
        mock_window.gameplay_event_bus.restore_state(saved["event_bus"])
        
        # Quest count should be preserved
        assert quest2.current_count == 1
        
        # Action runner should still be in delay
        assert action_runner2.is_running is True
        
        # Continue execution - finish delay
        action_runner2.update(0.8)
        
        # Process delayed_progress event
        for evt in mock_window.gameplay_event_bus.drain():
            if evt.event_type in quest2.listen_events:
                quest2.handle_event(evt.payload)
        
        # Quest should now have both counts
        assert quest2.current_count == 2
        assert quest2.is_completed
    
    def test_deterministic_multi_action_sequence(self, mock_window):
        """Multiple triggers produce deterministic results."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        from engine.gameplay_event_bus import GameplayEventBus
        
        results = []
        
        for _ in range(3):
            mock_window.gameplay_event_bus = GameplayEventBus()
            mock_window.game_state_controller.state.flags.clear()
            
            entity = MagicMock()
            entity.mesh_id = "runner"
            entity.mesh_name = "Runner"
            entity.mesh_tags = []
            entity.behaviours = []
            
            action_runner = ActionListRunnerBehaviour(
                entity,
                mock_window,
                listen_events=["trigger"],
                actions=[
                    {"type": "emit_event", "event_type": "event_a"},
                    {"type": "set_flag", "flag": "flag_a"},
                    {"type": "emit_event", "event_type": "event_b"},
                    {"type": "set_flag", "flag": "flag_b"},
                ],
            )
            
            # Same trigger sequence
            action_runner.handle_event("trigger", {"count": 1})
            action_runner.update(0.016)
            
            events = mock_window.gameplay_event_bus.peek()
            event_types = [e.event_type for e in events]
            flag_state = dict(mock_window.game_state_controller.state.flags)
            
            results.append((event_types, flag_state))
        
        # All runs should produce identical results
        assert results[0] == results[1] == results[2]
