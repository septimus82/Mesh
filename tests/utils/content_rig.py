import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def create_minimal_pack(tmpdir: Path, pack_id: str, type: str = "mod", wip: bool = False) -> Path:
    """Create a minimal content pack in the given directory."""
    pack_dir = tmpdir / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": pack_id,
        "version": "1.0.0",
        "type": type,
        "wip": wip,
        "dependencies": []
    }

    (pack_dir / "pack.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return pack_dir

def create_minimal_world(tmpdir: Path, pack_id: Optional[str] = None, with_vertical_slice: bool = False) -> Path:
    """Create a minimal world file."""
    world_data = {
        "id": "test_world",
        "scenes": [],
        "packs": [pack_id] if pack_id else []
    }

    if with_vertical_slice:
        # Add some dummy scenes if requested
        world_data["scenes"].append({"path": "scenes/start.json"})

    world_path = tmpdir / "world.json"
    world_path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")
    return world_path

def create_lockfile(tmpdir: Path, world_path: Path, packs: Optional[List[Dict[str, Any]]] = None) -> Path:
    """Create a content.lock.json file."""
    lock_data = {
        "version": 1,
        "packs": packs or [],
        "overrides": {"total_delta": 0},
        "content_files": {"changed": [], "added": [], "removed": []},
        "audit_snapshot": {
            "unused_assets_count": 0,
            "unused_prefabs_count": 0,
            "unused_items_count": 0,
            "unused_quests_count": 0
        }
    }

    lock_path = tmpdir / "content.lock.json"
    lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
    return lock_path
