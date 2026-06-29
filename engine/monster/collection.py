"""Runtime-free helpers for captured monster party/box state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from .battle_model import MonsterInstance, Species

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


def load_battle_party_from_values(
    values: MutableMapping[str, Any],
    species_by_id: Mapping[str, Species],
    *,
    fallback: MonsterInstance,
) -> tuple[list[MonsterInstance], list[str | None]]:
    """Build battle-ready party instances from persisted collection state.

    Returns the party plus parallel instance ids captured at load time. The fallback
    monster uses ``None`` when the persisted party is empty.
    """

    ensure_monster_collection(values)
    party: list[MonsterInstance] = []
    instance_ids: list[str | None] = []
    for instance_id in values[MONSTER_PARTY_KEY]:
        row = values[MONSTER_INSTANCES_KEY].get(str(instance_id))
        if not isinstance(row, dict):
            continue
        species_id = str(row.get("species_id", ""))
        species = species_by_id.get(species_id)
        if species is None:
            continue
        known_moves = row.get("known_moves")
        moves = tuple(str(move_id) for move_id in known_moves) if isinstance(known_moves, list) else species.learnset
        party.append(
            MonsterInstance(
                species,
                level=int(row.get("level", 1) or 1),
                current_hp=int(row.get("current_hp", 0) or 0),
                known_moves=moves,
                experience=int(row.get("xp", row.get("experience", 0)) or 0),
            )
        )
        instance_ids.append(str(instance_id))
    if party:
        return party, instance_ids
    return [fallback], [None]


def _next_instance_id(instances: MutableMapping[str, Any], species_id: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(species_id).strip()) or "monster"
    index = 1
    while True:
        candidate = f"{slug}_{index:04d}"
        if candidate not in instances:
            return candidate
        index += 1
