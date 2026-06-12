"""Golden tests for CutsceneRunner determinism and correctness.

Test Categories:
1. Basic command execution (wait, emit_event, set_flag, etc.)
2. Branching and goto
3. Save/restore mid-execution
4. Determinism: same dt + same flags => same result
5. Validation error handling
"""
from __future__ import annotations

import pytest

from engine.cutscene_runtime.runner import (
    CutsceneRunner,
    simulate_cutscene,
)
from engine.cutscene_runtime.schema import (
    CUTSCENE_SCHEMA_VERSION,
)
from tests.cutscene_helpers import MockEventBus, MockFlags, make_script

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_flags() -> MockFlags:
    return MockFlags()


@pytest.fixture
def mock_bus() -> MockEventBus:
    return MockEventBus()


@pytest.fixture
def runner(mock_bus: MockEventBus, mock_flags: MockFlags) -> CutsceneRunner:
    return CutsceneRunner(
        event_bus=mock_bus,
        flag_provider=mock_flags,
        flag_setter=mock_flags,
    )


# =============================================================================
# Basic Command Execution
# =============================================================================

class TestWaitCommand:
    """Test wait command execution."""

    def test_wait_exact_duration(self, runner: CutsceneRunner) -> None:
        """Wait completes exactly at duration."""
        script = make_script([
            {"type": "wait", "duration": 1.0},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        assert runner.start()

        # First tick - start waiting
        runner.tick(0.0)
        assert runner.current_command_index == 0
        assert runner._state.wait_remaining == 1.0

        # Partial tick
        runner.tick(0.5)
        assert runner.current_command_index == 0
        assert runner._state.wait_remaining == 0.5

        # Complete wait
        runner.tick(0.5)
        assert runner.current_command_index == 1
        assert runner._state.wait_remaining == 0.0

    def test_wait_overshoot(self, runner: CutsceneRunner) -> None:
        """Wait completes when dt exceeds remaining."""
        script = make_script([
            {"type": "wait", "duration": 1.0},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        assert runner.start()

        runner.tick(0.0)
        runner.tick(2.0)  # Overshoot

        assert runner.current_command_index == 1
        assert runner._state.wait_remaining == 0.0

    def test_wait_zero_duration(self, runner: CutsceneRunner) -> None:
        """Zero duration wait advances immediately."""
        script = make_script([
            {"type": "wait", "duration": 0.0},
            {"type": "emit_event", "event_type": "test_event"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        assert runner.start()

        runner.tick(0.0)
        assert runner.is_completed


class TestEmitEventCommand:
    """Test emit_event command execution."""

    def test_emit_event_basic(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """Emit event with type and payload."""
        script = make_script([
            {"type": "emit_event", "event_type": "quest_trigger", "payload": {"quest_id": "q1"}},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        assert runner.start()
        runner.tick(0.0)

        # Check emitted events (excluding cutscene_started/completed)
        quest_events = [e for e in mock_bus.events if e["type"] == "quest_trigger"]
        assert len(quest_events) == 1
        assert quest_events[0]["payload"]["quest_id"] == "q1"

    def test_emit_event_increments_counter(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """Each emit increments emitted_count."""
        script = make_script([
            {"type": "emit_event", "event_type": "event1"},
            {"type": "emit_event", "event_type": "event2"},
            {"type": "emit_event", "event_type": "event3"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        assert runner.start()
        runner.tick(0.0)

        assert runner._state.emitted_count == 3


class TestFlagCommands:
    """Test set_flag and clear_flag commands."""

    def test_set_flag(
        self, runner: CutsceneRunner, mock_flags: MockFlags
    ) -> None:
        """set_flag sets flag to true."""
        script = make_script([
            {"type": "set_flag", "flag": "test_flag"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        assert mock_flags.get_flag("test_flag") is False

        runner.start()
        runner.tick(0.0)

        assert mock_flags.get_flag("test_flag") is True

    def test_clear_flag(
        self, runner: CutsceneRunner, mock_flags: MockFlags
    ) -> None:
        """clear_flag sets flag to false."""
        mock_flags.set_flag("test_flag", True)

        script = make_script([
            {"type": "clear_flag", "flag": "test_flag"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        assert mock_flags.get_flag("test_flag") is False


class TestLabelAndGoto:
    """Test label and goto commands."""

    def test_goto_forward(self, runner: CutsceneRunner) -> None:
        """goto jumps forward to label."""
        script = make_script([
            {"type": "goto", "target": "skip_ahead"},
            {"type": "emit_event", "event_type": "should_skip"},
            {"type": "label", "name": "skip_ahead"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        # Should complete without emitting should_skip
        assert runner.is_completed
        assert runner._state.emitted_count == 0

    def test_goto_backward(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """goto can jump backward to label (looping)."""
        script = make_script([
            {"type": "label", "name": "loop_start"},
            {"type": "emit_event", "event_type": "loop_event"},
            {"type": "set_flag", "flag": "looped"},
            {"type": "branch_on_flag", "flag": "looped", "true_goto": "loop_end", "false_goto": "loop_start"},
            {"type": "label", "name": "loop_end"},
            {"type": "stop"},
        ])

        mock_flags = MockFlags()
        bus = MockEventBus()
        runner = CutsceneRunner(
            event_bus=bus,
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        # Should emit loop_event once, then exit
        loop_events = [e for e in bus.events if e["type"] == "loop_event"]
        assert len(loop_events) == 1


class TestBranchOnFlag:
    """Test branch_on_flag command."""

    def test_branch_true(self, runner: CutsceneRunner) -> None:
        """Branch takes true path when flag is set."""
        mock_flags = MockFlags({"test_flag": True})
        bus = MockEventBus()
        runner = CutsceneRunner(
            event_bus=bus,
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )

        script = make_script([
            {"type": "branch_on_flag", "flag": "test_flag", "true_goto": "true_path", "false_goto": "false_path"},
            {"type": "label", "name": "true_path"},
            {"type": "emit_event", "event_type": "took_true"},
            {"type": "goto", "target": "end"},
            {"type": "label", "name": "false_path"},
            {"type": "emit_event", "event_type": "took_false"},
            {"type": "label", "name": "end"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        assert bus.count("took_true") == 1
        assert bus.count("took_false") == 0

    def test_branch_false(self, runner: CutsceneRunner) -> None:
        """Branch takes false path when flag is not set."""
        mock_flags = MockFlags({"test_flag": False})
        bus = MockEventBus()
        runner = CutsceneRunner(
            event_bus=bus,
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )

        script = make_script([
            {"type": "branch_on_flag", "flag": "test_flag", "true_goto": "true_path", "false_goto": "false_path"},
            {"type": "label", "name": "true_path"},
            {"type": "emit_event", "event_type": "took_true"},
            {"type": "goto", "target": "end"},
            {"type": "label", "name": "false_path"},
            {"type": "emit_event", "event_type": "took_false"},
            {"type": "label", "name": "end"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        assert bus.count("took_true") == 0
        assert bus.count("took_false") == 1

    def test_branch_records_history(
        self, runner: CutsceneRunner, mock_flags: MockFlags
    ) -> None:
        """Branch records decision in branch_history."""
        mock_flags.set_flag("flag1", True)
        mock_flags.set_flag("flag2", False)

        script = make_script([
            {"type": "branch_on_flag", "flag": "flag1", "true_goto": "next1", "false_goto": "next1"},
            {"type": "label", "name": "next1"},
            {"type": "branch_on_flag", "flag": "flag2", "true_goto": "end", "false_goto": "end"},
            {"type": "label", "name": "end"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        history = runner._state.branch_history
        assert len(history) == 2
        assert history[0]["flag"] == "flag1"
        assert history[0]["value"] is True
        assert history[1]["flag"] == "flag2"
        assert history[1]["value"] is False


class TestRunActionsCommand:
    """Test run_actions command."""

    def test_run_actions_emits_event(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """run_actions emits cutscene_run_actions event."""
        script = make_script([
            {"type": "run_actions", "actions": [
                {"type": "spawn", "prefab": "enemy"},
                {"type": "play_sound", "sound": "alarm"},
            ]},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        action_events = [e for e in mock_bus.events if e["type"] == "cutscene_run_actions"]
        assert len(action_events) == 1
        assert len(action_events[0]["payload"]["actions"]) == 2


class TestStartDialogueCommand:
    """Test start_dialogue command."""

    def test_start_dialogue_emits_event(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """start_dialogue emits cutscene_start_dialogue event."""
        script = make_script([
            {"type": "start_dialogue", "dialogue_id": "npc_greeting", "target": "npc_001", "node_id": "start"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        dialogue_events = [e for e in mock_bus.events if e["type"] == "cutscene_start_dialogue"]
        assert len(dialogue_events) == 1
        assert dialogue_events[0]["payload"]["dialogue_id"] == "npc_greeting"
        assert dialogue_events[0]["payload"]["target"] == "npc_001"
        assert dialogue_events[0]["payload"]["node_id"] == "start"


class TestStopCommand:
    """Test stop command."""

    def test_stop_ends_cutscene(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """stop command ends cutscene and emits completed event."""
        script = make_script([
            {"type": "emit_event", "event_type": "before_stop"},
            {"type": "stop"},
            {"type": "emit_event", "event_type": "after_stop"},  # Should not execute
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        assert runner.is_completed
        assert not runner.is_running
        assert mock_bus.count("before_stop") == 1
        assert mock_bus.count("after_stop") == 0
        assert mock_bus.count("cutscene_completed") == 1


# =============================================================================
# Save/Restore
# =============================================================================

class TestSaveRestore:
    """Test save/restore functionality."""

    def test_saveable_state_roundtrip(self, runner: CutsceneRunner) -> None:
        """State survives save/restore roundtrip."""
        script = make_script([
            {"type": "wait", "duration": 2.0},
            {"type": "emit_event", "event_type": "after_wait"},
            {"type": "stop"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)  # Start wait
        runner.tick(0.5)  # Partial progress

        # Save state
        saved = runner.saveable_state()

        # Create new runner and restore
        mock_flags = MockFlags()
        bus = MockEventBus()
        runner2 = CutsceneRunner(
            event_bus=bus,
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )
        runner2.load_script(script)
        runner2.restore_state(saved)

        # Verify state restored
        assert runner2._state.command_index == 0
        assert runner2._state.wait_remaining == pytest.approx(1.5)
        assert runner2._state.is_running is True

    def test_restore_mid_wait_continues(self, runner: CutsceneRunner) -> None:
        """Restored runner continues from mid-wait correctly."""
        script = make_script([
            {"type": "wait", "duration": 2.0},
            {"type": "emit_event", "event_type": "after_wait"},
            {"type": "stop"},
        ])

        mock_flags = MockFlags()
        bus = MockEventBus()
        runner = CutsceneRunner(
            event_bus=bus,
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)
        runner.tick(0.5)

        # Save mid-wait
        saved = runner.saveable_state()

        # New runner
        bus2 = MockEventBus()
        runner2 = CutsceneRunner(
            event_bus=bus2,
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )
        runner2.load_script(script)
        runner2.restore_state(saved)

        # Continue from mid-wait
        runner2.tick(1.5)  # Complete the remaining wait and continue

        # After completing wait and executing remaining commands, cutscene completes
        assert runner2.is_completed
        assert bus2.count("after_wait") == 1

    def test_restore_preserves_branch_history(self, runner: CutsceneRunner) -> None:
        """Restored runner preserves branch history."""
        mock_flags = MockFlags({"test_flag": True})
        bus = MockEventBus()
        runner = CutsceneRunner(
            event_bus=bus,
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )

        script = make_script([
            {"type": "branch_on_flag", "flag": "test_flag", "true_goto": "next", "false_goto": "next"},
            {"type": "label", "name": "next"},
            {"type": "wait", "duration": 1.0},
            {"type": "stop"},
        ])

        runner.load_script(script)
        runner.start()
        runner.tick(0.0)  # Execute branch, start wait

        saved = runner.saveable_state()
        assert len(runner._state.branch_history) == 1

        # Restore to new runner
        runner2 = CutsceneRunner(
            event_bus=MockEventBus(),
            flag_provider=mock_flags,
            flag_setter=mock_flags,
        )
        runner2.load_script(script)
        runner2.restore_state(saved)

        assert len(runner2._state.branch_history) == 1
        assert runner2._state.branch_history[0]["flag"] == "test_flag"


# =============================================================================
# Determinism
# =============================================================================

class TestDeterminism:
    """Test deterministic execution."""

    def test_same_dt_same_result(self) -> None:
        """Same dt schedule produces same result."""
        script = make_script([
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "event1"},
            {"type": "wait", "duration": 0.5},
            {"type": "emit_event", "event_type": "event2"},
            {"type": "stop"},
        ])

        dt_schedule = [0.0, 0.3, 0.4, 0.3, 0.2, 0.3]

        result1 = simulate_cutscene(script, dt_schedule)
        result2 = simulate_cutscene(script, dt_schedule)

        assert result1["ok"] is True
        assert result2["ok"] is True
        assert result1["final_state"] == result2["final_state"]
        assert len(result1["emitted_events"]) == len(result2["emitted_events"])

    def test_same_flags_same_branch(self) -> None:
        """Same flag values produce same branch path."""
        script = make_script([
            {"type": "branch_on_flag", "flag": "choice", "true_goto": "path_a", "false_goto": "path_b"},
            {"type": "label", "name": "path_a"},
            {"type": "emit_event", "event_type": "chose_a"},
            {"type": "goto", "target": "end"},
            {"type": "label", "name": "path_b"},
            {"type": "emit_event", "event_type": "chose_b"},
            {"type": "label", "name": "end"},
            {"type": "stop"},
        ])

        result_true = simulate_cutscene(script, [0.0], flags={"choice": True})
        result_false = simulate_cutscene(script, [0.0], flags={"choice": False})

        # Results should differ based on flag
        true_events = [e for e in result_true["emitted_events"] if e["type"] == "chose_a"]
        false_events = [e for e in result_false["emitted_events"] if e["type"] == "chose_b"]

        assert len(true_events) == 1
        assert len(false_events) == 1

    def test_multiple_runs_identical(self) -> None:
        """Multiple runs with same inputs are identical."""
        script = make_script([
            {"type": "emit_event", "event_type": "start"},
            {"type": "wait", "duration": 0.5},
            {"type": "set_flag", "flag": "mid_flag"},
            {"type": "branch_on_flag", "flag": "mid_flag", "true_goto": "done", "false_goto": "done"},
            {"type": "label", "name": "done"},
            {"type": "emit_event", "event_type": "end"},
            {"type": "stop"},
        ])

        dt_schedule = [0.0, 0.2, 0.3, 0.1]
        results = [simulate_cutscene(script, dt_schedule) for _ in range(5)]

        for i, result in enumerate(results):
            assert result["ok"] is True, f"Run {i} failed"
            assert result["final_state"] == results[0]["final_state"], f"Run {i} differs"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_script(self, runner: CutsceneRunner) -> None:
        """Empty command list doesn't start."""
        script = make_script([])

        assert runner.load_script(script) == []
        assert runner.start() is False

    def test_stop_without_start(self, runner: CutsceneRunner) -> None:
        """Stop without start is no-op."""
        script = make_script([{"type": "stop"}])
        runner.load_script(script)

        # Should not raise
        runner.stop()
        assert not runner.is_running

    def test_tick_without_start(self, runner: CutsceneRunner) -> None:
        """Tick without start returns empty list."""
        script = make_script([
            {"type": "emit_event", "event_type": "test"},
            {"type": "stop"},
        ])
        runner.load_script(script)

        emitted = runner.tick(1.0)
        assert emitted == []

    def test_goto_invalid_label_rejected(self, runner: CutsceneRunner) -> None:
        """goto to invalid label is caught by validation."""
        script = make_script([
            {"type": "goto", "target": "nonexistent"},
            {"type": "emit_event", "event_type": "after_goto"},
            {"type": "stop"},
        ])

        errors = runner.load_script(script)

        # Validation catches undefined label
        assert len(errors) == 1
        assert errors[0].code == "goto.target.undefined"
        assert "nonexistent" in errors[0].message

    def test_implicit_completion(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """Cutscene completes when reaching end without stop."""
        script = make_script([
            {"type": "emit_event", "event_type": "only_event"},
        ])

        assert runner.load_script(script) == []
        runner.start()
        runner.tick(0.0)

        assert runner.is_completed
        assert mock_bus.count("cutscene_completed") == 1


# =============================================================================
# Inspector API
# =============================================================================

class TestInspectorAPI:
    """Test editor inspector API."""

    def test_get_inspector_state(self, runner: CutsceneRunner) -> None:
        """Inspector state includes expected fields."""
        script = make_script([
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "test"},
            {"type": "stop"},
        ], script_id="inspector_test")

        runner.load_script(script)
        runner.start()
        runner.tick(0.0)
        runner.tick(0.3)

        state = runner.get_inspector_state()

        assert state["script_id"] == "inspector_test"
        assert state["is_running"] is True
        assert state["completed"] is False
        assert state["command_index"] == 0
        assert state["command_count"] == 3
        assert state["current_command_type"] == "wait"
        assert state["wait_remaining"] == pytest.approx(0.7, abs=0.01)

    def test_get_command_list(self, runner: CutsceneRunner) -> None:
        """Command list includes summaries."""
        script = make_script([
            {"type": "wait", "duration": 1.5},
            {"type": "emit_event", "event_type": "my_event"},
            {"type": "label", "name": "my_label"},
            {"type": "goto", "target": "my_label"},
            {"type": "stop"},
        ])

        runner.load_script(script)

        commands = runner.get_command_list()

        assert len(commands) == 5
        assert commands[0]["type"] == "wait"
        assert commands[0]["duration"] == 1.5
        assert commands[1]["type"] == "emit_event"
        assert commands[1]["event_type"] == "my_event"
        assert commands[2]["type"] == "label"
        assert commands[2]["name"] == "my_label"
        assert commands[3]["type"] == "goto"
        assert commands[3]["target"] == "my_label"


# =============================================================================
# simulate_cutscene Tests
# =============================================================================

class TestSimulateCutscene:
    """Test simulate_cutscene helper function."""

    def test_simulate_basic_script(self) -> None:
        """Simulate basic script execution."""
        script = make_script([
            {"type": "emit_event", "event_type": "start"},
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "middle"},
            {"type": "stop"},
        ])

        result = simulate_cutscene(script, [0.0, 0.5, 0.5, 0.0])

        assert result["ok"] is True
        assert result["final_state"]["completed"] is True

        # Check steps
        assert len(result["steps"]) >= 3

    def test_simulate_with_flags(self) -> None:
        """Simulate with initial flag values."""
        script = make_script([
            {"type": "branch_on_flag", "flag": "test_flag", "true_goto": "yes", "false_goto": "no"},
            {"type": "label", "name": "yes"},
            {"type": "emit_event", "event_type": "yes_event"},
            {"type": "goto", "target": "end"},
            {"type": "label", "name": "no"},
            {"type": "emit_event", "event_type": "no_event"},
            {"type": "label", "name": "end"},
            {"type": "stop"},
        ])

        result = simulate_cutscene(script, [0.0], flags={"test_flag": True})

        assert result["ok"] is True
        yes_events = [e for e in result["emitted_events"] if e["type"] == "yes_event"]
        assert len(yes_events) == 1

    def test_simulate_flag_modification(self) -> None:
        """Simulate tracks flag modifications."""
        script = make_script([
            {"type": "set_flag", "flag": "new_flag"},
            {"type": "stop"},
        ])

        result = simulate_cutscene(script, [0.0])

        assert result["ok"] is True
        assert result["flags"]["new_flag"] is True

    def test_simulate_invalid_script(self) -> None:
        """Simulate reports validation errors."""
        script = {
            "schema_version": CUTSCENE_SCHEMA_VERSION,
            "id": "test",
            "commands": [
                {"type": "invalid_command_type"},
            ],
        }

        result = simulate_cutscene(script, [0.0])

        assert result["ok"] is False
        assert len(result["errors"]) > 0


# =============================================================================
# Validation Error Tests
# =============================================================================

class TestValidationErrors:
    """Test validation error handling."""

    def test_load_invalid_returns_errors(self, runner: CutsceneRunner) -> None:
        """Loading invalid script returns errors."""
        script = {
            "schema_version": CUTSCENE_SCHEMA_VERSION,
            "id": "test",
            "commands": [
                {"type": "wait"},  # Missing duration
            ],
        }

        errors = runner.load_script(script)

        assert len(errors) > 0
        assert errors[0].code == "wait.duration.required"

    def test_get_validation_errors(self, runner: CutsceneRunner) -> None:
        """get_validation_errors returns last errors."""
        script = {
            "schema_version": CUTSCENE_SCHEMA_VERSION,
            "id": "test",
            "commands": [
                {"type": "emit_event"},  # Missing event_type
            ],
        }

        runner.load_script(script)
        errors = runner.get_validation_errors()

        assert len(errors) > 0
        assert "event_type" in errors[0].message.lower()
