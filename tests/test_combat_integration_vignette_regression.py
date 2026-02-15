from __future__ import annotations

import hashlib
import json

from engine.hud_model import build_hud_view_model
from tests.test_combat_vignette_01_integration import _deal_damage_to_enemy, _enter_arena, _setup_arena


def _run_vignette_damage_schedule() -> dict[str, object]:
    ctx = _setup_arena()
    events: list[str] = []
    events.extend(event.event_type for event in _enter_arena(ctx))

    for damage in (3.0, 3.0, 2.0, 2.0):
        ctx["window"].gameplay_event_bus.emit(
            "combat_attack",
            source_entity="player",
            source_behaviour="PlayerController",
            source="player",
            target="sentry_archer",
        )
        ctx["window"].gameplay_event_bus.emit(
            "projectile_fired",
            source_entity="player",
            source_behaviour="Shooter",
            source="player",
            x=0.0,
            y=0.0,
            speed=300.0,
        )
        ctx["window"].gameplay_event_bus.emit(
            "combat_damage",
            source_entity="player",
            source_behaviour="Projectile",
            source="player",
            target="sentry_archer",
            amount=float(damage),
        )
        events.extend(event.event_type for event in _deal_damage_to_enemy(ctx, damage))

    ctx["player_health"].apply_damage(2.0)
    ctx["window"].gameplay_event_bus.emit(
        "combat_damage",
        source_entity="sentry_archer",
        source_behaviour="Projectile",
        source="sentry_archer",
        target="Player",
        amount=2.0,
    )
    events.extend(event.event_type for event in ctx["window"].gameplay_event_bus.drain())

    hud_player = ctx["player_health"].entity
    hud_player.mesh_behaviours_runtime = [ctx["player_health"]]
    hud_vm = build_hud_view_model(
        hud_player,
        ctx["window"].gameplay_event_bus.get_history(200),
        now_frame_or_time=200.0,
    )

    flags = dict(sorted(ctx["window"].game_state_controller.state.flags.items()))
    return {
        "events": events,
        "enemy_hp": float(ctx["enemy_health"].hp),
        "enemy_dead": bool(ctx["enemy_health"]._dead),
        "flags": flags,
        "hud": {
            "hp": hud_vm.health_state.hp,
            "max_hp": hud_vm.health_state.max_hp,
            "dead": hud_vm.health_state.dead,
            "last_damage_amount": hud_vm.health_state.last_damage_amount,
            "last_feed_types": [row.event_type for row in hud_vm.recent_feed_rows[-3:]],
        },
    }


def test_combat_vignette_damage_regression_is_stable() -> None:
    run_a = _run_vignette_damage_schedule()
    run_b = _run_vignette_damage_schedule()
    assert run_a == run_b
    assert run_a["hud"]["hp"] == 18.0
    assert run_a["hud"]["max_hp"] == 20.0
    assert run_a["hud"]["dead"] is False
    assert run_a["hud"]["last_damage_amount"] == 2.0
    assert run_a["hud"]["last_feed_types"]

    digest_a = hashlib.sha256(json.dumps(run_a, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    digest_b = hashlib.sha256(json.dumps(run_b, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert digest_a == digest_b
