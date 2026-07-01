"""Friendly terminology helpers for Creator Mode.

This module is intentionally pure: it accepts snapshots/dicts and returns labels.
It must not import Arcade, editor controllers, or runtime systems.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_TERM_MAP: dict[str, str] = {
    "entity": "Thing",
    "behaviour": "What it does",
    "behavior": "What it does",
    "scene": "Map",
    "sceneexit": "Door",
    "scene_exit": "Door",
    "scenetransition": "Door",
    "scene_transition": "Door",
    "triggerzone": "Area",
    "trigger_zone": "Area",
    "monsterencounterzone": "Monster Area",
    "monster_encounter_zone": "Monster Area",
    "vendor": "Shopkeeper",
}

_DOOR_BEHAVIOURS = {"sceneexit", "scene_exit", "scenetransition", "scene_transition"}
_MONSTER_AREA_BEHAVIOURS = {"monsterencounterzone", "monster_encounter_zone"}
_SHOPKEEPER_BEHAVIOURS = {"vendor"}
_TRIGGER_AREA_BEHAVIOURS = {"triggerzone", "trigger_zone"}
_LIGHT_BEHAVIOURS = {"lightsource", "light_source", "togglelights", "toggle_scene_lights"}
_ENEMY_AI_BEHAVIOURS = {"enemyai", "enemy_ai", "rangedenemyai", "ranged_enemy_ai", "patrolchase", "patrol_chase"}


def friendly_engine_term(term: object) -> str:
    """Return the creator-facing label for an engine term."""

    key = _normalize_name(term)
    return _TERM_MAP.get(key, str(term or "Thing"))


def classify_entity_snapshot(snapshot: Mapping[str, Any] | None) -> str:
    """Classify a selected entity snapshot into a Creator Mode kind."""

    if not isinstance(snapshot, Mapping):
        return "Thing"

    behaviours = _behaviour_names(snapshot)
    config_names = _config_names(snapshot)
    tags = _string_set(snapshot.get("tags")) | _string_set(snapshot.get("tag"))
    name = _normalize_name(snapshot.get("name") or snapshot.get("id") or snapshot.get("mesh_name"))
    all_names = behaviours | config_names

    if all_names & _DOOR_BEHAVIOURS:
        return "Door"
    if all_names & _MONSTER_AREA_BEHAVIOURS:
        return "Monster Area"
    if all_names & _SHOPKEEPER_BEHAVIOURS:
        return "Shopkeeper"
    if "health" in all_names and (all_names & _ENEMY_AI_BEHAVIOURS or "enemy" in tags or "enemy" in name):
        return "Enemy"
    if _is_light_related(snapshot, all_names, tags, name):
        return "Light"
    if all_names & _TRIGGER_AREA_BEHAVIOURS:
        return "Area"
    if _looks_like_person(all_names, tags, name):
        return "Person"
    if _looks_like_item(all_names, tags, name):
        return "Item"
    return "Thing"


def summarize_entity_snapshot(snapshot: Mapping[str, Any] | None) -> str:
    """Build a short read-only friendly summary for the selected snapshot."""

    if not isinstance(snapshot, Mapping):
        return "No object selected."
    kind = classify_entity_snapshot(snapshot)
    title = selected_title(snapshot)
    if not title:
        return f"Selected {kind}."
    return f"Selected {kind}: {title}."


def selected_title(snapshot: Mapping[str, Any] | None) -> str:
    """Return the best friendly title for a selected entity snapshot."""

    if not isinstance(snapshot, Mapping):
        return ""
    for key in ("display_name", "name", "mesh_name", "id", "prefab_id"):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _behaviour_names(snapshot: Mapping[str, Any]) -> set[str]:
    raw = snapshot.get("behaviours")
    names: set[str] = set()
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for entry in raw:
            if isinstance(entry, str):
                names.add(_normalize_name(entry))
            elif isinstance(entry, Mapping):
                names.add(_normalize_name(entry.get("type") or entry.get("name")))
    elif isinstance(raw, Mapping):
        names |= {_normalize_name(key) for key in raw.keys()}
    return {name for name in names if name}


def _config_names(snapshot: Mapping[str, Any]) -> set[str]:
    raw = snapshot.get("behaviour_config")
    if not isinstance(raw, Mapping):
        return set()
    return {_normalize_name(key) for key in raw.keys() if _normalize_name(key)}


def _is_light_related(snapshot: Mapping[str, Any], all_names: set[str], tags: set[str], name: str) -> bool:
    if all_names & _LIGHT_BEHAVIOURS:
        return True
    if "light" in tags or "light" in name:
        return True
    light_type = snapshot.get("type")
    return _normalize_name(light_type) in {"light", "pointlight", "point_light"}


def _looks_like_person(all_names: set[str], tags: set[str], name: str) -> bool:
    if all_names & {"dialogue", "questgiver", "quest_giver", "npcschedule", "npc_schedule"}:
        return True
    return bool(tags & {"person", "npc", "character"}) or "npc" in name


def _looks_like_item(all_names: set[str], tags: set[str], name: str) -> bool:
    if all_names & {"collectible", "pickupcollectible", "pickup_collectible", "inventoryholder", "inventory_holder"}:
        return True
    return bool(tags & {"item", "collectible", "pickup"}) or "item" in name


def _string_set(value: object) -> set[str]:
    if isinstance(value, str):
        return {_normalize_name(value)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {_normalize_name(item) for item in value if _normalize_name(item)}
    return set()


def _normalize_name(value: object) -> str:
    return str(value or "").strip().replace("-", "_").replace(" ", "_").lower()
