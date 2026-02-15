"""Pure-ish player input-to-action mapping and combat trace adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.combat_constants import EVENT_COMBAT_ATTACK
from engine.event_emit import emit_gameplay_event


@dataclass(frozen=True, slots=True)
class PlayerInputSnapshot:
    move_x: float
    move_y: float
    interact_down: bool
    attack_down: bool


@dataclass(frozen=True, slots=True)
class PlayerActionState:
    interact_was_down: bool = False


@dataclass(frozen=True, slots=True)
class PlayerActionDecision:
    action_ids: tuple[str, ...]
    move_x: float
    move_y: float
    interact_triggered: bool
    attack_triggered: bool


def build_player_input_snapshot(
    input_manager: Any,
    *,
    move_x: float,
    move_y: float,
) -> PlayerInputSnapshot:
    interact_down = False
    attack_down = False
    if input_manager is not None:
        interact_down = bool(input_manager.is_action_down("interact"))
        attack_down = bool(input_manager.is_action_down("attack"))
    return PlayerInputSnapshot(
        move_x=_clamp_axis(move_x),
        move_y=_clamp_axis(move_y),
        interact_down=interact_down,
        attack_down=attack_down,
    )


def map_input_to_actions(
    snapshot: PlayerInputSnapshot,
    state: PlayerActionState,
) -> tuple[PlayerActionDecision, PlayerActionState]:
    interact_triggered = bool(snapshot.interact_down and not state.interact_was_down)
    attack_triggered = bool(snapshot.attack_down)

    action_ids: list[str] = []
    if snapshot.move_x != 0.0 or snapshot.move_y != 0.0:
        action_ids.append("move")
    if interact_triggered:
        action_ids.append("interact")
    if attack_triggered:
        action_ids.append("attack")

    decision = PlayerActionDecision(
        action_ids=tuple(action_ids),
        move_x=float(snapshot.move_x),
        move_y=float(snapshot.move_y),
        interact_triggered=interact_triggered,
        attack_triggered=attack_triggered,
    )
    next_state = PlayerActionState(interact_was_down=bool(snapshot.interact_down))
    return decision, next_state


def dispatch_attack_action(entity: Any, window: Any) -> bool:
    """Trigger existing attack behaviour path and emit canonical attack trace."""
    if entity is None:
        return False
    behaviours = getattr(entity, "mesh_behaviours_runtime", [])
    attacked = False
    for behaviour in behaviours:
        attack = getattr(behaviour, "attack", None)
        if callable(attack):
            attack()
            attacked = True
            break
    if not attacked:
        return False
    _emit_attack_trace(window, entity)
    return True


def _emit_attack_trace(window: Any, entity: Any) -> None:
    if window is None:
        return
    source = _coerce_str(getattr(entity, "mesh_name", "") or getattr(entity, "mesh_id", "") or "player")
    target = _coerce_str(getattr(entity, "mesh_target_hint", ""))
    payload = {
        "attacker": source,
        "source": source,
        "target": target or "unknown",
        "type": "input_attack",
        "action_id": "attack",
    }
    emit_gameplay_event(
        window,
        EVENT_COMBAT_ATTACK,
        payload,
        source_entity_id=str(getattr(entity, "mesh_id", "") or ""),
        source_behaviour="PlayerActions",
    )


def _clamp_axis(value: float) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return 0.0
    if raw < -1.0:
        return -1.0
    if raw > 1.0:
        return 1.0
    return raw


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()
