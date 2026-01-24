"""Content pack management system."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PackDependency:
    id: str
    min_version: Optional[str] = None
    max_version: Optional[str] = None

@dataclass
class Pack:
    id: str
    root: Path
    name: str = ""
    version: str = "0.0.0"
    type: str = "mod"  # core, demo, mod, dlc, test
    requires: List[PackDependency] = field(default_factory=list)
    load_after: List[str] = field(default_factory=list)
    load_before: List[str] = field(default_factory=list)
    overrides: List[str] = field(default_factory=list)

    # Audit metadata
    wip: bool = False
    audit_exempt: bool = False
    audit_policy_override: Dict[str, Any] = field(default_factory=dict)

    # Runtime metadata
    is_implicit: bool = False  # True if inferred from folder name

def load_pack(root_path: Path) -> Pack:
    """Load a pack from a directory, parsing manifest.json if present."""
    manifest_path = root_path / "manifest.json"

    if not manifest_path.exists():
        # Infer pack from directory
        return Pack(
            id=root_path.name,
            root=root_path,
            name=root_path.name,
            is_implicit=True
        )

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Mesh][Packs] Error parsing manifest at {manifest_path}: {e}")
        # Fallback to implicit
        return Pack(
            id=root_path.name,
            root=root_path,
            name=root_path.name,
            is_implicit=True
        )

    # Parse dependencies
    requires = []
    for req in data.get("requires", []):
        if isinstance(req, dict) and "id" in req:
            requires.append(PackDependency(
                id=req["id"],
                min_version=req.get("min"),
                max_version=req.get("max")
            ))

    return Pack(
        id=data.get("id", root_path.name),
        root=root_path,
        name=data.get("name", root_path.name),
        version=data.get("version", "0.0.0"),
        type=data.get("type", "mod"),
        requires=requires,
        load_after=data.get("load_after", []),
        load_before=data.get("load_before", []),
        overrides=data.get("overrides", []),
        wip=data.get("wip", False),
        audit_exempt=data.get("audit_exempt", False),
        audit_policy_override=data.get("audit_policy_override", {}),
        is_implicit=False
    )

def load_all_packs(roots: List[Path]) -> List[Pack]:
    """Load packs from all content roots."""
    return [load_pack(root) for root in roots if root.exists()]

def discover_packs(roots: List[Path]) -> List[Pack]:
    """Discover all packs including those in packs/ subdirectories."""
    packs = []
    for root in roots:
        if not root.exists():
            continue

        # The root itself is a pack (usually the main project)
        packs.append(load_pack(root))

        # Check for sub-packs
        packs_dir = root / "packs"
        if packs_dir.exists():
            for child in packs_dir.iterdir():
                if child.is_dir():
                    packs.append(load_pack(child))

    return sort_packs(packs)

def sort_packs(packs: List[Pack]) -> List[Pack]:
    """
    Sort packs based on load_after/load_before constraints and config order.
    Returns a list of packs in load order (highest priority first? No, usually load order implies application order).

    In Mesh, 'roots' are searched in order. The first root found wins.
    So 'High Priority' means 'First in List'.

    If Pack A says 'load_after: [B]', it means B should be loaded BEFORE A.
    So B is applied first, then A is applied (overriding B).
    So A should come BEFORE B in the priority list (roots list)?

    Wait.
    Standard mod loading:
    Base Game (Core) -> Mod A -> Mod B.
    Mod B overrides Mod A overrides Core.

    In Mesh `resolve_path`:
    for root in roots:
       if exists: return

    So the roots list is [HighPriority, MediumPriority, LowPriority].

    If Mod A 'load_after' Core:
    Core is loaded first (base). Mod A is loaded after (layer on top).
    So Mod A should be HIGHER priority in the lookup list.
    So Mod A comes BEFORE Core in the `roots` list.

    So:
    'load_after': [B] -> A is applied AFTER B -> A overrides B -> A is BEFORE B in roots list.
    'load_before': [B] -> A is applied BEFORE B -> B overrides A -> B is BEFORE A in roots list.

    We want to produce the `roots` list (High Priority -> Low Priority).

    Let's model this as a dependency graph where edge X -> Y means "X must be lower priority than Y" (Y overrides X).

    If A load_after B: A overrides B. A is higher priority. A -> B (A comes before B in list).
    If A load_before B: B overrides A. B is higher priority. B -> A (B comes before A in list).

    We also want to respect the original config order as a stable fallback.
    Original: [R1, R2, R3] -> R1 is highest priority.

    Let's use a topological sort.
    Nodes: Packs.
    Edges: Constraint "comes before in list".

    If A load_after B: A comes before B. Edge A -> B.
    If A load_before B: B comes before A. Edge B -> A.

    What about implicit order?
    If no constraints, we want to preserve the input order (which is the config order).

    We can use a stable topological sort.
    """

    # Map id -> Pack
    pack_map = {p.id: p for p in packs}

    # Build graph
    # adj[u] = [v] means u comes before v (u is higher priority)
    adj: Dict[str, List[str]] = {p.id: [] for p in packs}
    in_degree: Dict[str, int] = {p.id: 0 for p in packs}

    for p in packs:
        # load_after: p overrides target. p -> target.
        for target_id in p.load_after:
            if target_id in pack_map:
                adj[p.id].append(target_id)
                in_degree[target_id] += 1

        # load_before: target overrides p. target -> p.
        for target_id in p.load_before:
            if target_id in pack_map:
                adj[target_id].append(p.id)
                in_degree[p.id] += 1

    # Topological sort
    # We want to prefer the original order when there are no constraints.
    # So we initialize the queue with nodes having in_degree 0, sorted by their original index.

    # Original index map
    original_indices = {p.id: i for i, p in enumerate(packs)}

    queue = [p.id for p in packs if in_degree[p.id] == 0]
    # Sort queue by original index to maintain stability
    queue.sort(key=lambda pid: original_indices[pid])

    result = []

    while queue:
        u = queue.pop(0)
        result.append(pack_map[u])

        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

        # Re-sort queue every time we add new nodes?
        # Yes, to ensure that among available nodes, we pick the one that appeared earliest in config.
        queue.sort(key=lambda pid: original_indices[pid])

    if len(result) != len(packs):
        print("[Mesh][Packs] WARNING: Cyclic dependency detected in pack load order. Fallback to config order.")
        return packs

    return result

def validate_pack_dependencies(packs: List[Pack]) -> List[str]:
    """Check if all requirements are met."""
    errors = []
    pack_map = {p.id: p for p in packs}

    for p in packs:
        for req in p.requires:
            if req.id not in pack_map:
                errors.append(f"Pack '{p.id}' requires missing pack '{req.id}'")
                continue

            # Version check could go here (simple string compare or semver)
            # For now, just existence.

    return errors
