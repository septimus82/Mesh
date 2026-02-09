"""Integration tests for the Puzzle Room 01 content wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.gameplay_event_bus import GameplayEventBus
from engine.game_state_controller import GameState
from engine.quest_runtime.runner import QuestRunner
from engine.state_runtime import flags as state_flags


SCENE_PATH = Path("scenes/puzzle_room_01.json")
PREFABS_PATH = Path("assets/prefabs.json")


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

    prefab = _load_prefab("puzzle_hint_plaque")
    config = prefab.get("entity", {}).get("behaviour_config", {}).get("DialogueRunner", {})

    plaque = MagicMock()
    plaque.mesh_id = "puzzle_room_01_hint_plaque"
    plaque.mesh_name = "HintPlaque"
    plaque.mesh_tags = []

    runner = DialogueRunnerBehaviour(plaque, window, **config)
    plaque.behaviours = [runner]

    return plaque, runner


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


def _drain_and_route(window: MagicMock, runners: List[Any], dt: float = 0.0) -> List[Any]:
    events = window.gameplay_event_bus.drain()
    if not events:
        return []
    for event in events:
        for runner in runners:
            if event.event_type in runner.listen_events:
                runner.handle_event(event.event_type, event.payload)
    for runner in runners:
        runner.update(dt)
    return events


def _drain_until_empty(window: MagicMock, runners: List[Any], dt: float = 0.0) -> List[Any]:
    collected: List[Any] = []
    for _ in range(8):
        batch = _drain_and_route(window, runners, dt=dt)
        if not batch:
            break
        collected.extend(batch)
    return collected


def _advance_time(window: MagicMock, runners: List[Any], dt: float) -> None:
    for runner in runners:
        runner.update(dt)

def _step_on_trigger(trigger: Any, player: Any, *, off_pos: tuple[float, float] = (0.0, 0.0)) -> None:
    player.center_x = float(trigger.entity.center_x)
    player.center_y = float(trigger.entity.center_y)
    trigger.update(0.016)
    player.center_x = float(off_pos[0])
    player.center_y = float(off_pos[1])
    trigger.update(0.016)


class TestPuzzleRoomSequenceIntegration:
    def test_puzzle_room_sequence_progression(self) -> None:
        window = _build_window()
        runners = _build_action_runners(window)

        hint_plaque, _dialogue_runner = _build_hint_plaque(window)

        player = MagicMock()
        player.mesh_id = "player"
        player.mesh_name = "Player"
        player.mesh_tags = ["player"]
        player.center_x = 0.0
        player.center_y = 0.0

        window.scene_controller.all_sprites = [player, hint_plaque]

        entry_trigger = _build_rune_trigger(
            window,
            "puzzle_room_entry_trigger",
            "puzzle_room_01_entry_trigger",
            "RoomEntryTrigger",
            256.0,
            192.0,
        )

        rune_a = _build_rune_trigger(window, "puzzle_rune_a", "puzzle_room_01_rune_a", "RuneA", 200.0, 180.0)
        rune_b = _build_rune_trigger(window, "puzzle_rune_b", "puzzle_room_01_rune_b", "RuneB", 312.0, 180.0)
        rune_c = _build_rune_trigger(window, "puzzle_rune_c", "puzzle_room_01_rune_c", "RuneC", 256.0, 240.0)

        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        assert quests.start_quest("puzzle_room_01") is True

        # Enter room -> step0 completes
        _step_on_trigger(entry_trigger, player)
        events = _drain_until_empty(window, runners)
        quests.process_events(events)

        state = quests.get_quest_state("puzzle_room_01")
        assert state is not None
        assert state.current_stage == "step1"

        # Interact with hint plaque -> dialogue_completed -> hint_read
        window.gameplay_event_bus.emit("hint_plaque_interact", interactor="player")
        events = _drain_until_empty(window, runners)
        quests.process_events(events)

        state = quests.get_quest_state("puzzle_room_01")
        assert state is not None
        assert state.current_stage == "step2"

        # Wrong sequence: A then B -> reset
        _step_on_trigger(rune_a, player)
        events = _drain_until_empty(window, runners)
        quests.process_events(events)

        assert window.game_state_controller.state.flags.get("puzzle.seq1") is True

        _step_on_trigger(rune_b, player)
        events = _drain_until_empty(window, runners)
        quests.process_events(events)

        event_types = [e.event_type for e in events]
        assert "puzzle_wrong" in event_types
        assert window.game_state_controller.state.flags.get("puzzle.seq1") is False
        assert window.game_state_controller.state.flags.get("puzzle.seq2") is False
        assert window.game_state_controller.state.flags.get("puzzle.locked") is True

        _advance_time(window, runners, 0.3)
        reset_events = _drain_until_empty(window, runners)
        assert any(e.event_type == "puzzle_reset" for e in reset_events)
        assert window.game_state_controller.state.flags.get("puzzle.locked") is False

        # Correct sequence: A -> C -> B
        _step_on_trigger(rune_a, player)
        events = _drain_until_empty(window, runners)
        quests.process_events(events)

        _step_on_trigger(rune_c, player)
        events = _drain_until_empty(window, runners)
        quests.process_events(events)

        _step_on_trigger(rune_b, player)
        events = _drain_until_empty(window, runners)
        emitted = quests.process_events(events)

        assert window.game_state_controller.state.flags.get("puzzle.solved") is True
        assert any(e.event_type == "puzzle_solved" for e in events)
        assert any(e.event_type == "quest_room_complete" for e in emitted)

        state = quests.get_quest_state("puzzle_room_01")
        assert state is not None
        assert state.status == "completed"

        # Door gate is now satisfied
        door_prefab = _load_prefab("puzzle_exit_door")
        door_entity = MagicMock()
        door_entity.mesh_entity_data = door_prefab.get("entity", {})
        from engine.scene_entity_gating import runtime_entity_passes_flag_gates
        assert runtime_entity_passes_flag_gates(door_entity, get_flag=window.get_flag) is True

    def test_save_restore_mid_sequence(self) -> None:
        window = _build_window()
        runners = _build_action_runners(window)

        # Trigger the first rune and save
        window.gameplay_event_bus.emit("puzzle_rune_a", entity="player")
        _drain_until_empty(window, runners)

        assert window.game_state_controller.state.flags.get("puzzle.seq1") is True

        saved_flags = window.game_state_controller.state.snapshot()
        saved_bus = window.gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in runners}

        # Restore into a fresh window
        new_window = _build_window()
        new_runners = _build_action_runners(new_window)

        new_window.game_state_controller.state.restore(saved_flags)
        new_window.gameplay_event_bus.restore_state(saved_bus)

        for runner in new_runners:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)

        # Continue sequence after restore
        new_window.gameplay_event_bus.emit("puzzle_rune_c", entity="player")
        _drain_until_empty(new_window, new_runners)
        new_window.gameplay_event_bus.emit("puzzle_rune_b", entity="player")
        _drain_until_empty(new_window, new_runners)

        assert new_window.game_state_controller.state.flags.get("puzzle.solved") is True
        assert new_window.game_state_controller.state.flags.get("puzzle.seq1") is False
        assert new_window.game_state_controller.state.flags.get("puzzle.seq2") is False
