from __future__ import annotations

from types import SimpleNamespace

from engine.behaviours.health import Health
from engine.hud_model import (
    build_hud_view_model,
    merge_event_histories,
)


def _make_player(*, hp: float, max_hp: float):
    window = SimpleNamespace(engine_config=None)
    entity = SimpleNamespace(
        mesh_id="player",
        mesh_name="Player",
        mesh_tag="player",
        mesh_entity_data={},
        mesh_behaviours_runtime=[],
    )
    health = Health(entity, window, hp=hp, max_hp=max_hp)
    entity.mesh_behaviours_runtime = [health]
    return entity, health


def test_hud_model_feed_ordering_is_sequence_stable() -> None:
    player, _health = _make_player(hp=12.0, max_hp=20.0)
    history = [
        {"event_type": "combat_attack", "sequence": 7, "payload": {"source": "player", "target": "enemy_a"}},
        {"event_type": "combat_damage", "sequence": 3, "payload": {"source": "enemy_a", "target": "Player", "amount": 2}},
        {"event_type": "projectile_fired", "sequence": 5, "payload": {"source": "player"}},
    ]

    vm = build_hud_view_model(player, history, now_frame_or_time=10.0)
    assert [row.seq for row in vm.recent_feed_rows] == [3, 5, 7]
    assert [row.event_type for row in vm.recent_feed_rows] == [
        "combat_damage",
        "projectile_fired",
        "combat_attack",
    ]


def test_hud_model_last_damage_fields_are_derived_deterministically() -> None:
    player, health = _make_player(hp=8.0, max_hp=10.0)
    health.apply_damage(3.0)
    history = [
        {"event_type": "combat_damage", "sequence": 12, "payload": {"source": "enemy", "target": "Player", "amount": 3.0}},
    ]

    vm = build_hud_view_model(player, history, now_frame_or_time=20.0)
    assert vm.health_state.hp == 5.0
    assert vm.health_state.max_hp == 10.0
    assert vm.health_state.dead is False
    assert vm.health_state.last_damage_amount == 3.0
    assert vm.health_state.last_damage_time == 8.0


def test_hud_model_feed_is_bounded() -> None:
    player, _health = _make_player(hp=5.0, max_hp=5.0)
    history = [
        {"event_type": "combat_attack", "sequence": index, "payload": {"source": "player", "target": "enemy"}}
        for index in range(25)
    ]

    vm = build_hud_view_model(player, history, now_frame_or_time=50.0, feed_limit=10)
    assert len(vm.recent_feed_rows) == 10
    assert vm.recent_feed_rows[0].seq == 15
    assert vm.recent_feed_rows[-1].seq == 24


def test_merge_event_histories_offsets_mesh_history_deterministically() -> None:
    gameplay = [
        {"event_type": "combat_attack", "sequence": 1, "payload": {"source": "player"}},
        {"event_type": "combat_damage", "sequence": 4, "payload": {"source": "enemy", "target": "Player", "amount": 2}},
    ]
    mesh = [
        {"name": "projectile_fired", "payload": {"source": "player"}},
        {"name": "damage_applied", "payload": {"source": "enemy", "target": "Player", "amount": 2}},
    ]

    merged = merge_event_histories(gameplay, mesh)
    assert [item.sequence for item in merged] == [1, 4, 5, 6]
    assert merged[-1].event_type == "damage_applied"

