"""Integration tests for the Puzzle Room 03 content wiring.

Covers:
- Success path: left -> right -> rune within 8s -> solved -> door -> quest complete
- Fail order: right first -> puzzle3_failed reason=order -> reset cutscene -> retry
- Fail timeout: left -> right -> 8s+ -> puzzle3_failed reason=timeout -> reset cutscene -> retry
- Save/restore mid-window: save after right pulled, restore, solve
- Save/restore mid-cutscene: save during reset cutscene, restore, deterministic completion
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.gameplay_event_bus import GameplayEventBus
from engine.game_state_controller import GameState
from engine.quest_runtime.runner import QuestRunner
from engine.state_runtime import flags as state_flags

from tests.cutscene_helpers import advance_cutscene_time


SCENE_PATH = Path("scenes/puzzle_room_03.json")
PREFABS_PATH = Path("assets/prefabs.json")

CUTSCENE_RESET_ORDER = {
    "schema_version": 1,
    "id": "puzzle_room_03_reset_order",
    "commands": [
        {"type": "wait", "duration": 0.5},
        {"type": "emit_event", "event_type": "puzzle3_reset", "payload": {"reason": "order"}},
    ],
}

CUTSCENE_RESET_TIMEOUT = {
    "schema_version": 1,
    "id": "puzzle_room_03_reset_timeout",
    "commands": [
        {"type": "wait", "duration": 0.5},
        {"type": "emit_event", "event_type": "puzzle3_reset", "payload": {"reason": "timeout"}},
    ],
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_prefab(prefab_id: str) -> Dict[str, Any]:
    prefabs = _load_json(PREFABS_PATH)
    for entry in prefabs:
        if entry.get("id") == prefab_id:
            return entry
    raise AssertionError(f"Prefab '{prefab_id}' not found")


def _load_scene_entities() -> List[Dict[str, Any]]:
    payload = _load_json(SCENE_PATH)
    return list(payload.get("entities", []))


def _build_window() -> MagicMock:
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    game_state_ctrl = MagicMock()
    game_state_ctrl.state = GameState()
    window.game_state_controller = game_state_ctrl
    window.get_flag = lambda name, default=False: state_flags.get_flag(
        game_state_ctrl.state, name, default
    )
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    return window


def _build_action_runners(window: MagicMock) -> List[Any]:
    from engine.behaviours.action_list_runner import ActionListRunnerBehaviour

    runners: List[Any] = []
    for entity in _load_scene_entities():
        if entity.get("prefab_id") != "puzzle_controller":
            continue
        config = (entity.get("behaviour_config") or {}).get("ActionListRunner", {})
        runner_entity = MagicMock()
        runner_entity.mesh_id = entity.get("id", "")
        runner_entity.mesh_name = entity.get("name", "")
        runner_entity.mesh_tags = []
        runner_entity.behaviours = []
        runner = ActionListRunnerBehaviour(runner_entity, window, **config)
        runners.append(runner)
    return runners


def _build_timer(window: MagicMock):
    from engine.behaviours.timer import TimerBehaviour

    prefab = _load_prefab("puzzle3_timer")
    config = prefab.get("entity", {}).get("behaviour_config", {}).get("Timer", {})

    timer_entity = MagicMock()
    timer_entity.mesh_id = "puzzle_room_03_timer"
    timer_entity.mesh_name = "Puzzle3Timer"
    timer_entity.mesh_tags = []

    timer = TimerBehaviour(timer_entity, window, **config)
    timer_entity.behaviours = [timer]

    return timer_entity, timer


def _build_cutscene_runner(window: MagicMock, script: Dict[str, Any]):
    from engine.cutscene_runtime.runner import CutsceneRunner

    class _Flags:
        def __init__(self, state):
            self._state = state

        def get_flag(self, name: str, default: bool = False) -> bool:
            return state_flags.get_flag(self._state, name, default)

        def set_flag(self, name: str, value: bool) -> None:
            state_flags.set_flag(self._state, name, bool(value))

    flags = _Flags(window.game_state_controller.state)
    runner = CutsceneRunner(
        event_bus=window.gameplay_event_bus,
        flag_provider=flags,
        flag_setter=flags,
    )
    errors = runner.load_script_from_data(dict(script))
    assert not errors, f"Cutscene load errors: {errors}"
    return runner


def _build_trigger(window: MagicMock, prefab_id: str, mesh_id: str, mesh_name: str, x: float, y: float):
    from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

    prefab = _load_prefab(prefab_id)
    cfg = prefab.get("entity", {}).get("behaviour_config", {}).get("TriggerVolume", {})

    entity = MagicMock()
    entity.mesh_id = mesh_id
    entity.mesh_name = mesh_name
    entity.center_x = float(x)
    entity.center_y = float(y)
    entity.width = float(cfg.get("width", 32))
    entity.height = float(cfg.get("height", 32))

    return TriggerVolumeBehaviour(entity, window, **cfg)


def _drain_and_route(
    window: MagicMock,
    runners: List[Any],
    cutscene_order=None,
    cutscene_timeout=None,
) -> List[Any]:
    events = window.gameplay_event_bus.drain()
    if not events:
        return []
    for event in events:
        for runner in runners:
            if event.event_type in runner.listen_events:
                runner.handle_event(event.event_type, event.payload)
        # Start the appropriate reset cutscene on puzzle3_failed
        if event.event_type == "puzzle3_failed":
            reason = event.payload.get("reason", "")
            if reason == "order" and cutscene_order and not cutscene_order.is_running:
                cutscene_order.start()
            elif reason == "timeout" and cutscene_timeout and not cutscene_timeout.is_running:
                cutscene_timeout.start()
    for runner in runners:
        runner.update(0.0)
    return events


def _drain_until_empty(
    window: MagicMock,
    runners: List[Any],
    cutscene_order=None,
    cutscene_timeout=None,
) -> List[Any]:
    collected: List[Any] = []
    for _ in range(12):
        batch = _drain_and_route(
            window, runners,
            cutscene_order=cutscene_order,
            cutscene_timeout=cutscene_timeout,
        )
        if not batch:
            break
        collected.extend(batch)
    return collected


def _advance_time(
    window: MagicMock,
    runners: List[Any],
    timers: List[Any],
    cutscene_order,
    cutscene_timeout,
    dt: float,
) -> List[Any]:
    for timer in timers:
        timer.update(dt)
    for cs in (cutscene_order, cutscene_timeout):
        if cs and cs.is_running:
            advance_cutscene_time(cs, dt)
    for runner in runners:
        runner.update(dt)
    return _drain_until_empty(
        window, runners,
        cutscene_order=cutscene_order,
        cutscene_timeout=cutscene_timeout,
    )


def _step_on_trigger(trigger: Any, player: Any, *, off_pos: tuple[float, float] = (0.0, 0.0)) -> None:
    player.center_x = float(trigger.entity.center_x)
    player.center_y = float(trigger.entity.center_y)
    trigger.update(0.016)
    player.center_x = float(off_pos[0])
    player.center_y = float(off_pos[1])
    trigger.update(0.016)


# =============================================================================
# Helpers for building a full room context
# =============================================================================

def _setup_room():
    """Build the full room fixture and return all components as a dict."""
    window = _build_window()
    runners = _build_action_runners(window)
    timer_entity, timer = _build_timer(window)
    cs_order = _build_cutscene_runner(window, CUTSCENE_RESET_ORDER)
    cs_timeout = _build_cutscene_runner(window, CUTSCENE_RESET_TIMEOUT)

    player = MagicMock()
    player.mesh_id = "player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 0.0
    player.center_y = 0.0

    window.scene_controller.all_sprites = [player, timer_entity]

    entry_trigger = _build_trigger(
        window, "puzzle_room3_entry_trigger",
        "puzzle_room_03_entry_trigger", "RoomEntryTrigger03",
        256.0, 192.0,
    )
    rune_center = _build_trigger(
        window, "puzzle3_rune_center",
        "puzzle_room_03_rune_center", "RuneCenter03",
        256.0, 256.0,
    )

    return {
        "window": window,
        "runners": runners,
        "timer_entity": timer_entity,
        "timer": timer,
        "cs_order": cs_order,
        "cs_timeout": cs_timeout,
        "player": player,
        "entry_trigger": entry_trigger,
        "rune_center": rune_center,
    }


def _enter_room(ctx: Dict[str, Any]) -> List[Any]:
    """Step on entry trigger and drain events."""
    _step_on_trigger(ctx["entry_trigger"], ctx["player"])
    return _drain_until_empty(
        ctx["window"], ctx["runners"],
        cutscene_order=ctx["cs_order"],
        cutscene_timeout=ctx["cs_timeout"],
    )


def _pull_lever(ctx: Dict[str, Any], event_type: str) -> List[Any]:
    """Emit a lever pull event and drain."""
    ctx["window"].gameplay_event_bus.emit(event_type, interactor="player")
    return _drain_until_empty(
        ctx["window"], ctx["runners"],
        cutscene_order=ctx["cs_order"],
        cutscene_timeout=ctx["cs_timeout"],
    )


def _advance(ctx: Dict[str, Any], dt: float) -> List[Any]:
    return _advance_time(
        ctx["window"], ctx["runners"], [ctx["timer"]],
        ctx["cs_order"], ctx["cs_timeout"], dt,
    )


def _get_flag(ctx: Dict[str, Any], flag: str) -> bool:
    return ctx["window"].game_state_controller.state.flags.get(flag) is True


# =============================================================================
# Tests
# =============================================================================

class TestPuzzleRoom03Integration:
    # -----------------------------------------------------------------
    # SUCCESS PATH
    # -----------------------------------------------------------------
    def test_success_path(self) -> None:
        """Left -> Right -> rune within 8s -> solved -> door -> quest complete."""
        ctx = _setup_room()
        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        assert quests.start_quest("puzzle_room_03") is True

        # Enter room -> step0 completes
        events = _enter_room(ctx)
        quests.process_events(events)
        state = quests.get_quest_state("puzzle_room_03")
        assert state is not None
        assert state.current_stage == "step1"
        assert _get_flag(ctx, "puzzle3.locked")

        # Pull left lever
        events = _pull_lever(ctx, "lever_left_pulled")
        quests.process_events(events)
        assert _get_flag(ctx, "puzzle3.left_pulled")
        state = quests.get_quest_state("puzzle_room_03")
        assert state is not None
        assert state.current_stage == "step2"

        # Pull right lever -> timer starts, window opens
        events = _pull_lever(ctx, "lever_right_pulled")
        quests.process_events(events)
        assert _get_flag(ctx, "puzzle3.right_pulled")
        assert _get_flag(ctx, "puzzle3.window_active")
        assert any(e.event_type == "puzzle3_window_started" for e in events)

        # Step on rune within 8s
        _step_on_trigger(ctx["rune_center"], ctx["player"])
        events = _drain_until_empty(
            ctx["window"], ctx["runners"],
            cutscene_order=ctx["cs_order"],
            cutscene_timeout=ctx["cs_timeout"],
        )
        emitted = quests.process_events(events)

        assert _get_flag(ctx, "puzzle3.solved")
        assert not _get_flag(ctx, "puzzle3.window_active")
        assert not _get_flag(ctx, "puzzle3.locked")
        assert any(e.event_type == "puzzle3_solved" for e in events)
        assert any(e.event_type == "quest_room3_complete" for e in emitted)

        state = quests.get_quest_state("puzzle_room_03")
        assert state is not None
        assert state.status == "completed"

        # Door gate is now satisfied
        door_prefab = _load_prefab("puzzle3_exit_door")
        door_entity = MagicMock()
        door_entity.mesh_entity_data = door_prefab.get("entity", {})
        from engine.scene_entity_gating import runtime_entity_passes_flag_gates
        assert runtime_entity_passes_flag_gates(
            door_entity, get_flag=ctx["window"].get_flag
        ) is True

    # -----------------------------------------------------------------
    # FAIL: WRONG ORDER
    # -----------------------------------------------------------------
    def test_fail_wrong_order_then_solve(self) -> None:
        """Right first -> fail(order) -> reset cutscene -> retry -> solve."""
        ctx = _setup_room()

        _enter_room(ctx)
        assert _get_flag(ctx, "puzzle3.locked")

        # Pull right first (wrong order)
        events = _pull_lever(ctx, "lever_right_pulled")
        fail_events = [e for e in events if e.event_type == "puzzle3_failed"]
        assert fail_events
        assert fail_events[-1].payload.get("reason") == "order"
        assert ctx["cs_order"].is_running is True

        # Let reset cutscene complete
        _advance(ctx, 0.6)
        reset_events = _drain_until_empty(
            ctx["window"], ctx["runners"],
            cutscene_order=ctx["cs_order"],
            cutscene_timeout=ctx["cs_timeout"],
        )
        # All flags should be cleared back to initial state
        assert not _get_flag(ctx, "puzzle3.left_pulled")
        assert not _get_flag(ctx, "puzzle3.right_pulled")
        assert not _get_flag(ctx, "puzzle3.window_active")
        assert _get_flag(ctx, "puzzle3.locked")

        # Now solve correctly: left -> right -> rune
        _pull_lever(ctx, "lever_left_pulled")
        assert _get_flag(ctx, "puzzle3.left_pulled")

        _pull_lever(ctx, "lever_right_pulled")
        assert _get_flag(ctx, "puzzle3.right_pulled")
        assert _get_flag(ctx, "puzzle3.window_active")

        _step_on_trigger(ctx["rune_center"], ctx["player"])
        events = _drain_until_empty(
            ctx["window"], ctx["runners"],
            cutscene_order=ctx["cs_order"],
            cutscene_timeout=ctx["cs_timeout"],
        )
        assert _get_flag(ctx, "puzzle3.solved")
        assert any(e.event_type == "puzzle3_solved" for e in events)

    # -----------------------------------------------------------------
    # FAIL: TIMEOUT
    # -----------------------------------------------------------------
    def test_fail_timeout_then_solve(self) -> None:
        """Left -> Right -> timeout -> fail(timeout) -> reset -> retry -> solve."""
        ctx = _setup_room()

        _enter_room(ctx)

        # Correct lever order
        _pull_lever(ctx, "lever_left_pulled")
        _pull_lever(ctx, "lever_right_pulled")
        assert _get_flag(ctx, "puzzle3.window_active")

        # Advance past 8s timeout
        events = _advance(ctx, 8.5)
        assert any(e.event_type == "puzzle3_timeout" for e in events)
        timeout_fail = [e for e in events if e.event_type == "puzzle3_failed"]
        assert timeout_fail
        assert timeout_fail[-1].payload.get("reason") == "timeout"
        assert ctx["cs_timeout"].is_running is True

        # Let reset cutscene complete
        _advance(ctx, 0.6)
        _drain_until_empty(
            ctx["window"], ctx["runners"],
            cutscene_order=ctx["cs_order"],
            cutscene_timeout=ctx["cs_timeout"],
        )
        assert not _get_flag(ctx, "puzzle3.left_pulled")
        assert not _get_flag(ctx, "puzzle3.right_pulled")
        assert not _get_flag(ctx, "puzzle3.window_active")
        assert _get_flag(ctx, "puzzle3.locked")

        # Solve correctly
        _pull_lever(ctx, "lever_left_pulled")
        _pull_lever(ctx, "lever_right_pulled")
        _step_on_trigger(ctx["rune_center"], ctx["player"])
        events = _drain_until_empty(
            ctx["window"], ctx["runners"],
            cutscene_order=ctx["cs_order"],
            cutscene_timeout=ctx["cs_timeout"],
        )
        assert _get_flag(ctx, "puzzle3.solved")
        assert any(e.event_type == "puzzle3_solved" for e in events)

    # -----------------------------------------------------------------
    # SAVE / RESTORE: MID-WINDOW
    # -----------------------------------------------------------------
    def test_save_restore_mid_window(self) -> None:
        """Save after right pulled (mid-timer), restore, then solve."""
        ctx = _setup_room()

        _enter_room(ctx)
        _pull_lever(ctx, "lever_left_pulled")
        _pull_lever(ctx, "lever_right_pulled")
        assert _get_flag(ctx, "puzzle3.window_active")

        # Advance timer 3 seconds before saving
        _advance(ctx, 3.0)

        saved_flags = ctx["window"].game_state_controller.state.snapshot()
        saved_bus = ctx["window"].gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in ctx["runners"]}
        saved_timer = ctx["timer"].saveable_state()
        saved_cs_order = ctx["cs_order"].saveable_state()
        saved_cs_timeout = ctx["cs_timeout"].saveable_state()

        # Restore into a fresh window
        new_ctx = _setup_room()
        new_ctx["window"].game_state_controller.state.restore(saved_flags)
        new_ctx["window"].gameplay_event_bus.restore_state(saved_bus)
        for runner in new_ctx["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)
        new_ctx["timer"].restore_state(saved_timer)
        new_ctx["cs_order"].restore_state(saved_cs_order)
        new_ctx["cs_timeout"].restore_state(saved_cs_timeout)

        # Verify state preserved
        assert _get_flag(new_ctx, "puzzle3.window_active")
        assert _get_flag(new_ctx, "puzzle3.left_pulled")
        assert _get_flag(new_ctx, "puzzle3.right_pulled")

        # Solve after restore by stepping on rune within remaining time
        _step_on_trigger(new_ctx["rune_center"], new_ctx["player"])
        events = _drain_until_empty(
            new_ctx["window"], new_ctx["runners"],
            cutscene_order=new_ctx["cs_order"],
            cutscene_timeout=new_ctx["cs_timeout"],
        )
        assert _get_flag(new_ctx, "puzzle3.solved")
        assert any(e.event_type == "puzzle3_solved" for e in events)

    # -----------------------------------------------------------------
    # SAVE / RESTORE: MID-CUTSCENE
    # -----------------------------------------------------------------
    def test_save_restore_mid_reset_cutscene(self) -> None:
        """Save during reset cutscene, restore, cutscene completes deterministically."""
        ctx = _setup_room()

        _enter_room(ctx)

        # Trigger wrong-order fail
        _pull_lever(ctx, "lever_right_pulled")
        assert ctx["cs_order"].is_running is True

        # Advance partway through the reset cutscene (0.2s of 0.5s wait)
        _advance(ctx, 0.2)
        assert ctx["cs_order"].is_running is True

        saved_flags = ctx["window"].game_state_controller.state.snapshot()
        saved_bus = ctx["window"].gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in ctx["runners"]}
        saved_timer = ctx["timer"].saveable_state()
        saved_cs_order = ctx["cs_order"].saveable_state()
        saved_cs_timeout = ctx["cs_timeout"].saveable_state()

        # Restore into a fresh window
        new_ctx = _setup_room()
        new_ctx["window"].game_state_controller.state.restore(saved_flags)
        new_ctx["window"].gameplay_event_bus.restore_state(saved_bus)
        for runner in new_ctx["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)
        new_ctx["timer"].restore_state(saved_timer)
        new_ctx["cs_order"].restore_state(saved_cs_order)
        new_ctx["cs_timeout"].restore_state(saved_cs_timeout)

        # Complete the cutscene after restore (remaining ~0.3s)
        _advance(new_ctx, 0.4)
        _drain_until_empty(
            new_ctx["window"], new_ctx["runners"],
            cutscene_order=new_ctx["cs_order"],
            cutscene_timeout=new_ctx["cs_timeout"],
        )

        # Flags should be reset
        assert not _get_flag(new_ctx, "puzzle3.left_pulled")
        assert not _get_flag(new_ctx, "puzzle3.right_pulled")
        assert not _get_flag(new_ctx, "puzzle3.window_active")
        assert _get_flag(new_ctx, "puzzle3.locked")

        # Should be able to solve after restored reset completes
        _pull_lever(new_ctx, "lever_left_pulled")
        _pull_lever(new_ctx, "lever_right_pulled")
        _step_on_trigger(new_ctx["rune_center"], new_ctx["player"])
        events = _drain_until_empty(
            new_ctx["window"], new_ctx["runners"],
            cutscene_order=new_ctx["cs_order"],
            cutscene_timeout=new_ctx["cs_timeout"],
        )
        assert _get_flag(new_ctx, "puzzle3.solved")
        assert any(e.event_type == "puzzle3_solved" for e in events)
