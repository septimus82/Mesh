"""Content lockfile and fingerprinting system."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine import json_io
from engine.paths import get_content_index, resolve_path
from engine.version import ENGINE_VERSION


_MESH_LOCK_LOGGED_ONCE: set[str] = set()


def _mesh_lock_log_once(key: str, exc: Exception, *, context: str = "") -> None:
    if key in _MESH_LOCK_LOGGED_ONCE:
        return
    _MESH_LOCK_LOGGED_ONCE.add(key)
    suffix = f" ({context})" if context else ""
    print(f"[Mesh][Lock] ERROR {key}{suffix}: {exc}")


def _hash_file(path: Path) -> Optional[str]:
    """Compute SHA-256 hash of a file."""
    if not path.exists():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    except Exception as exc:  # noqa: BLE001
        _mesh_lock_log_once("hash_file", exc, context=str(path))
        return None

def _get_referenced_scenes(world_path: Path) -> List[str]:
    """Extract referenced scenes from a world file."""
    scenes = set()
    if not world_path.exists():
        return []

    try:
        world_data = json.loads(world_path.read_text(encoding="utf-8"))

        # Initial scene
        if "initial_scene" in world_data:
            scenes.add(world_data["initial_scene"])

        # Map nodes
        for node in world_data.get("map_nodes", {}).values():
            if "scene_file" in node:
                scenes.add(node["scene_file"])

        # Scenes dict
        for s_def in world_data.get("scenes", {}).values():
            if "path" in s_def:
                scenes.add(s_def["path"])
    except Exception as exc:  # noqa: BLE001
        _mesh_lock_log_once("referenced_scenes", exc, context=str(world_path))

    return sorted(list(scenes))

def build_lock(world_path: str = "worlds/main_world.json") -> Dict[str, Any]:
    """Generate a lock dictionary representing the current content state."""
    index = get_content_index(refresh=True)
    index.build()

    packs_data = []
    for p in index.packs:
        # Try to make root relative to CWD for portability
        try:
            root_str = str(p.root.relative_to(Path.cwd()))
        except ValueError:
            root_str = str(p.root)

        packs_data.append({
            "id": p.id,
            "version": p.version,
            "type": p.type,
            "root": root_str,
            "requires": [{"id": r.id, "min": r.min_version, "max": r.max_version} for r in p.requires],
            "load_after": sorted(p.load_after),
            "load_before": sorted(p.load_before),
            "is_implicit": p.is_implicit
        })

    # Override summary
    # We store a deterministic map of overrides
    overrides = {}
    for key, entry in sorted(index.entries.items()):
        if entry.shadowed_pack_ids:
            overrides[key] = {
                "provider": entry.providing_pack_id,
                "shadowed": sorted(entry.shadowed_pack_ids)
            }

    # Content Files Hashing
    content_files = {}

    # 1. Key Data Files
    files_to_hash = [
        world_path,
        "assets/data/quests.json",
        "assets/data/items.json",
        "assets/prefabs.json",
        "assets/data/events.json"
    ]

    for f_str in files_to_hash:
        file_path = resolve_path(f_str)
        h = _hash_file(file_path)
        if h:
            content_files[f_str] = h

    # 2. Referenced Scenes
    w_p = resolve_path(world_path)
    for s_str in _get_referenced_scenes(w_p):
        scene_path = resolve_path(s_str)
        h = _hash_file(scene_path)
        if h:
            content_files[s_str] = h

    # 3. Audit Snapshot (Lightweight)
    # We compute a quick audit to store counts.
    # This allows baseline comparisons without full re-audit.
    from engine.content_audit import audit_world
    # We use default ignore patterns here, or maybe none?
    # Ideally we want the raw counts.
    try:
        # This might be slow for huge projects, but for now it's fine.
        # We suppress output and just get stats.
        report = audit_world(world_path)
        audit_snapshot = report["stats"]
    except Exception as exc:  # noqa: BLE001
        _mesh_lock_log_once("audit_snapshot", exc, context=str(world_path))
        audit_snapshot = {}

    return {
        "version": 1,
        "engine_version": ENGINE_VERSION,
        "packs": packs_data,
        "overrides": overrides,
        "content_files": content_files,
        "audit_snapshot": audit_snapshot
    }

def write_lock(path: Path, lock_data: Dict[str, Any]) -> None:
    """Write lock data to a file."""
    json_io.write_json_atomic(path, lock_data)

def read_lock(path: Path) -> Dict[str, Any]:
    """Read lock data from a file."""
    raw = json_io.read_json(path)
    return raw if isinstance(raw, dict) else {}

def compute_content_fingerprint(lock_data: Dict[str, Any]) -> str:
    """Compute a SHA-256 fingerprint of the content state."""
    # Since build_lock now includes hashes of key content files,
    # we can just hash the lock data structure itself.
    hasher = hashlib.sha256()
    hasher.update(json_io.dumps_stable(lock_data).encode("utf-8"))
    return hasher.hexdigest()


def compute_strict_fingerprint(lock_data: Dict[str, Any]) -> str:
    """Compute a strict, deterministic fingerprint based only on key content files."""
    # Only consider the 'content_files' section which contains hashes of:
    # - World file
    # - Referenced scenes
    # - Key data files (quests, items, prefabs, events)
    content_files = lock_data.get("content_files", {})

    hasher = hashlib.sha256()
    # Sort keys to ensure determinism
    hasher.update(json_io.dumps_stable(content_files).encode("utf-8"))
    return hasher.hexdigest()
