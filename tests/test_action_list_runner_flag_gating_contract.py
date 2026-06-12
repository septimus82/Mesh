"""Contract tests for ActionListRunner flag gating and validation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from engine.behaviours.action_list_runner import ActionListRunnerBehaviour, validate_action_list_runner_config
from engine.game_state_controller import GameState
from engine.gameplay_event_bus import GameplayEventBus


def _make_window() -> SimpleNamespace:
    game_state_ctrl = SimpleNamespace(state=GameState())
    scene_controller = SimpleNamespace(all_sprites=[])
    return SimpleNamespace(
        gameplay_event_bus=GameplayEventBus(),
        game_state_controller=game_state_ctrl,
        scene_controller=scene_controller,
    )


def _make_entity() -> MagicMock:
    entity = MagicMock()
    entity.mesh_id = "action_runner_001"
    entity.mesh_name = "ActionRunner"
    entity.mesh_tags = []
    entity.behaviours = []
    return entity


def test_require_flags_block_until_all_present() -> None:
    window = _make_window()
    entity = _make_entity()

    runner = ActionListRunnerBehaviour(
        entity,
        window,
        listen_events=["trigger"],
        require_flags=["flag_a", "flag_b"],
        actions=[{"type": "emit_event", "event_type": "did_run"}],
    )

    assert runner.handle_event("trigger", {}) is False
    runner.update(0.016)
    assert not any(e.event_type == "did_run" for e in window.gameplay_event_bus.peek())

    window.game_state_controller.state.flags["flag_a"] = True
    assert runner.handle_event("trigger", {}) is False
    runner.update(0.016)
    assert not any(e.event_type == "did_run" for e in window.gameplay_event_bus.peek())

    window.game_state_controller.state.flags["flag_b"] = True
    assert runner.handle_event("trigger", {}) is True
    runner.update(0.016)
    assert any(e.event_type == "did_run" for e in window.gameplay_event_bus.peek())


def test_forbid_flags_block_when_present() -> None:
    window = _make_window()
    entity = _make_entity()

    window.game_state_controller.state.flags["blocked"] = True
    runner = ActionListRunnerBehaviour(
        entity,
        window,
        listen_events=["trigger"],
        forbid_flags=["blocked"],
        actions=[{"type": "emit_event", "event_type": "did_run"}],
    )

    assert runner.handle_event("trigger", {}) is False
    runner.update(0.016)
    assert not any(e.event_type == "did_run" for e in window.gameplay_event_bus.peek())

    window.game_state_controller.state.flags["blocked"] = False
    assert runner.handle_event("trigger", {}) is True
    runner.update(0.016)
    assert any(e.event_type == "did_run" for e in window.gameplay_event_bus.peek())


def test_combined_flag_gating() -> None:
    window = _make_window()
    entity = _make_entity()

    runner = ActionListRunnerBehaviour(
        entity,
        window,
        listen_events=["trigger"],
        require_flags=["allow"],
        forbid_flags=["deny"],
        actions=[{"type": "emit_event", "event_type": "did_run"}],
    )

    window.game_state_controller.state.flags["allow"] = False
    window.game_state_controller.state.flags["deny"] = False
    assert runner.handle_event("trigger", {}) is False

    window.game_state_controller.state.flags["allow"] = True
    window.game_state_controller.state.flags["deny"] = True
    assert runner.handle_event("trigger", {}) is False

    window.game_state_controller.state.flags["deny"] = False
    assert runner.handle_event("trigger", {}) is True
    runner.update(0.016)
    assert any(e.event_type == "did_run" for e in window.gameplay_event_bus.peek())


def test_gating_blocks_before_side_effects() -> None:
    window = _make_window()
    entity = _make_entity()

    runner = ActionListRunnerBehaviour(
        entity,
        window,
        listen_events=["trigger"],
        require_flags=["gate"],
        actions=[
            {"type": "set_flag", "flag": "side_effect"},
            {"type": "emit_event", "event_type": "side_effect_event"},
        ],
    )

    assert runner.handle_event("trigger", {}) is False
    runner.update(0.016)
    assert window.game_state_controller.state.flags.get("side_effect") is not True
    assert window.gameplay_event_bus.pending_count() == 0


def test_gating_deterministic_across_runs() -> None:
    def _run_once() -> list[str]:
        window = _make_window()
        entity = _make_entity()
        window.game_state_controller.state.flags["gate"] = True
        runner = ActionListRunnerBehaviour(
            entity,
            window,
            listen_events=["trigger"],
            require_flags=["gate"],
            actions=[{"type": "emit_event", "event_type": "did_run"}],
        )
        assert runner.handle_event("trigger", {}) is True
        runner.update(0.016)
        return [e.event_type for e in window.gameplay_event_bus.peek()]

    assert _run_once() == _run_once()


def test_save_restore_mid_state_does_not_bypass_gating() -> None:
    window = _make_window()
    entity = _make_entity()
    window.game_state_controller.state.flags["gate"] = True

    runner = ActionListRunnerBehaviour(
        entity,
        window,
        listen_events=["trigger"],
        require_flags=["gate"],
        actions=[
            {"type": "emit_event", "event_type": "first"},
            {"type": "delay", "duration": 0.5},
            {"type": "emit_event", "event_type": "second"},
        ],
    )

    assert runner.handle_event("trigger", {}) is True
    runner.update(0.016)
    state = runner.saveable_state()

    new_window = _make_window()
    new_entity = _make_entity()
    new_window.game_state_controller.state.flags["gate"] = False
    restored = ActionListRunnerBehaviour(
        new_entity,
        new_window,
        listen_events=["trigger"],
        require_flags=["gate"],
        actions=[
            {"type": "emit_event", "event_type": "first"},
            {"type": "delay", "duration": 0.5},
            {"type": "emit_event", "event_type": "second"},
        ],
    )
    restored.restore_state(state)

    restored.update(0.6)
    assert any(e.event_type == "second" for e in new_window.gameplay_event_bus.peek())
    assert restored.handle_event("trigger", {}) is False


def test_validate_flag_lists_require_list_type_and_format() -> None:
    config = {
        "listen_events": ["on_trigger"],
        "actions": [{"type": "emit_event", "event_type": "ok"}],
        "require_flags": "not_a_list",
    }
    errors = validate_action_list_runner_config(config, entity_id="entity_1")
    assert any(e.config_path == "require_flags" for e in errors)
    assert any(e.hint for e in errors if e.config_path == "require_flags")

    config = {
        "listen_events": ["on_trigger"],
        "actions": [{"type": "emit_event", "event_type": "ok"}],
        "require_flags": ["Bad Flag"],
    }
    errors = validate_action_list_runner_config(config, entity_id="entity_1")
    assert any(e.config_path == "require_flags[0]" for e in errors)
    assert any("pattern" in e.message for e in errors if e.config_path == "require_flags[0]")


def test_validate_flag_list_duplicates_deterministic() -> None:
    config = {
        "listen_events": ["on_trigger"],
        "actions": [{"type": "emit_event", "event_type": "ok"}],
        "require_flags": ["alpha", "beta", "alpha", "beta"],
    }
    errors = validate_action_list_runner_config(config, entity_id="entity_1")
    dup_errors = [e for e in errors if e.config_path == "require_flags" and "duplicate" in e.message]
    assert dup_errors
    assert dup_errors[0].hint.startswith("Deduplicate to:")
