import argparse
import json
from pathlib import Path
from typing import Any, Dict

from engine.migrations import migrate_payload
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload


def detect_type(path: Path, data: Dict[str, Any]) -> str:
    """Heuristic to detect content type."""
    if "scenes" in data and "links" in data:
        return "world"
    if "entities" in data and "layers" in data:
        return "scene"
    if "quests" in data or (isinstance(data, dict) and all(isinstance(v, dict) and "id" in v for v in data.values())):
        # Quests can be wrapped or raw dict
        return "quests"
    if "prefabs" in data:
        return "prefabs"
    if "events" in data:
        return "events"

    # Fallback by extension/name
    name = path.name.lower()
    if "quest" in name:
        return "quests"
    if "prefab" in name:
        return "prefabs"
    if "event" in name:
        return "events"
    if "world" in name:
        return "world"

    return "unknown"

def handle_migrate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"[Mesh][Migrate] File not found: {path}")
        return 1

    # Special case for trace (JSONL)
    if path.suffix == ".jsonl":
        print(f"[Mesh][Migrate] Migrating trace file: {path}")
        # We can't easily rewrite JSONL in place without reading all
        # For now, just read and print count
        from engine.tooling.event_trace import read_event_jsonl
        count = 0
        for _ in read_event_jsonl(str(path)):
            count += 1
        print(f"[Mesh][Migrate] Read {count} events (migrations applied in memory)")
        if args.write:
            print("[Mesh][Migrate] WARNING: --write not supported for traces yet")
        return 0

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Mesh][Migrate] Failed to load JSON: {e}")
        return 1

    content_type = detect_type(path, data)
    if content_type == "unknown":
        print(f"[Mesh][Migrate] Could not detect content type for {path}")
        return 1

    print(f"[Mesh][Migrate] Detected type: {content_type}")

    try:
        migrated = migrate_payload(content_type, data)
    except Exception as e:
        print(f"[Mesh][Migrate] Migration failed: {e}")
        return 1

    if args.write:
        # Special handling for scenes to keep them compact
        if content_type == "scene":
            # We need to load it fully to apply defaults, then compact it?
            # Or just save the migrated structure?
            # If migration adds fields, we want to save them.
            # But we don't want to save default fields.
            # Let's assume migration operates on the raw structure.
            # If we want to compact, we should use scene_serializer.

            # For now, just dump the migrated data, but maybe try to compact if it's a scene
            # To compact, we need to know defaults.
            loader = SceneLoader()
            full = loader.apply_scene_defaults(migrated)
            final_data = compact_scene_payload(full)
        else:
            final_data = migrated

        with path.open("w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2)
        print(f"[Mesh][Migrate] Saved to {path}")
    else:
        print("[Mesh][Migrate] Migration successful (dry run)")
        # Print diff or summary?

    return 0
