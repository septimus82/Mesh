"""Pure friendly inspector models for Creator Mode."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .creator_terms import classify_entity_snapshot, selected_title, summarize_entity_snapshot


@dataclass(frozen=True, slots=True)
class CreatorInspectorField:
    """One read-only, creator-facing inspector row."""

    label: str
    value: str
    missing: bool = False


@dataclass(frozen=True, slots=True)
class CreatorInspectorModel:
    """Read-only friendly inspector data for the selected object."""

    kind: str
    title: str
    summary: str
    fields: tuple[CreatorInspectorField, ...]
    warnings: tuple[str, ...]


def empty_creator_inspector() -> CreatorInspectorModel:
    """Return the no-selection inspector state."""

    return CreatorInspectorModel(
        kind="Thing",
        title="",
        summary="No object selected.",
        fields=(),
        warnings=(),
    )


def build_creator_inspector(snapshot: Mapping[str, Any] | None) -> CreatorInspectorModel:
    """Build a read-only friendly inspector model without mutating input."""

    if not isinstance(snapshot, Mapping):
        return empty_creator_inspector()

    kind = classify_entity_snapshot(snapshot)
    title = selected_title(snapshot)
    summary = summarize_entity_snapshot(snapshot)

    if kind == "Door":
        fields = _door_fields(snapshot)
        warnings = () if _field_value(fields, "Destination Map") else ("Door has no destination map.",)
    elif kind == "Person":
        fields = _person_fields(snapshot)
        warnings = ()
    elif kind == "Monster Area":
        fields = _monster_area_fields(snapshot)
        warnings = ()
    elif kind == "Shopkeeper":
        fields = _shopkeeper_fields(snapshot)
        warnings = ()
    elif kind == "Enemy":
        fields = _enemy_fields(snapshot)
        warnings = ()
    elif kind == "Light":
        fields = _light_fields(snapshot)
        warnings = ()
    else:
        fields = _thing_fields(snapshot)
        warnings = ()

    return CreatorInspectorModel(
        kind=kind,
        title=title,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def _door_fields(snapshot: Mapping[str, Any]) -> tuple[CreatorInspectorField, ...]:
    config = _merged_config(snapshot, ("SceneExit", "SceneTransition"))
    return (
        _field("Destination Map", _first_value(config, snapshot, ("target_scene", "scene", "destination", "target"))),
        _field("Arrival Point", _first_value(config, snapshot, ("spawn_id", "target_spawn", "target_spawn_id"))),
        _field("Trigger", _first_value(config, snapshot, ("listen_event", "trigger"))),
        _field("Locked", _locked_value(config, snapshot)),
    )


def _person_fields(snapshot: Mapping[str, Any]) -> tuple[CreatorInspectorField, ...]:
    dialogue = _merged_config(snapshot, ("Dialogue",))
    quest = _merged_config(snapshot, ("QuestGiver", "Quest_Giver"))
    vendor = _merged_config(snapshot, ("Vendor",))
    schedule = _merged_config(snapshot, ("NpcSchedule", "Npc_Schedule", "NPCSchedule"))
    return (
        _field("Conversation", _first_value(dialogue, snapshot, ("dialogue_id", "conversation", "conversation_id", "text"))),
        _field("Quest", _first_value(quest, snapshot, ("quest_id", "quest", "quests"))),
        _field("Shop", _first_value(vendor, snapshot, ("shop_id", "stock", "inventory"))),
        _field("Schedule", _first_value(schedule, snapshot, ("schedule", "schedule_id", "route"))),
    )


def _monster_area_fields(snapshot: Mapping[str, Any]) -> tuple[CreatorInspectorField, ...]:
    config = _merged_config(snapshot, ("MonsterEncounterZone", "Monster_Encounter_Zone"))
    return (
        _field("Encounter Set", _first_value(config, snapshot, ("encounter_set", "encounter_set_id", "encounters"))),
        _field("Monster", _first_value(config, snapshot, ("monster", "monster_id", "monsters", "enemy"))),
        _field("Chance", _first_value(config, snapshot, ("chance", "encounter_chance", "rate"))),
        _field("Cooldown", _first_value(config, snapshot, ("cooldown", "cooldown_seconds", "cooldown_ms"))),
    )


def _shopkeeper_fields(snapshot: Mapping[str, Any]) -> tuple[CreatorInspectorField, ...]:
    config = _merged_config(snapshot, ("Vendor",))
    return (
        _field("Stock", _first_value(config, snapshot, ("stock", "items", "inventory", "shop_id"))),
        _field("Currency", _first_value(config, snapshot, ("currency", "currency_id", "money_item"))),
    )


def _enemy_fields(snapshot: Mapping[str, Any]) -> tuple[CreatorInspectorField, ...]:
    health = _merged_config(snapshot, ("Health",))
    ai = _merged_config(snapshot, ("EnemyAI", "Enemy_AI", "RangedEnemyAI", "Ranged_Enemy_AI", "PatrolChase", "Patrol_Chase"))
    return (
        _field("Health", _first_value(health, snapshot, ("hp", "health", "max_hp", "max_health"))),
        _field("AI", _ai_value(snapshot, ai)),
        _field("Target", _first_value(ai, snapshot, ("target", "target_tag", "target_id"))),
    )


def _light_fields(snapshot: Mapping[str, Any]) -> tuple[CreatorInspectorField, ...]:
    config = _merged_config(snapshot, ("LightSource", "Light_Source", "ToggleLights", "Toggle_Scene_Lights"))
    return (
        _field("Type", _first_value(config, snapshot, ("type", "light_type", "kind"))),
        _field("Color", _first_value(config, snapshot, ("color", "colour", "tint"))),
        _field("Radius", _first_value(config, snapshot, ("radius", "range"))),
        _field("Intensity", _first_value(config, snapshot, ("intensity", "strength", "alpha"))),
    )


def _thing_fields(snapshot: Mapping[str, Any]) -> tuple[CreatorInspectorField, ...]:
    return (
        _field("Name", selected_title(snapshot)),
        _field("Behaviours", _behaviour_list(snapshot)),
    )


def _field(label: str, raw_value: object) -> CreatorInspectorField:
    if raw_value is None or raw_value == "":
        return CreatorInspectorField(label=label, value="Not set", missing=True)
    return CreatorInspectorField(label=label, value=_format_value(raw_value), missing=False)


def _field_value(fields: tuple[CreatorInspectorField, ...], label: str) -> str:
    for field in fields:
        if field.label == label and not field.missing:
            return field.value
    return ""


def _first_value(*sources_and_keys: object) -> object:
    keys = sources_and_keys[-1]
    sources = sources_and_keys[:-1]
    if not isinstance(keys, tuple):
        return None
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            value = _lookup(source, str(key))
            if value is not None and value != "":
                return value
    return None


def _locked_value(config: Mapping[str, Any], snapshot: Mapping[str, Any]) -> object:
    locked = _first_value(config, snapshot, ("locked",))
    if locked is not None:
        return locked
    requires_flag = _first_value(config, snapshot, ("requires_flag",))
    if requires_flag:
        return f"Requires {requires_flag}"
    return None


def _ai_value(snapshot: Mapping[str, Any], config: Mapping[str, Any]) -> object:
    value = _first_value(config, snapshot, ("ai", "ai_type", "state", "mode"))
    if value is not None:
        return value
    names = [name for name in _behaviour_names(snapshot) if "ai" in _normalize_name(name)]
    return ", ".join(names) if names else None


def _merged_config(snapshot: Mapping[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    raw = snapshot.get("behaviour_config")
    if not isinstance(raw, Mapping):
        return {}

    normalized_names = {_normalize_name(name) for name in names}
    merged: dict[str, Any] = {}
    for key, value in raw.items():
        if _normalize_name(key) not in normalized_names:
            continue
        if isinstance(value, Mapping):
            merged.update(dict(value))
    return merged


def _lookup(source: Mapping[str, Any], key: str) -> object:
    if key in source:
        return source[key]
    normalized_key = _normalize_name(key)
    for existing_key, value in source.items():
        if _normalize_name(existing_key) == normalized_key:
            return value
    return None


def _behaviour_list(snapshot: Mapping[str, Any]) -> object:
    names = _behaviour_names(snapshot)
    if not names:
        return None
    return ", ".join(names)


def _behaviour_names(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    raw = snapshot.get("behaviours")
    names: list[str] = []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for entry in raw:
            if isinstance(entry, str) and entry.strip():
                names.append(entry.strip())
            elif isinstance(entry, Mapping):
                value = entry.get("type") or entry.get("name")
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
    elif isinstance(raw, Mapping):
        names.extend(str(key).strip() for key in raw.keys() if str(key).strip())
    return tuple(names)


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Mapping):
        return "Configured" if value else "Empty"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if not value:
            return "Empty"
        return ", ".join(_format_value(item) for item in value)
    return str(value)


def _normalize_name(value: object) -> str:
    return str(value or "").strip().replace("-", "_").replace(" ", "_").lower()
