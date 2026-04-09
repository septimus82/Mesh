from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.paths import get_content_roots


@dataclass(frozen=True)
class PackDependencySpec:
    id: str
    version_range: str | None = None


@dataclass(frozen=True)
class PackManifest:
    id: str
    version: str
    title: str | None
    description: str | None
    engine_compat: str | None
    dependencies: list[PackDependencySpec]
    root: Path
    path: str
    implicit: bool = False


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _format_path(path: Path, roots: list[Path]) -> str:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    for root in roots:
        try:
            root_resolved = root.resolve()
        except Exception:
            root_resolved = root
        try:
            rel = resolved.relative_to(root_resolved)
        except Exception:
            continue
        return rel.as_posix()
    return path.as_posix()


def discover_pack_roots() -> list[Path]:
    roots = get_content_roots()
    packs: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        packs.append(root)
        packs_dir = root / "packs"
        if not packs_dir.exists():
            continue
        for child in sorted([p for p in packs_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
            packs.append(child)
    return packs


def load_manifest(pack_root: Path) -> tuple[PackManifest, list[str]]:
    roots = get_content_roots()
    manifest_path = pack_root / "pack.json"
    errors: list[str] = []

    if not manifest_path.exists():
        manifest = PackManifest(
            id=pack_root.name,
            version="0.0.0-dev",
            title=None,
            description=None,
            engine_compat=None,
            dependencies=[],
            root=pack_root,
            path=_format_path(manifest_path, roots),
            implicit=True,
        )
        return manifest, errors

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: malformed pack manifests should report a parse error and fall back to the implicit manifest defaults
        errors.append(f"{_format_path(manifest_path, roots)}: parse_error: {exc}")
        manifest = PackManifest(
            id=pack_root.name,
            version="0.0.0-dev",
            title=None,
            description=None,
            engine_compat=None,
            dependencies=[],
            root=pack_root,
            path=_format_path(manifest_path, roots),
            implicit=True,
        )
        return manifest, errors

    if not isinstance(payload, dict):
        errors.append(f"{_format_path(manifest_path, roots)}: manifest root must be an object")
        payload = {}

    raw_id = payload.get("id")
    raw_version = payload.get("version")
    pack_id = _string(raw_id) or pack_root.name
    version = _string(raw_version) or "0.0.0-dev"
    title = _string(payload.get("title"))
    description = _string(payload.get("description"))
    engine_compat = _string(payload.get("engine_compat"))

    dependencies: list[PackDependencySpec] = []
    raw_deps = payload.get("dependencies", [])
    if raw_deps is None:
        raw_deps = []
    if not isinstance(raw_deps, list):
        errors.append(f"{_format_path(manifest_path, roots)}: dependencies must be a list")
        raw_deps = []
    for item in raw_deps:
        if not isinstance(item, dict):
            errors.append(f"{_format_path(manifest_path, roots)}: dependency entry must be an object")
            continue
        dep_id = _string(item.get("id"))
        if not dep_id:
            errors.append(f"{_format_path(manifest_path, roots)}: dependency missing id")
            continue
        version_range = _string(item.get("version_range"))
        dependencies.append(PackDependencySpec(id=dep_id, version_range=version_range))

    if not _string(raw_id):
        errors.append(f"{_format_path(manifest_path, roots)}: missing id")
    if not _string(raw_version):
        errors.append(f"{_format_path(manifest_path, roots)}: missing version")

    manifest = PackManifest(
        id=pack_id,
        version=version,
        title=title,
        description=description,
        engine_compat=engine_compat,
        dependencies=dependencies,
        root=pack_root,
        path=_format_path(manifest_path, roots),
        implicit=False,
    )
    errors.extend(validate_manifest(manifest, roots=roots))
    return manifest, errors


def validate_manifest(manifest: PackManifest, *, roots: list[Path] | None = None) -> list[str]:
    roots = roots or get_content_roots()
    errors: list[str] = []
    if not manifest.id:
        errors.append(f"{manifest.path}: missing id")
    if not manifest.version:
        errors.append(f"{manifest.path}: missing version")
    if manifest.title is not None and not isinstance(manifest.title, str):
        errors.append(f"{manifest.path}: title must be string")
    if manifest.description is not None and not isinstance(manifest.description, str):
        errors.append(f"{manifest.path}: description must be string")
    if manifest.engine_compat is not None and not isinstance(manifest.engine_compat, str):
        errors.append(f"{manifest.path}: engine_compat must be string")
    for dep in manifest.dependencies:
        if not dep.id:
            errors.append(f"{manifest.path}: dependency missing id")
    return errors


def load_all_manifests(*, pack_id: str | None = None) -> tuple[list[PackManifest], list[str]]:
    manifests: list[PackManifest] = []
    errors: list[str] = []
    wanted = _string(pack_id)
    for root in discover_pack_roots():
        manifest, manifest_errors = load_manifest(root)
        if wanted and manifest.id != wanted:
            continue
        manifests.append(manifest)
        errors.extend(manifest_errors)
    manifests.sort(key=lambda m: (m.id, m.path))
    errors.sort()
    return manifests, errors


def resolve_pack_order(manifests: list[PackManifest]) -> tuple[list[PackManifest], list[str]]:
    errors: list[str] = []
    pack_map: dict[str, PackManifest] = {}
    for manifest in manifests:
        if manifest.id in pack_map:
            errors.append(f"duplicate pack id: {manifest.id}")
        else:
            pack_map[manifest.id] = manifest

    adjacency: dict[str, list[str]] = {m.id: [] for m in pack_map.values()}
    in_degree: dict[str, int] = {m.id: 0 for m in pack_map.values()}

    for manifest in pack_map.values():
        for dep in manifest.dependencies:
            dep_id = dep.id
            if dep_id not in pack_map:
                errors.append(f"missing dependency: {manifest.id} requires {dep_id}")
                continue
            dep_manifest = pack_map[dep_id]
            if dep.version_range and dep.version_range not in {"*", ""}:
                if dep_manifest.version != dep.version_range:
                    errors.append(
                        f"version mismatch: {manifest.id} requires {dep_id} {dep.version_range} but found {dep_manifest.version}"
                    )
            adjacency[dep_id].append(manifest.id)
            in_degree[manifest.id] += 1

    order: list[PackManifest] = []
    queue = sorted([pid for pid, deg in in_degree.items() if deg == 0])
    while queue:
        pid = queue.pop(0)
        order.append(pack_map[pid])
        for nxt in sorted(adjacency.get(pid, [])):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
                queue.sort()

    if len(order) != len(pack_map):
        remaining = sorted([pid for pid, deg in in_degree.items() if deg > 0])
        cycle = _find_cycle(adjacency, remaining)
        if cycle:
            errors.append(f"cycle detected: {' -> '.join(cycle)}")
        else:
            errors.append("cycle detected in pack dependencies")
        order = [pack_map[pid] for pid in sorted(pack_map.keys())]

    return order, errors


def _find_cycle(adjacency: dict[str, list[str]], nodes: list[str]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def _dfs(node: str) -> list[str] | None:
        visiting.add(node)
        path.append(node)
        for nxt in adjacency.get(node, []):
            if nxt in visiting:
                cycle_start = path.index(nxt)
                return path[cycle_start:] + [nxt]
            if nxt in visited:
                continue
            cycle = _dfs(nxt)
            if cycle:
                return cycle
        visiting.remove(node)
        visited.add(node)
        path.pop()
        return None

    for node in nodes:
        if node in visited:
            continue
        cycle = _dfs(node)
        if cycle:
            return cycle
    return None
