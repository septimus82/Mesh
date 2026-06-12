from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class FieldPatch:
    path: tuple[str, ...]
    op: str
    value: object | None = None


@dataclass(frozen=True, slots=True)
class SpawnOp:
    prefab_id: str | None = None
    target_id: str | None = None
    initial_fields: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class DespawnOp:
    entity_id: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MutateOp:
    entity_id: str
    patches: tuple[FieldPatch, ...]


@dataclass(frozen=True, slots=True)
class EntityOp:
    kind: str
    payload: object
    seq: int


@dataclass(frozen=True, slots=True)
class DrainPlan:
    ordered_ops: tuple[EntityOp, ...]


def stable_entity_order(entity_ids: Sequence[str], primary_id: str | None) -> list[str]:
    ordered: list[str] = []
    primary = str(primary_id).strip() if primary_id else ""
    if primary:
        if primary in entity_ids:
            ordered.append(primary)
    remainder = [eid for eid in entity_ids if eid and eid != primary]
    remainder.sort()
    ordered.extend(remainder)
    return ordered


def _kind_rank(kind: str) -> int:
    if kind == "despawn":
        return 0
    if kind == "spawn":
        return 1
    if kind == "mutate":
        return 2
    return 99


def normalize_ops(ops: Iterable[EntityOp]) -> list[EntityOp]:
    ordered = list(ops)
    ordered.sort(key=lambda op: (_kind_rank(op.kind), int(op.seq)))
    return ordered


def build_drain_plan(pending_ops: Iterable[EntityOp]) -> DrainPlan:
    ordered = tuple(normalize_ops(pending_ops))
    return DrainPlan(ordered_ops=ordered)
