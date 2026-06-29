"""Runtime-free helpers for captured monster party/box state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

from .battle_model import MonsterInstance

MONSTER_PARTY_KEY = "monster_party"
MONSTER_BOX_KEY = "monster_box"
MONSTER_INSTANCES_KEY = "monster_instances"
POCKET_BALL_COUNT_KEY = "pocket_ball_count"
DEFAULT_POCKET_BALL_COUNT = 3
MAX_PARTY_SIZE = 6


@dataclass(frozen=True, slots=True)
class AddCaughtMonsterResult:
    instance_id: str
    storage: str
    party_size: int
    box_size: int


def ensure_monster_collection(values: MutableMapping[str, Any]) -> None:
    if not isinstance(values.get(MONSTER_PARTY_KEY), list):
        values[MONSTER_PARTY_KEY] = []
    if not isinstance(values.get(MONSTER_BOX_KEY), list):
        values[MONSTER_BOX_KEY] = []
    if not isinstance(values.get(MONSTER_INSTANCES_KEY), dict):
        values[MONSTER_INSTANCES_KEY] = {}
    if not isinstance(values.get(POCKET_BALL_COUNT_KEY), (int, float)) or isinstance(values.get(POCKET_BALL_COUNT_KEY), bool):
        values[POCKET_BALL_COUNT_KEY] = DEFAULT_POCKET_BALL_COUNT
    values[POCKET_BALL_COUNT_KEY] = max(0, int(values[POCKET_BALL_COUNT_KEY]))


def get_pocket_ball_count(values: MutableMapping[str, Any]) -> int:
    ensure_monster_collection(values)
    return int(values[POCKET_BALL_COUNT_KEY])


def consume_pocket_ball(values: MutableMapping[str, Any]) -> bool:
    ensure_monster_collection(values)
    count = int(values[POCKET_BALL_COUNT_KEY])
    if count <= 0:
        return False
    values[POCKET_BALL_COUNT_KEY] = count - 1
    return True


def add_caught_monster(values: MutableMapping[str, Any], monster: MonsterInstance) -> AddCaughtMonsterResult:
    ensure_monster_collection(values)
    party = values[MONSTER_PARTY_KEY]
    box = values[MONSTER_BOX_KEY]
    instances = values[MONSTER_INSTANCES_KEY]
    instance_id = _next_instance_id(instances, monster.species.id)
    instances[instance_id] = serialize_monster_instance(monster)
    if len(party) < MAX_PARTY_SIZE:
        party.append(instance_id)
        storage = "party"
    else:
        box.append(instance_id)
        storage = "box"
    return AddCaughtMonsterResult(instance_id, storage, len(party), len(box))


def serialize_monster_instance(monster: MonsterInstance) -> dict[str, Any]:
    return {
        "species_id": monster.species.id,
        "level": int(monster.level),
        "xp": int(monster.experience),
        "current_hp": int(monster.current_hp or 0),
        "known_moves": list(monster.known_moves),
    }


def _next_instance_id(instances: MutableMapping[str, Any], species_id: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(species_id).strip()) or "monster"
    index = 1
    while True:
        candidate = f"{slug}_{index:04d}"
        if candidate not in instances:
            return candidate
        index += 1
