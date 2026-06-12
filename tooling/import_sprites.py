"""
Tool to scan assets/sprites and auto-generate prefab entries in assets/prefabs.json.
Usage: python tooling/import_sprites.py
"""

import json
import os
from pathlib import Path

from engine import json_io

ASSETS_DIR = Path("assets")
SPRITES_DIR = ASSETS_DIR / "sprites"
PREFABS_FILE = ASSETS_DIR / "prefabs.json"

def scan_and_import():
    if not SPRITES_DIR.exists():
        print(f"Creating {SPRITES_DIR}...")
        SPRITES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load existing prefabs
    existing_prefabs = []
    if PREFABS_FILE.exists():
        try:
            with open(PREFABS_FILE, "r", encoding="utf-8") as f:
                existing_prefabs = json.load(f)
        except Exception as e:
            print(f"Error reading {PREFABS_FILE}: {e}")
            return

    # Track existing IDs to avoid duplicates
    existing_ids = {p["id"] for p in existing_prefabs}
    existing_sprites = {p["entity"].get("sprite") for p in existing_prefabs}

    new_entries = []

    # 2. Scan for images
    print(f"Scanning {SPRITES_DIR}...")
    for file_path in SPRITES_DIR.glob("*.*"):
        if file_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp"):
            continue

        # Relativize path for the engine (e.g. "assets/sprites/tree.png")
        # We need to be careful with separators on Windows
        rel_path = str(file_path).replace(os.sep, "/")

        # Check if already imported
        if rel_path in existing_sprites:
            continue

        # Generate ID from filename (e.g. "tree.png" -> "tree")
        name_stem = file_path.stem
        clean_id = "".join(c for c in name_stem if c.isalnum() or c == "_").lower()

        # Ensure unique ID
        original_id = clean_id
        counter = 1
        while clean_id in existing_ids:
            clean_id = f"{original_id}_{counter}"
            counter += 1

        # Create default entity definition
        display_name = name_stem.replace("_", " ").title()

        new_prefab = {
            "id": clean_id,
            "display_name": display_name,
            "entity": {
                "name": display_name,
                "sprite": rel_path,
                "solid": True, # Default to solid, easy to change in editor
                "layer": "entities",
                "behaviours": []
            }
        }

        new_entries.append(new_prefab)
        existing_ids.add(clean_id)
        print(f"  [+] Found new sprite: {rel_path} -> ID: {clean_id}")

    if not new_entries:
        print("No new sprites found.")
        return

    # 3. Save back to prefabs.json
    all_prefabs = existing_prefabs + new_entries

    try:
        json_io.write_json_atomic(PREFABS_FILE, all_prefabs)
        print(f"Successfully added {len(new_entries)} new prefabs to {PREFABS_FILE}")
    except Exception as e:
        print(f"Failed to write prefabs file: {e}")

if __name__ == "__main__":
    scan_and_import()
