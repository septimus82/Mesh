"""Integration tests for CutsceneRunner.

Test integration with:
- ActionListRunner (via run_actions events)
- DialogueRunner (via start_dialogue events)
- GameplayEventBus patterns
- Save/load pipeline compatibility
"""
from __future__ import annotations

import pytest
from typing import Any

from engine.cutscene_runtime.runner import (
    CutsceneRunner,
    CutsceneRunnerState,
    simulate_cutscene,
)
from engine.cutscene_runtime.schema import CUTSCENE_SCHEMA_VERSION

from tests.cutscene_helpers import MockFlags, MockEventBus, make_script


# =============================================================================
# ActionListRunner Integration
# =============================================================================

class TestActionListIntegration:
    """Test integration with ActionListRunner patterns."""
    
    def test_run_actions_emits_action_list(self) -> None:
        """run_actions command emits cutscene_run_actions event with actions."""
        bus = MockEventBus()
        flags = MockFlags()
        runner = CutsceneRunner(event_bus=bus, flag_provider=flags, flag_setter=flags)
        
        script = make_script([
            {"type": "run_actions", "actions": [
                {"type": "spawn", "prefab": "enemy_grunt", "x": 100, "y": 200},
                {"type": "play_sound", "sound": "alert"},
            ]},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        events = bus.filter("cutscene_run_actions")
        assert len(events) == 1
        
        actions = events[0]["payload"]["actions"]
        assert len(actions) == 2
        assert actions[0]["type"] == "spawn"
        assert actions[0]["prefab"] == "enemy_grunt"
        assert actions[1]["type"] == "play_sound"
    
    def test_run_actions_preserves_action_data(self) -> None:
        """run_actions preserves all action fields."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        complex_action = {
            "type": "camera_shake",
            "intensity": 5.0,
            "duration": 0.5,
            "falloff": "linear",
        }
        
        script = make_script([
            {"type": "run_actions", "actions": [complex_action]},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        events = bus.filter("cutscene_run_actions")
        assert len(events) == 1
        
        restored_action = events[0]["payload"]["actions"][0]
        assert restored_action["type"] == "camera_shake"
        assert restored_action["intensity"] == 5.0
        assert restored_action["duration"] == 0.5
        assert restored_action["falloff"] == "linear"
    
    def test_sequential_run_actions_emit_in_order(self) -> None:
        """Multiple run_actions commands emit events in order."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "run_actions", "actions": [{"type": "action1"}]},
            {"type": "run_actions", "actions": [{"type": "action2"}]},
            {"type": "run_actions", "actions": [{"type": "action3"}]},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        events = bus.filter("cutscene_run_actions")
        assert len(events) == 3
        
        # Verify order
        assert events[0]["payload"]["actions"][0]["type"] == "action1"
        assert events[1]["payload"]["actions"][0]["type"] == "action2"
        assert events[2]["payload"]["actions"][0]["type"] == "action3"


# =============================================================================
# DialogueRunner Integration
# =============================================================================

class TestDialogueIntegration:
    """Test integration with DialogueRunner patterns."""
    
    def test_start_dialogue_emits_event(self) -> None:
        """start_dialogue command emits cutscene_start_dialogue event."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "start_dialogue", "dialogue_id": "npc_greeting", "target": "npc_shopkeeper"},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        events = bus.filter("cutscene_start_dialogue")
        assert len(events) == 1
        assert events[0]["payload"]["dialogue_id"] == "npc_greeting"
        assert events[0]["payload"]["target"] == "npc_shopkeeper"
    
    def test_start_dialogue_with_node_id(self) -> None:
        """start_dialogue can specify starting node_id."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "start_dialogue", "dialogue_id": "quest_dialogue", "target": "quest_giver", "node_id": "quest_complete"},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        events = bus.filter("cutscene_start_dialogue")
        assert len(events) == 1
        assert events[0]["payload"]["node_id"] == "quest_complete"
    
    def test_dialogue_after_wait(self) -> None:
        """Dialogue can be started after wait command."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "wait", "duration": 1.0},
            {"type": "start_dialogue", "dialogue_id": "delayed_dialogue", "target": "npc"},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)  # Start wait
        runner.tick(1.0)  # Complete wait
        
        events = bus.filter("cutscene_start_dialogue")
        assert len(events) == 1
        assert events[0]["payload"]["dialogue_id"] == "delayed_dialogue"


# =============================================================================
# GameplayEventBus Integration
# =============================================================================

class TestEventBusIntegration:
    """Test GameplayEventBus patterns."""
    
    def test_emit_event_includes_source_script(self) -> None:
        """Emitted events include source_script in payload."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "emit_event", "event_type": "custom_event", "payload": {"value": 42}},
            {"type": "stop"},
        ], script_id="my_cutscene")
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        events = bus.filter("custom_event")
        assert len(events) == 1
        assert events[0]["payload"]["source_script"] == "my_cutscene"
        assert events[0]["payload"]["value"] == 42
    
    def test_lifecycle_events_emitted(self) -> None:
        """Cutscene emits started and completed lifecycle events."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "stop"},
        ], script_id="lifecycle_test")
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        # Check lifecycle events
        assert bus.count("cutscene_started") == 1
        assert bus.count("cutscene_completed") == 1
        
        started = bus.filter("cutscene_started")[0]
        assert started["payload"]["script_id"] == "lifecycle_test"
        
        completed = bus.filter("cutscene_completed")[0]
        assert completed["payload"]["script_id"] == "lifecycle_test"
    
    def test_stop_command_emits_stopped_event(self) -> None:
        """Stop via command emits cutscene_completed (not stopped)."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        # stop command results in completion
        assert bus.count("cutscene_completed") == 1
        assert bus.count("cutscene_stopped") == 0
    
    def test_external_stop_emits_stopped_event(self) -> None:
        """External stop() call emits cutscene_stopped event."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "wait", "duration": 10.0},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        runner.stop()  # External stop
        
        assert bus.count("cutscene_stopped") == 1
        assert bus.count("cutscene_completed") == 0


# =============================================================================
# Save/Load Pipeline Integration
# =============================================================================

class TestSavePipelineIntegration:
    """Test save/load pipeline compatibility."""
    
    def test_state_dict_json_serializable(self) -> None:
        """State dict is JSON serializable."""
        import json
        
        bus = MockEventBus()
        flags = MockFlags({"test_flag": True})
        runner = CutsceneRunner(event_bus=bus, flag_provider=flags, flag_setter=flags)
        
        script = make_script([
            {"type": "branch_on_flag", "flag": "test_flag", "true_goto": "next", "false_goto": "next"},
            {"type": "label", "name": "next"},
            {"type": "wait", "duration": 2.0},
            {"type": "emit_event", "event_type": "test"},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        runner.tick(0.5)
        
        # Get state and serialize
        state = runner.saveable_state()
        json_str = json.dumps(state)
        
        # Verify roundtrip
        restored_dict = json.loads(json_str)
        assert restored_dict["command_index"] == state["command_index"]
        assert restored_dict["is_running"] == state["is_running"]
    
    def test_state_restoration_preserves_wait(self) -> None:
        """State restoration preserves mid-wait state."""
        flags = MockFlags()
        bus1 = MockEventBus()
        runner1 = CutsceneRunner(event_bus=bus1, flag_provider=flags, flag_setter=flags)
        
        script = make_script([
            {"type": "wait", "duration": 2.0},
            {"type": "emit_event", "event_type": "after_wait"},
            {"type": "stop"},
        ])
        
        runner1.load_script(script)
        runner1.start()
        runner1.tick(0.0)
        runner1.tick(0.5)
        
        # Save mid-wait
        state = runner1.saveable_state()
        assert state["wait_remaining"] == pytest.approx(1.5)
        
        # Restore to new runner
        bus2 = MockEventBus()
        runner2 = CutsceneRunner(event_bus=bus2, flag_provider=flags, flag_setter=flags)
        runner2.load_script(script)
        runner2.restore_state(state)
        
        # Continue and complete
        runner2.tick(1.5)
        
        # Event should fire after wait completes
        assert bus2.count("after_wait") == 1
    
    def test_multiple_save_restore_cycles(self) -> None:
        """Multiple save/restore cycles maintain consistency."""
        flags = MockFlags()
        
        script = make_script([
            {"type": "emit_event", "event_type": "event1"},
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "event2"},
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "event3"},
            {"type": "stop"},
        ])
        
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus, flag_provider=flags, flag_setter=flags)
        runner.load_script(script)
        runner.start()
        
        # First tick
        runner.tick(0.0)
        state1 = runner.saveable_state()
        
        # Restore and continue
        bus.clear()
        runner2 = CutsceneRunner(event_bus=bus, flag_provider=flags, flag_setter=flags)
        runner2.load_script(script)
        runner2.restore_state(state1)
        runner2.tick(0.5)
        state2 = runner2.saveable_state()
        
        # Restore again and complete
        bus.clear()
        runner3 = CutsceneRunner(event_bus=bus, flag_provider=flags, flag_setter=flags)
        runner3.load_script(script)
        runner3.restore_state(state2)
        runner3.tick(0.5)  # Complete first wait
        runner3.tick(1.0)  # Complete second wait and finish
        
        # Should have event2 and event3 after restoration
        assert bus.count("event2") == 1
        assert bus.count("event3") == 1


# =============================================================================
# Complex Scenario Tests
# =============================================================================

class TestComplexScenarios:
    """Test complex multi-step scenarios."""
    
    def test_branching_with_actions_and_dialogue(self) -> None:
        """Complex scenario with branching, actions, and dialogue."""
        flags = MockFlags({"quest_complete": True})
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus, flag_provider=flags, flag_setter=flags)
        
        script = make_script([
            {"type": "emit_event", "event_type": "cutscene_start"},
            {"type": "branch_on_flag", "flag": "quest_complete", "true_goto": "victory", "false_goto": "failure"},
            
            {"type": "label", "name": "victory"},
            {"type": "run_actions", "actions": [{"type": "spawn_confetti"}]},
            {"type": "start_dialogue", "dialogue_id": "victory_dialogue", "target": "npc"},
            {"type": "goto", "target": "end"},
            
            {"type": "label", "name": "failure"},
            {"type": "start_dialogue", "dialogue_id": "failure_dialogue", "target": "npc"},
            
            {"type": "label", "name": "end"},
            {"type": "emit_event", "event_type": "cutscene_end"},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        # Verify victory path taken
        assert bus.count("cutscene_run_actions") == 1
        actions_event = bus.filter("cutscene_run_actions")[0]
        assert actions_event["payload"]["actions"][0]["type"] == "spawn_confetti"
        
        # Verify victory dialogue started
        dialogue_events = bus.filter("cutscene_start_dialogue")
        assert len(dialogue_events) == 1
        assert dialogue_events[0]["payload"]["dialogue_id"] == "victory_dialogue"
    
    def test_timed_sequence_with_events(self) -> None:
        """Timed sequence emitting events at specific times."""
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus)
        
        script = make_script([
            {"type": "emit_event", "event_type": "phase_1"},
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "phase_2"},
            {"type": "wait", "duration": 0.5},
            {"type": "emit_event", "event_type": "phase_3"},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        
        # Track which events fired at each tick
        runner.tick(0.0)  # Should fire phase_1
        after_t0 = bus.count("phase_1")
        
        runner.tick(0.5)  # Still waiting
        after_t05 = bus.count("phase_2")
        
        runner.tick(0.5)  # Should fire phase_2
        after_t1 = bus.count("phase_2")
        
        runner.tick(0.5)  # Should fire phase_3
        after_t15 = bus.count("phase_3")
        
        assert after_t0 == 1
        assert after_t05 == 0  # Not yet
        assert after_t1 == 1
        assert after_t15 == 1
    
    def test_flag_state_propagation(self) -> None:
        """Flags set by cutscene affect subsequent branches."""
        flags = MockFlags()
        bus = MockEventBus()
        runner = CutsceneRunner(event_bus=bus, flag_provider=flags, flag_setter=flags)
        
        script = make_script([
            {"type": "branch_on_flag", "flag": "initialized", "true_goto": "skip_init", "false_goto": "do_init"},
            
            {"type": "label", "name": "do_init"},
            {"type": "set_flag", "flag": "initialized"},
            {"type": "emit_event", "event_type": "initialized"},
            
            {"type": "label", "name": "skip_init"},
            {"type": "branch_on_flag", "flag": "initialized", "true_goto": "ready", "false_goto": "error"},
            
            {"type": "label", "name": "ready"},
            {"type": "emit_event", "event_type": "ready"},
            {"type": "goto", "target": "end"},
            
            {"type": "label", "name": "error"},
            {"type": "emit_event", "event_type": "error"},
            
            {"type": "label", "name": "end"},
            {"type": "stop"},
        ])
        
        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        
        # Should have initialized and be ready
        assert bus.count("initialized") == 1
        assert bus.count("ready") == 1
        assert bus.count("error") == 0
        assert flags.get_flag("initialized") is True


# =============================================================================
# Simulation API Tests
# =============================================================================

class TestSimulationAPI:
    """Test the simulate_cutscene API."""
    
    def test_simulate_returns_final_flags(self) -> None:
        """Simulation returns final flag state."""
        script = make_script([
            {"type": "set_flag", "flag": "flag_a"},
            {"type": "set_flag", "flag": "flag_b"},
            {"type": "clear_flag", "flag": "flag_c"},
            {"type": "stop"},
        ])
        
        result = simulate_cutscene(script, [0.0], flags={"flag_c": True})
        
        assert result["ok"] is True
        assert result["flags"]["flag_a"] is True
        assert result["flags"]["flag_b"] is True
        assert result["flags"]["flag_c"] is False
    
    def test_simulate_tracks_steps(self) -> None:
        """Simulation tracks step-by-step progress."""
        script = make_script([
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "test"},
            {"type": "stop"},
        ])
        
        result = simulate_cutscene(script, [0.0, 0.5, 0.5, 0.0])
        
        assert result["ok"] is True
        assert len(result["steps"]) >= 3
        
        # Check step data
        assert result["steps"][0]["dt"] == 0.0
        assert result["steps"][0]["command_index"] == 0
    
    def test_simulate_deterministic_branches(self) -> None:
        """Simulation produces deterministic branch results."""
        script = make_script([
            {"type": "branch_on_flag", "flag": "choice", "true_goto": "yes", "false_goto": "no"},
            {"type": "label", "name": "yes"},
            {"type": "emit_event", "event_type": "chose_yes"},
            {"type": "goto", "target": "end"},
            {"type": "label", "name": "no"},
            {"type": "emit_event", "event_type": "chose_no"},
            {"type": "label", "name": "end"},
            {"type": "stop"},
        ])
        
        # Run multiple times with same flags
        results = [
            simulate_cutscene(script, [0.0], flags={"choice": True})
            for _ in range(3)
        ]
        
        # All results should be identical
        for i, r in enumerate(results):
            assert r["ok"] is True
            yes_events = [e for e in r["emitted_events"] if e["type"] == "chose_yes"]
            assert len(yes_events) == 1, f"Run {i} had wrong event count"
