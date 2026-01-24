import json
from pathlib import Path
from typing import Optional

from engine.content_audit import audit_world
from engine.content_lock import read_lock, write_lock
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload
from engine.tooling import graph
from engine.tooling.validate_all import UnifiedValidator


def generate_polished_scene_data(path: Path) -> dict:
    """Load and compact a scene, returning the data dict."""
    with path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(raw_data)
    compacted = compact_scene_payload(full_scene)
    return compacted


def polish_scene(path: Path, strict_compact: bool = True) -> bool:
    """Load, compact, save, and validate a scene."""
    print(f"[Mesh][Polish] Polishing scene: {path}")

    try:
        # 1. Load and Compact
        compacted = generate_polished_scene_data(path)

        # 2. Write back
        with path.open("w", encoding="utf-8") as f:
            json.dump(compacted, f, indent=2, sort_keys=False)

        # 3. Validate
        validator = UnifiedValidator(Path("."))
        if not validator.validate_scene(path):
            print(f"[Mesh][Polish] Validation FAILED for {path}")
            validator.print_report()
            return False

        print(f"[Mesh][Polish] Successfully polished {path}")
        return True

    except Exception as e:
        print(f"[Mesh][Polish] ERROR processing {path}: {e}")
        return False

def polish_world(path: Path, compact_scenes: bool = False, export_graph_path: Optional[str] = None) -> bool:
    """Validate world, optionally compact referenced scenes and export graph."""
    print(f"[Mesh][Polish] Polishing world: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            world_data = json.load(f)

        # 1. Validate World
        validator = UnifiedValidator(Path("."))
        if not validator.validate_world(path, world_data):
            print("[Mesh][Polish] World validation FAILED")
            validator.print_report()
            return False

        # 2. Compact Scenes if requested
        if compact_scenes:
            scenes = world_data.get("scenes", {})
            for key, scene_def in scenes.items():
                scene_path_str = scene_def.get("path")
                if scene_path_str:
                    scene_path = Path(scene_path_str)
                    if scene_path.exists():
                        if not polish_scene(scene_path):
                            print(f"[Mesh][Polish] WARNING: Failed to polish referenced scene '{key}'")
                    else:
                        print(f"[Mesh][Polish] WARNING: Referenced scene '{key}' not found at {scene_path}")

        # 3. Export Graph if requested
        if export_graph_path:
            graph.export_graph(str(path), export_graph_path)

        print(f"[Mesh][Polish] Successfully polished world {path}")
        return True

    except Exception as e:
        print(f"[Mesh][Polish] ERROR processing world {path}: {e}")
        return False

def main(path_str: str, compact_scenes: bool = False, export_graph_path: Optional[str] = None, update_lock_audit: bool = False) -> int:
    path = Path(path_str)
    if not path.exists():
        print(f"[Mesh][Polish] File not found: {path}")
        return 1

    # Detect type
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Mesh][Polish] Failed to parse JSON: {e}")
        return 1

    success = False
    if "scenes" in data and "links" in data:
        # It's a world
        success = polish_world(path, compact_scenes, export_graph_path)
    else:
        # Assume it's a scene
        success = polish_scene(path)

    if success and update_lock_audit:
        lock_path = Path("content.lock.json")
        if lock_path.exists():
            print("[Mesh][Polish] Updating audit snapshot in content.lock.json...")
            try:
                lock_data = read_lock(lock_path)
                # Assuming main_world.json or the polished world if it is one?
                # If we polished a scene, we should audit the main world to see impact.
                # If we polished a world, we should audit that world.
                # Let's default to "worlds/main_world.json" if the polished file is not a world,
                # or use the polished file if it is a world.

                audit_target = "worlds/main_world.json"
                if "scenes" in data and "links" in data:
                    audit_target = str(path)

                report = audit_world(audit_target)
                lock_data["audit_snapshot"] = report["stats"]
                write_lock(lock_path, lock_data)
                print("[Mesh][Polish] Audit snapshot updated.")
            except Exception as e:
                print(f"[Mesh][Polish] WARNING: Failed to update audit snapshot: {e}")
        else:
            print("[Mesh][Polish] content.lock.json not found, skipping audit update.")

    return 0 if success else 1
