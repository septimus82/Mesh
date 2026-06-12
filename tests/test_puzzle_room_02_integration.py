"""Integration tests for the Puzzle Room 02 content wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.game_state_controller import GameState
from engine.gameplay_event_bus import GameplayEventBus
from engine.quest_runtime.runner import QuestRunner
from engine.state_runtime import flags as state_flags
from tests.cutscene_helpers import advance_cutscene_time

SCENE_PATH = Path("scenes/puzzle_room_02.json")
PREFABS_PATH = Path("assets/prefabs.json")
CUTSCENE_ID = "puzzle_room_02_reset"


CUTSCENE_SCRIPT = {
    "schema_version": 1,
    "id": CUTSCENE_ID,
    "commands": [
        {"type": "wait", "duration": 0.5},
        {"type": "emit_event", "event_type": "puzzle2_reset", "payload": {"reason": "cutscene"}},
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
    window.get_flag = lambda name, default=False: state_flags.get_flag(game_state_ctrl.state, name, default)
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


def _build_hint_plaque(window: MagicMock):
    from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour

    prefab = _load_prefab("puzzle2_hint_plaque")
    config = prefab.get("entity", {}).get("behaviour_config", {}).get("DialogueRunner", {})

    plaque = MagicMock()
    plaque.mesh_id = "puzzle_room_02_hint_plaque"
    plaque.mesh_name = "HintPlaque02"
    plaque.mesh_tags = []

    runner = DialogueRunnerBehaviour(plaque, window, **config)
    plaque.behaviours = [runner]

    return plaque, runner


def _build_timer(window: MagicMock):
    from engine.behaviours.timer import TimerBehaviour

    prefab = _load_prefab("puzzle2_timer")
    config = prefab.get("entity", {}).get("behaviour_config", {}).get("Timer", {})

    timer_entity = MagicMock()
    timer_entity.mesh_id = "puzzle_room_02_timer"
    timer_entity.mesh_name = "Puzzle2Timer"
    timer_entity.mesh_tags = []

    timer = TimerBehaviour(timer_entity, window, **config)
    timer_entity.behaviours = [timer]

    return timer_entity, timer


def _build_cutscene_runner(window: MagicMock):
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
    errors = runner.load_script_from_data(dict(CUTSCENE_SCRIPT))
    assert not errors
    return runner


def _build_rune_trigger(window: MagicMock, prefab_id: str, mesh_id: str, mesh_name: str, x: float, y: float):
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


def _drain_and_route(window: MagicMock, runners: List[Any], cutscene_runner=None) -> List[Any]:
    events = window.gameplay_event_bus.drain()
    if not events:
        return []
    for event in events:
        for runner in runners:
            if event.event_type in runner.listen_events:
                runner.handle_event(event.event_type, event.payload)
        if cutscene_runner and event.event_type == "puzzle2_failed" and not cutscene_runner.is_running:
            cutscene_runner.start()
    for runner in runners:
        runner.update(0.0)
    return events


def _drain_until_empty(window: MagicMock, runners: List[Any], cutscene_runner=None) -> List[Any]:
    collected: List[Any] = []
    for _ in range(12):
        batch = _drain_and_route(window, runners, cutscene_runner=cutscene_runner)
        if not batch:
            break
        collected.extend(batch)
    return collected


def _advance_time(window: MagicMock, runners: List[Any], timers: List[Any], cutscene_runner, dt: float) -> List[Any]:
    for timer in timers:
        timer.update(dt)
    if cutscene_runner and cutscene_runner.is_running:
        advance_cutscene_time(cutscene_runner, dt)
    for runner in runners:
        runner.update(dt)
    return _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)


def _step_on_trigger(trigger: Any, player: Any, *, off_pos: tuple[float, float] = (0.0, 0.0)) -> None:
    player.center_x = float(trigger.entity.center_x)
    player.center_y = float(trigger.entity.center_y)
    trigger.update(0.016)
    player.center_x = float(off_pos[0])
    player.center_y = float(off_pos[1])
    trigger.update(0.016)


class TestPuzzleRoom02Integration:
    def test_puzzle_room_02_success_path(self) -> None:
        window = _build_window()
        runners = _build_action_runners(window)

        hint_plaque, _dialogue_runner = _build_hint_plaque(window)
        timer_entity, timer = _build_timer(window)
        cutscene_runner = _build_cutscene_runner(window)

        player = MagicMock()
        player.mesh_id = "player"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 0.0
        player.center_y = 0.0

        window.scene_controller.all_sprites = [player, hint_plaque, timer_entity]

        entry_trigger = _build_rune_trigger(
            window,
            "puzzle_room2_entry_trigger",
            "puzzle_room_02_entry_trigger",
            "RoomEntryTrigger02",
            256.0,
            192.0,
        )

        rune_b = _build_rune_trigger(window, "puzzle2_rune_b", "puzzle_room_02_rune_b", "RuneB02", 200.0, 180.0)
        rune_a = _build_rune_trigger(window, "puzzle2_rune_a", "puzzle_room_02_rune_a", "RuneA02", 256.0, 240.0)
        rune_c = _build_rune_trigger(window, "puzzle2_rune_c", "puzzle_room_02_rune_c", "RuneC02", 312.0, 180.0)

        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        assert quests.start_quest("puzzle_room_02") is True

        # Enter room -> step0 completes, timer starts
        _step_on_trigger(entry_trigger, player)
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        quests.process_events(events)

        state = quests.get_quest_state("puzzle_room_02")
        assert state is not None
        assert state.current_stage == "step1"
        assert window.game_state_controller.state.flags.get("puzzle2.running") is True

        # Interact with hint plaque -> dialogue_completed -> hint2_read
        window.gameplay_event_bus.emit("hint2_plaque_interact", interactor="player")
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        quests.process_events(events)

        state = quests.get_quest_state("puzzle_room_02")
        assert state is not None
        assert state.current_stage == "step2"

        # Correct sequence: B -> A -> C
        _step_on_trigger(rune_b, player)
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        quests.process_events(events)

        _step_on_trigger(rune_a, player)
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        quests.process_events(events)

        _step_on_trigger(rune_c, player)
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        emitted = quests.process_events(events)

        assert window.game_state_controller.state.flags.get("puzzle2.solved") is True
        assert window.game_state_controller.state.flags.get("puzzle2.seq1") is False
        assert window.game_state_controller.state.flags.get("puzzle2.seq2") is False
        assert any(e.event_type == "puzzle2_solved" for e in events)
        assert any(e.event_type == "quest_room2_complete" for e in emitted)

        state = quests.get_quest_state("puzzle_room_02")
        assert state is not None
        assert state.status == "completed"

        # Door gate is now satisfied
        door_prefab = _load_prefab("puzzle2_exit_door")
        door_entity = MagicMock()
        door_entity.mesh_entity_data = door_prefab.get("entity", {})
        from engine.scene_entity_gating import runtime_entity_passes_flag_gates
        assert runtime_entity_passes_flag_gates(door_entity, get_flag=window.get_flag) is True

    def test_puzzle_room_02_timeout_and_spotted_failures(self) -> None:
        window = _build_window()
        runners = _build_action_runners(window)
        timer_entity, timer = _build_timer(window)
        cutscene_runner = _build_cutscene_runner(window)

        player = MagicMock()
        player.mesh_id = "player"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 0.0
        player.center_y = 0.0

        window.scene_controller.all_sprites = [player, timer_entity]

        entry_trigger = _build_rune_trigger(
            window,
            "puzzle_room2_entry_trigger",
            "puzzle_room_02_entry_trigger",
            "RoomEntryTrigger02",
            256.0,
            192.0,
        )
        sentinel_vision = _build_rune_trigger(
            window,
            "puzzle2_sentinel_vision",
            "puzzle_room_02_sentinel_vision",
            "SentinelVision02",
            256.0,
            112.0,
        )
        rune_b = _build_rune_trigger(window, "puzzle2_rune_b", "puzzle_room_02_rune_b", "RuneB02", 200.0, 180.0)

        # Timeout failure
        _step_on_trigger(entry_trigger, player)
        _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)

        events = _advance_time(window, runners, [timer], cutscene_runner, 20.5)
        assert any(e.event_type == "puzzle2_timeout" for e in events)
        timeout_events = [e for e in events if e.event_type == "puzzle2_failed"]
        assert timeout_events
        assert timeout_events[-1].payload.get("reason") == "timeout"
        assert cutscene_runner.is_running is True

        # Let cutscene emit puzzle2_reset — advance_cutscene_time handles priming
        reset_events = _advance_time(window, runners, [timer], cutscene_runner, 0.6)
        assert any(e.event_type == "puzzle2_reset" for e in reset_events)
        assert window.game_state_controller.state.flags.get("puzzle2.restart_pending") is False
        assert window.game_state_controller.state.flags.get("puzzle2.locked") is False
        assert window.game_state_controller.state.flags.get("puzzle2.running") is True

        # Spotted failure mid-sequence
        _step_on_trigger(rune_b, player)
        _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        assert window.game_state_controller.state.flags.get("puzzle2.seq1") is True

        _step_on_trigger(sentinel_vision, player)
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        spotted_events = [e for e in events if e.event_type == "puzzle2_failed"]
        assert spotted_events
        assert spotted_events[-1].payload.get("reason") == "spotted"

        _advance_time(window, runners, [timer], cutscene_runner, 0.6)
        assert window.game_state_controller.state.flags.get("puzzle2.seq1") is False
        assert window.game_state_controller.state.flags.get("puzzle2.seq2") is False

    def test_save_restore_mid_sequence(self) -> None:
        window = _build_window()
        runners = _build_action_runners(window)
        timer_entity, timer = _build_timer(window)
        cutscene_runner = _build_cutscene_runner(window)

        player = MagicMock()
        player.mesh_id = "player"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 0.0
        player.center_y = 0.0

        window.scene_controller.all_sprites = [player, timer_entity]

        entry_trigger = _build_rune_trigger(
            window,
            "puzzle_room2_entry_trigger",
            "puzzle_room_02_entry_trigger",
            "RoomEntryTrigger02",
            256.0,
            192.0,
        )
        rune_b = _build_rune_trigger(window, "puzzle2_rune_b", "puzzle_room_02_rune_b", "RuneB02", 200.0, 180.0)
        rune_a = _build_rune_trigger(window, "puzzle2_rune_a", "puzzle_room_02_rune_a", "RuneA02", 256.0, 240.0)
        rune_c = _build_rune_trigger(window, "puzzle2_rune_c", "puzzle_room_02_rune_c", "RuneC02", 312.0, 180.0)

        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        assert quests.start_quest("puzzle_room_02") is True

        _step_on_trigger(entry_trigger, player)
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        quests.process_events(events)

        # Emit hint2_read directly so quest advances past step1 before save
        # (skipping full dialogue flow — this test focuses on save/restore of
        # mid-sequence puzzle state, not the hint dialogue interaction)
        window.gameplay_event_bus.emit("hint2_read", hint_id="puzzle2_hint_plaque")
        events = _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        quests.process_events(events)

        _step_on_trigger(rune_b, player)
        _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        assert window.game_state_controller.state.flags.get("puzzle2.seq1") is True

        _advance_time(window, runners, [timer], cutscene_runner, 5.0)

        saved_flags = window.game_state_controller.state.snapshot()
        saved_bus = window.gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in runners}
        saved_timer = timer.saveable_state()
        saved_cutscene = cutscene_runner.saveable_state()
        saved_quests = quests.get_state()

        # Restore into a fresh window
        new_window = _build_window()
        new_runners = _build_action_runners(new_window)
        new_timer_entity, new_timer = _build_timer(new_window)
        new_cutscene_runner = _build_cutscene_runner(new_window)

        new_window.scene_controller.all_sprites = [player, new_timer_entity]

        new_window.game_state_controller.state.restore(saved_flags)
        new_window.gameplay_event_bus.restore_state(saved_bus)

        for runner in new_runners:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)

        new_timer.restore_state(saved_timer)
        new_cutscene_runner.restore_state(saved_cutscene)

        new_quests = QuestRunner()
        new_quests.load_definitions(Path("assets/data/quests.json"))
        new_quests.apply_state(saved_quests)

        # Continue sequence after restore
        new_window.gameplay_event_bus.emit("puzzle2_rune_a", entity="player")
        events = _drain_until_empty(new_window, new_runners, cutscene_runner=new_cutscene_runner)
        new_quests.process_events(events)

        new_window.gameplay_event_bus.emit("puzzle2_rune_c", entity="player")
        events = _drain_until_empty(new_window, new_runners, cutscene_runner=new_cutscene_runner)
        emitted = new_quests.process_events(events)

        assert new_window.game_state_controller.state.flags.get("puzzle2.solved") is True
        assert any(e.event_type == "quest_room2_complete" for e in emitted)

    def test_save_restore_mid_cutscene(self) -> None:
        window = _build_window()
        runners = _build_action_runners(window)
        timer_entity, timer = _build_timer(window)
        cutscene_runner = _build_cutscene_runner(window)

        player = MagicMock()
        player.mesh_id = "player"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 0.0
        player.center_y = 0.0

        window.scene_controller.all_sprites = [player, timer_entity]

        entry_trigger = _build_rune_trigger(
            window,
            "puzzle_room2_entry_trigger",
            "puzzle_room_02_entry_trigger",
            "RoomEntryTrigger02",
            256.0,
            192.0,
        )
        sentinel_vision = _build_rune_trigger(
            window,
            "puzzle2_sentinel_vision",
            "puzzle_room_02_sentinel_vision",
            "SentinelVision02",
            256.0,
            112.0,
        )

        _step_on_trigger(entry_trigger, player)
        _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)

        _step_on_trigger(sentinel_vision, player)
        _drain_until_empty(window, runners, cutscene_runner=cutscene_runner)
        assert cutscene_runner.is_running is True

        # advance_cutscene_time (inside _advance_time) handles priming
        _advance_time(window, runners, [timer], cutscene_runner, 0.2)
        assert cutscene_runner.is_running is True

        saved_flags = window.game_state_controller.state.snapshot()
        saved_bus = window.gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in runners}
        saved_timer = timer.saveable_state()
        saved_cutscene = cutscene_runner.saveable_state()

        # Restore into a fresh window
        new_window = _build_window()
        new_runners = _build_action_runners(new_window)
        new_timer_entity, new_timer = _build_timer(new_window)
        new_cutscene_runner = _build_cutscene_runner(new_window)

        new_window.scene_controller.all_sprites = [player, new_timer_entity]

        new_window.game_state_controller.state.restore(saved_flags)
        new_window.gameplay_event_bus.restore_state(saved_bus)

        for runner in new_runners:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)

        new_timer.restore_state(saved_timer)
        new_cutscene_runner.restore_state(saved_cutscene)

        # Continue cutscene after restore — wait_remaining was 0.3s at save time
        _advance_time(new_window, new_runners, [new_timer], new_cutscene_runner, 0.4)
        # Prime the reset_after_fail ActionListRunner reaction
        _advance_time(new_window, new_runners, [new_timer], new_cutscene_runner, 0.0)
        assert new_window.game_state_controller.state.flags.get("puzzle2.restart_pending") is False
        assert new_window.game_state_controller.state.flags.get("puzzle2.running") is True
