"""Pure, deterministic HUD view-model helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from engine.combat_constants import (
    EVENT_COMBAT_ATTACK,
    EVENT_COMBAT_DAMAGE,
    EVENT_COMBAT_DEATH,
    EVENT_COMBAT_HIT,
    EVENT_COMBAT_MISS,
    EVENT_PROJECTILE_FIRED,
    EVENT_PROJECTILE_HIT,
    canonicalize_combat_event_name,
)

_DEFAULT_FEED_LIMIT = 10

_FEED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        EVENT_COMBAT_ATTACK,
        EVENT_PROJECTILE_FIRED,
        EVENT_PROJECTILE_HIT,
        EVENT_COMBAT_HIT,
        EVENT_COMBAT_DAMAGE,
        EVENT_COMBAT_MISS,
        EVENT_COMBAT_DEATH,
    }
)


@dataclass(frozen=True, slots=True)
class HealthHudState:
    hp: float
    max_hp: float
    dead: bool
    last_damage_time: float | None
    last_damage_amount: float | None


@dataclass(frozen=True, slots=True)
class CombatFeedRow:
    event_type: str
    source: str
    target: str
    amount: float
    seq: int


@dataclass(frozen=True, slots=True)
class HudViewModel:
    health_state: HealthHudState
    recent_feed_rows: tuple[CombatFeedRow, ...]


@dataclass(frozen=True, slots=True)
class HudEventRecord:
    event_type: str
    payload: dict[str, Any]
    sequence: int


def merge_event_histories(
    gameplay_history: Iterable[Any] | None,
    mesh_history: Iterable[Any] | None,
) -> tuple[HudEventRecord, ...]:
    """Merge gameplay + mesh event histories into one deterministic sequence."""
    primary = normalize_event_history(gameplay_history, sequence_offset=0)
    next_seq = (max((item.sequence for item in primary), default=-1) + 1) if primary else 0
    secondary = normalize_event_history(mesh_history, sequence_offset=next_seq)
    merged = sorted((*primary, *secondary), key=lambda item: (item.sequence, item.event_type))
    return tuple(merged)


def normalize_event_history(
    history: Iterable[Any] | None,
    *,
    sequence_offset: int = 0,
) -> tuple[HudEventRecord, ...]:
    """Normalize heterogeneous history entries into canonical event records."""
    if history is None:
        return ()

    records: list[HudEventRecord] = []
    base = int(sequence_offset)
    for index, raw in enumerate(list(history)):
        event_type, payload, sequence = _extract_event(raw, index=index, sequence_offset=base)
        if not event_type:
            continue
        records.append(HudEventRecord(event_type=event_type, payload=payload, sequence=sequence))
    records.sort(key=lambda item: (item.sequence, item.event_type))
    return tuple(records)


def build_hud_view_model(
    player_entity: Any,
    gameplay_event_bus_history: Iterable[Any],
    now_frame_or_time: float,
    *,
    feed_limit: int = _DEFAULT_FEED_LIMIT,
) -> HudViewModel:
    """Build deterministic HUD state from entity health and event history."""
    records = normalize_event_history(gameplay_event_bus_history)
    player_tokens = _player_tokens(player_entity)
    hp, max_hp, dead = _health_from_entity(player_entity)

    rows: list[CombatFeedRow] = []
    last_damage_seq: int | None = None
    last_damage_amount: float | None = None
    death_by_event = False

    for record in records:
        event_type = canonicalize_combat_event_name(record.event_type)
        if event_type not in _FEED_EVENT_TYPES:
            continue
        source = _coerce_str(
            record.payload.get("source")
            or record.payload.get("attacker")
            or record.payload.get("entity_name")
        )
        target = _coerce_str(
            record.payload.get("target")
            or record.payload.get("name")
            or record.payload.get("entity")
        )
        amount = _coerce_float(record.payload.get("amount", record.payload.get("damage", 0.0)))
        row = CombatFeedRow(
            event_type=event_type,
            source=source,
            target=target,
            amount=round(amount, 6),
            seq=int(record.sequence),
        )
        rows.append(row)

        target_is_player = bool(target and target in player_tokens)
        if event_type == EVENT_COMBAT_DAMAGE and target_is_player:
            last_damage_seq = row.seq
            last_damage_amount = row.amount
        if event_type == EVENT_COMBAT_DEATH and target_is_player:
            death_by_event = True

    rows.sort(key=lambda item: (item.seq, item.event_type, item.source, item.target, item.amount))
    limit = max(0, int(feed_limit))
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    elif limit == 0:
        rows = []

    if not dead and death_by_event:
        dead = True

    last_damage_time: float | None = None
    if last_damage_seq is not None:
        now_value = float(now_frame_or_time)
        last_damage_time = round(max(0.0, now_value - float(last_damage_seq)), 6)

    health_state = HealthHudState(
        hp=round(hp, 6),
        max_hp=round(max_hp, 6),
        dead=bool(dead),
        last_damage_time=last_damage_time,
        last_damage_amount=last_damage_amount,
    )
    return HudViewModel(health_state=health_state, recent_feed_rows=tuple(rows))


def _extract_event(raw: Any, *, index: int, sequence_offset: int) -> tuple[str, dict[str, Any], int]:
    if isinstance(raw, HudEventRecord):
        return (
            str(raw.event_type or "").strip(),
            dict(raw.payload) if isinstance(raw.payload, dict) else {},
            int(raw.sequence),
        )

    if isinstance(raw, dict):
        event_type = _coerce_str(raw.get("event_type") or raw.get("name") or raw.get("type"))
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        sequence = raw.get("sequence")
        if isinstance(sequence, (int, float)) and not isinstance(sequence, bool):
            seq = int(sequence)
        else:
            seq = int(sequence_offset + index)
        return event_type, dict(payload), seq

    event_type = _coerce_str(
        getattr(raw, "event_type", None)
        or getattr(raw, "name", None)
        or getattr(raw, "type", None)
    )
    payload = getattr(raw, "payload", {})
    if not isinstance(payload, dict):
        payload = {}
    sequence = getattr(raw, "sequence", None)
    if isinstance(sequence, (int, float)) and not isinstance(sequence, bool):
        seq = int(sequence)
    else:
        seq = int(sequence_offset + index)
    return event_type, dict(payload), seq


def _health_from_entity(player_entity: Any) -> tuple[float, float, bool]:
    if player_entity is None:
        return (0.0, 0.0, True)
    behaviours = getattr(player_entity, "mesh_behaviours_runtime", [])
    for behaviour in behaviours:
        hp_raw = getattr(behaviour, "hp", None)
        max_hp_raw = getattr(behaviour, "max_hp", None)
        if isinstance(hp_raw, (int, float)) and isinstance(max_hp_raw, (int, float)):
            hp = float(hp_raw)
            max_hp = float(max_hp_raw)
            dead_raw = getattr(behaviour, "_dead", hp <= 0.0)
            return (hp, max_hp, bool(dead_raw))
    return (0.0, 0.0, True)


def _player_tokens(player_entity: Any) -> set[str]:
    tokens: set[str] = set()
    for attr in ("mesh_id", "mesh_name", "name"):
        value = _coerce_str(getattr(player_entity, attr, ""))
        if value:
            tokens.add(value)
    tag = _coerce_str(getattr(player_entity, "mesh_tag", ""))
    if tag:
        tokens.add(tag)
    tokens.add("player")
    tokens.add("Player")
    return tokens


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

