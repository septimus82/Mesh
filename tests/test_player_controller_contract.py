from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from engine.behaviours.health import Health
from engine.behaviours.player_controller import PlayerController
from engine.events import MeshEventBus
from engine.hud_model import build_hud_view_model, merge_event_histories
from engine.player_actions import PlayerActionState, build_player_input_snapshot, map_input_to_actions


@dataclass
class _FrameInput:
    move_x: float = 0.0
    move_y: float = 0.0
    attack: bool = False
    interact: bool = False


class _InputSchedule:
    def __init__(self, frames: list[_FrameInput]) -> None:
        self._frames = list(frames)
        self._index = 0

    def set_frame(self, index: int) -> None:
        self._index = int(index)

    def get_axis(self, negative_action: str, positive_action: str) -> float:
        frame = self._frames[self._index]
        if "left" in negative_action and "right" in positive_action:
            return float(frame.move_x)
        return float(frame.move_y)

    def is_action_down(self, action: str) -> bool:
        frame = self._frames[self._index]
        if action == "attack":
            return bool(frame.attack)
        if action == "interact":
            return bool(frame.interact)
        return False


class _AttackBehaviour:
    def __init__(self, window: Any, owner: Any) -> None:
        self._window = window
        self._owner = owner
        self.calls = 0

    def attack(self) -> None:
        self.calls += 1
        self._window.event_bus.emit(
            "projectile_fired",
            source=str(getattr(self._owner, "mesh_name", "player") or "player"),
            speed=300.0,
            x=float(getattr(self._owner, "center_x", 0.0)),
            y=float(getattr(self._owner, "center_y", 0.0)),
        )


def test_player_actions_mapping_contract() -> None:
    state = PlayerActionState()
    snapshot_a = build_player_input_snapshot(
        SimpleNamespace(is_action_down=lambda action: action == "interact"),
        move_x=2.0,
        move_y=-2.0,
    )
    decision_a, state = map_input_to_actions(snapshot_a, state)
    assert decision_a.move_x == 1.0
    assert decision_a.move_y == -1.0
    assert decision_a.action_ids == ("move", "interact")
    assert decision_a.interact_triggered is True

    snapshot_b = build_player_input_snapshot(
        SimpleNamespace(is_action_down=lambda action: action == "interact"),
        move_x=0.0,
        move_y=0.0,
    )
    decision_b, _state_b = map_input_to_actions(snapshot_b, state)
    assert decision_b.action_ids == ()
    assert decision_b.interact_triggered is False


def test_player_controller_emits_attack_trace_and_hud_is_deterministic() -> None:
    run_a = _run_player_loop_schedule()
    run_b = _run_player_loop_schedule()
    assert run_a == run_b

    event_names = [item["name"] for item in run_a["events"]]
    assert event_names == [
        "projectile_fired",
        "combat_attack",
        "projectile_fired",
        "combat_attack",
        "projectile_fired",
        "combat_attack",
        "combat_hit",
        "combat_damage",
        "damage_applied",
    ]
    assert run_a["attack_calls"] == 3
    assert "combat_attack" in run_a["hud_feed_types"]
    assert "projectile_fired" in run_a["hud_feed_types"]
    assert run_a["hud_hp"] == 18.0
    assert run_a["hud_max_hp"] == 20.0
    assert run_a["hud_dead"] is False


def _run_player_loop_schedule() -> dict[str, Any]:
    frames = [
        _FrameInput(move_x=1.0, move_y=0.0, attack=False),
        _FrameInput(move_x=1.0, move_y=0.0, attack=True),
        _FrameInput(move_x=0.0, move_y=0.0, attack=True),
        _FrameInput(move_x=-1.0, move_y=0.0, attack=False),
        _FrameInput(move_x=0.0, move_y=1.0, attack=True),
    ]
    input_schedule = _InputSchedule(frames)
    event_bus = MeshEventBus()

    window = SimpleNamespace()
    window.input = input_schedule
    window.event_bus = event_bus
    window.scene_controller = SimpleNamespace(solid_sprites=None)
    window.engine_config = SimpleNamespace(player_stats_enabled=False)
    window._mesh_interact_consumed = False
    window.player_input_blocked = lambda: False
    window.is_input_locked = lambda: False
    window.dialogue_blocks_input = lambda: False

    def _move_entity_with_collision(entity: Any, dx: float, dy: float, dt: float = 0.0) -> None:  # noqa: ARG001
        entity.center_x = float(getattr(entity, "center_x", 0.0)) + float(dx)
        entity.center_y = float(getattr(entity, "center_y", 0.0)) + float(dy)

    window.move_entity_with_collision = _move_entity_with_collision

    entity = SimpleNamespace(
        mesh_id="player",
        mesh_name="Player",
        mesh_tag="player",
        mesh_entity_data={},
        mesh_behaviours_runtime=[],
        center_x=0.0,
        center_y=0.0,
        width=32.0,
        height=32.0,
    )

    attack_behaviour = _AttackBehaviour(window, entity)
    health = Health(entity, window, max_hp=20.0, hp=20.0)
    entity.mesh_behaviours_runtime = [attack_behaviour, health]
    window.player = entity

    controller = PlayerController(entity, window, speed=100.0)
    for index in range(len(frames)):
        input_schedule.set_frame(index)
        controller.update(0.1)

    health.apply_damage(2.0, source_entity="enemy_test", source_behaviour="contract")

    recent = event_bus.get_recent_events(50)
    merged = merge_event_histories([], recent)
    hud_model = build_hud_view_model(entity, merged, now_frame_or_time=100.0)
    return {
        "attack_calls": int(attack_behaviour.calls),
        "events": [
            {"name": str(item.get("name", "")), "payload": dict(item.get("payload") or {})}
            for item in recent
        ],
        "hud_hp": hud_model.health_state.hp,
        "hud_max_hp": hud_model.health_state.max_hp,
        "hud_dead": hud_model.health_state.dead,
        "hud_feed_types": [row.event_type for row in hud_model.recent_feed_rows],
    }

