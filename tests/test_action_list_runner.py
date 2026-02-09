"""Tests for ActionListRunner behaviour.

Tests cover:
- Config validation with actionable errors
- Deterministic action execution
- Save/restore round-trip
- Event ordering
"""

from __future__ import annotations

import pytest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_window():
    """Create a mock window with event bus and game state."""
    from engine.gameplay_event_bus import GameplayEventBus
    from engine.game_state_controller import GameState
    
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    
    # Mock game state controller
    game_state_ctrl = MagicMock()
    game_state_ctrl.state = GameState()
    window.game_state_controller = game_state_ctrl
    
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    
    return window


@pytest.fixture
def mock_entity():
    """Create a mock entity."""
    entity = MagicMock()
    entity.mesh_id = "action_runner_001"
    entity.mesh_name = "ActionRunner"
    entity.mesh_tags = []
    entity.behaviours = []
    return entity


# ============================================================================
# Config Validation Tests
# ============================================================================

class TestActionListRunnerValidation:
    """Tests for ActionListRunner config validation."""
    
    def test_valid_config(self):
        """Valid config passes validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [
                {"type": "emit_event", "event_type": "test_event"},
                {"type": "set_flag", "flag": "my_flag"},
            ],
        }
        
        errors = validate_action_list_runner_config(config)
        assert len(errors) == 0
    
    def test_empty_listen_events(self):
        """Empty listen_events fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": [],
            "actions": [{"type": "emit_event", "event_type": "test"}],
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("listen_events" in e.config_path for e in errors)
    
    def test_empty_actions(self):
        """Empty actions fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [],
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("actions" in e.config_path for e in errors)
    
    def test_unknown_action_type(self):
        """Unknown action type fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [{"type": "unknown_action"}],
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("unknown action type" in e.message for e in errors)
    
    def test_missing_action_type(self):
        """Missing action type fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [{"event_type": "test"}],  # Missing "type"
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("type" in e.config_path and "required" in e.message for e in errors)
    
    def test_emit_event_missing_event_type(self):
        """emit_event without event_type fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [{"type": "emit_event"}],  # Missing "event_type"
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("event_type" in e.config_path for e in errors)
    
    def test_set_flag_missing_flag(self):
        """set_flag without flag name fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [{"type": "set_flag"}],  # Missing "flag"
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("flag" in e.config_path for e in errors)
    
    def test_delay_invalid_duration(self):
        """delay with invalid duration fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [{"type": "delay", "duration": -1}],
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("duration" in e.config_path for e in errors)
    
    def test_negative_cooldown(self):
        """Negative cooldown fails validation."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": ["on_trigger"],
            "actions": [{"type": "emit_event", "event_type": "test"}],
            "cooldown": -1,
        }
        
        errors = validate_action_list_runner_config(config, entity_id="test")
        assert any("cooldown" in e.config_path for e in errors)
    
    def test_error_includes_entity_id(self):
        """Validation errors include entity_id."""
        from engine.behaviours.action_list_runner import validate_action_list_runner_config
        
        config = {
            "listen_events": [],
            "actions": [],
        }
        
        errors = validate_action_list_runner_config(config, entity_id="my_entity")
        assert all(e.entity_id == "my_entity" for e in errors)


# ============================================================================
# Action Execution Tests
# ============================================================================

class TestActionListRunnerExecution:
    """Tests for ActionListRunner action execution."""
    
    def test_emit_event_action(self, mock_window, mock_entity):
        """emit_event action emits correct event."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[
                {"type": "emit_event", "event_type": "my_event", "payload": {"key": "value"}},
            ],
        )
        
        # Trigger the action list
        behaviour.handle_event("trigger", {})
        behaviour.update(0.016)
        
        events = mock_window.gameplay_event_bus.peek()
        my_events = [e for e in events if e.event_type == "my_event"]
        assert len(my_events) == 1
        assert my_events[0].payload.get("key") == "value"
    
    def test_set_flag_action(self, mock_window, mock_entity):
        """set_flag action sets game state flag."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[{"type": "set_flag", "flag": "test_flag"}],
        )
        
        behaviour.handle_event("trigger", {})
        behaviour.update(0.016)
        
        assert mock_window.game_state_controller.state.flags.get("test_flag") is True
    
    def test_clear_flag_action(self, mock_window, mock_entity):
        """clear_flag action clears game state flag."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        # Pre-set flag
        mock_window.game_state_controller.state.flags["test_flag"] = True
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[{"type": "clear_flag", "flag": "test_flag"}],
        )
        
        behaviour.handle_event("trigger", {})
        behaviour.update(0.016)
        
        assert mock_window.game_state_controller.state.flags.get("test_flag") is False
    
    def test_add_tag_action(self, mock_window, mock_entity):
        """add_tag action adds tag to entity."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[{"type": "add_tag", "tag": "new_tag", "target": "self"}],
        )
        
        behaviour.handle_event("trigger", {})
        behaviour.update(0.016)
        
        assert "new_tag" in mock_entity.mesh_tags
    
    def test_remove_tag_action(self, mock_window, mock_entity):
        """remove_tag action removes tag from entity."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        mock_entity.mesh_tags = ["existing_tag"]
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[{"type": "remove_tag", "tag": "existing_tag", "target": "self"}],
        )
        
        behaviour.handle_event("trigger", {})
        behaviour.update(0.016)
        
        assert "existing_tag" not in mock_entity.mesh_tags
    
    def test_delay_action(self, mock_window, mock_entity):
        """delay action pauses execution."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[
                {"type": "emit_event", "event_type": "first"},
                {"type": "delay", "duration": 0.5},
                {"type": "emit_event", "event_type": "second"},
            ],
        )
        
        behaviour.handle_event("trigger", {})
        
        # First update - executes first event and delay
        behaviour.update(0.016)
        events = mock_window.gameplay_event_bus.peek()
        assert any(e.event_type == "first" for e in events)
        assert not any(e.event_type == "second" for e in events)
        
        # Not enough time passed
        behaviour.update(0.2)
        events = mock_window.gameplay_event_bus.peek()
        assert not any(e.event_type == "second" for e in events)
        
        # Enough time passes
        behaviour.update(0.4)
        events = mock_window.gameplay_event_bus.peek()
        assert any(e.event_type == "second" for e in events)
    
    def test_event_filter(self, mock_window, mock_entity):
        """Event filter restricts which events trigger actions."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            event_filter={"zone": "special_zone"},
            actions=[{"type": "emit_event", "event_type": "triggered"}],
        )
        
        # Non-matching event
        behaviour.handle_event("trigger", {"zone": "other_zone"})
        behaviour.update(0.016)
        events = mock_window.gameplay_event_bus.peek()
        assert not any(e.event_type == "triggered" for e in events)
        
        # Matching event
        behaviour.handle_event("trigger", {"zone": "special_zone"})
        behaviour.update(0.016)
        events = mock_window.gameplay_event_bus.peek()
        assert any(e.event_type == "triggered" for e in events)
    
    def test_run_once(self, mock_window, mock_entity):
        """run_once prevents multiple executions."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            run_once=True,
            actions=[{"type": "emit_event", "event_type": "triggered"}],
        )
        
        # First trigger works
        assert behaviour.handle_event("trigger", {}) is True
        behaviour.update(0.016)
        
        # Drain events
        mock_window.gameplay_event_bus.drain()
        
        # Second trigger is ignored
        assert behaviour.handle_event("trigger", {}) is False
        behaviour.update(0.016)
        events = mock_window.gameplay_event_bus.peek()
        assert not any(e.event_type == "triggered" for e in events)
    
    def test_cooldown(self, mock_window, mock_entity):
        """Cooldown prevents rapid re-triggering."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            cooldown=1.0,
            actions=[{"type": "emit_event", "event_type": "triggered"}],
        )
        
        # First trigger works
        behaviour.handle_event("trigger", {})
        behaviour.update(0.016)
        mock_window.gameplay_event_bus.drain()
        
        # Second trigger during cooldown is blocked
        assert behaviour.handle_event("trigger", {}) is False
        
        # After cooldown, trigger works again
        behaviour.update(1.0)
        assert behaviour.handle_event("trigger", {}) is True


# ============================================================================
# Determinism Tests
# ============================================================================

class TestActionListRunnerDeterminism:
    """Tests for deterministic action execution."""
    
    def test_action_order_is_deterministic(self, mock_window, mock_entity):
        """Actions execute in defined order."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[
                {"type": "emit_event", "event_type": "event_1"},
                {"type": "emit_event", "event_type": "event_2"},
                {"type": "emit_event", "event_type": "event_3"},
            ],
        )
        
        behaviour.handle_event("trigger", {})
        behaviour.update(0.016)
        
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events if e.event_type.startswith("event_")]
        
        # Account for action_list_started and action_list_completed
        assert event_types == ["event_1", "event_2", "event_3"]
    
    def test_same_inputs_same_outputs(self, mock_window, mock_entity):
        """Same trigger sequence produces same results."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        from engine.gameplay_event_bus import GameplayEventBus
        
        results = []
        
        for _ in range(2):
            mock_window.gameplay_event_bus = GameplayEventBus()
            
            behaviour = ActionListRunnerBehaviour(
                mock_entity,
                mock_window,
                listen_events=["trigger"],
                actions=[
                    {"type": "emit_event", "event_type": "a"},
                    {"type": "emit_event", "event_type": "b"},
                ],
            )
            
            behaviour.handle_event("trigger", {})
            behaviour.update(0.016)
            
            events = mock_window.gameplay_event_bus.peek()
            results.append([e.event_type for e in events])
        
        assert results[0] == results[1]


# ============================================================================
# Save/Restore Tests
# ============================================================================

class TestActionListRunnerSaveRestore:
    """Tests for save/restore functionality."""
    
    def test_save_restore_roundtrip(self, mock_window, mock_entity):
        """State survives save/restore cycle."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour1 = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[
                {"type": "emit_event", "event_type": "first"},
                {"type": "delay", "duration": 1.0},
                {"type": "emit_event", "event_type": "second"},
            ],
        )
        
        # Trigger and partially execute
        behaviour1.handle_event("trigger", {})
        behaviour1.update(0.016)  # Executes first, starts delay
        behaviour1.update(0.3)   # In the middle of delay
        
        # Save state
        state = behaviour1.saveable_state()
        
        # Create new behaviour and restore
        behaviour2 = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[
                {"type": "emit_event", "event_type": "first"},
                {"type": "delay", "duration": 1.0},
                {"type": "emit_event", "event_type": "second"},
            ],
        )
        behaviour2.restore_state(state)
        
        # Verify state restored
        assert behaviour2._run_count == behaviour1._run_count
        assert len(behaviour2._pending_actions) == len(behaviour1._pending_actions)
        assert behaviour2._pending_index == behaviour1._pending_index
        assert abs(behaviour2._delay_remaining - behaviour1._delay_remaining) < 0.001
    
    def test_mid_action_restore_continues(self, mock_window, mock_entity):
        """Restored mid-action state continues correctly."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        from engine.gameplay_event_bus import GameplayEventBus
        
        behaviour1 = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[
                {"type": "emit_event", "event_type": "first"},
                {"type": "delay", "duration": 0.5},
                {"type": "emit_event", "event_type": "second"},
            ],
        )
        
        behaviour1.handle_event("trigger", {})
        behaviour1.update(0.016)  # first + start delay
        behaviour1.update(0.2)   # mid-delay
        
        state = behaviour1.saveable_state()
        
        # New bus for clean slate
        mock_window.gameplay_event_bus = GameplayEventBus()
        
        behaviour2 = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger"],
            actions=[
                {"type": "emit_event", "event_type": "first"},
                {"type": "delay", "duration": 0.5},
                {"type": "emit_event", "event_type": "second"},
            ],
        )
        behaviour2.restore_state(state)
        
        # Continue execution
        behaviour2.update(0.4)  # Should complete delay and emit second
        
        events = mock_window.gameplay_event_bus.peek()
        assert any(e.event_type == "second" for e in events)
    
    def test_inspector_state(self, mock_window, mock_entity):
        """Inspector state returns expected summary."""
        from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
        
        behaviour = ActionListRunnerBehaviour(
            mock_entity,
            mock_window,
            listen_events=["trigger_a", "trigger_b"],
            actions=[{"type": "emit_event", "event_type": "test"}],
        )
        
        state = behaviour.get_inspector_state()
        
        assert "enabled" in state
        assert "is_running" in state
        assert "run_count" in state
        assert "action_count" in state
        assert "listening_to" in state
        assert len(state["listening_to"]) == 2
