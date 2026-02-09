from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class NavInputs:
    scene_path: str | None
    revision: int


@dataclass(frozen=True, slots=True)
class NavCachePlan:
    scene_path: str | None
    revision: int


@dataclass(frozen=True, slots=True)
class PortalLink:
    source: str
    target: str
    via: str | None


def build_nav_cache_plan(inputs: NavInputs) -> NavCachePlan:
    return NavCachePlan(scene_path=inputs.scene_path, revision=int(inputs.revision))


def resolve_portals(scene_payload: dict[str, Any] | None) -> list[PortalLink]:
    if not isinstance(scene_payload, dict):
        return []
    raw = scene_payload.get("portals")
    if not isinstance(raw, list):
        return []
    links: list[PortalLink] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        source = entry.get("from") or entry.get("source")
        target = entry.get("to") or entry.get("target")
        if not isinstance(source, str) or not source.strip():
            continue
        if not isinstance(target, str) or not target.strip():
            continue
        via = entry.get("via")
        via_str = str(via).strip() if isinstance(via, str) and via.strip() else None
        links.append(PortalLink(source=source.strip(), target=target.strip(), via=via_str))
    links.sort(key=lambda link: (link.source, link.target, link.via or ""))
    return links


def stable_neighbor_order(deltas: Iterable[tuple[int, int]] | None = None) -> tuple[tuple[int, int], ...]:
    if deltas is None:
        return ((0, -1), (1, 0), (0, 1), (-1, 0))
    return tuple(deltas)
