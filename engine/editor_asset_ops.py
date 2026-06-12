"""Editor operations for assets."""

from __future__ import annotations

from pathlib import Path


def spawn_entity_from_asset(
    scene_json: dict,
    rel_path: str,
    pos: tuple[float, float]
) -> tuple[dict, str]:
    """
    Spawns a new entity in the scene from an asset path.
    
    Args:
        scene_json: The current scene data dictionary.
        rel_path: Relative path to the asset (e.g. 'assets/sprites/char.png').
        pos: World position (x, y) to spawn at.
        
    Returns:
        tuple (updated_scene_json, new_entity_id)
    """
    # Ensure entities dict exists
    if "entities" not in scene_json:
        scene_json["entities"] = {}

    entities = scene_json["entities"]

    # Generate ID: asset_{filename}_{n}
    path_obj = Path(rel_path)
    stem = path_obj.stem
    # sanitize stem
    safe_stem = "".join(c if c.isalnum() else "_" for c in stem)
    base_id = f"asset_{safe_stem}"

    # Find next available suffix
    n = 1
    new_id = f"{base_id}_{n}"
    while new_id in entities:
        n += 1
        new_id = f"{base_id}_{n}"

    # Create entity
    new_entity = {
        "x": pos[0],
        "y": pos[1],
        "texture": rel_path,
        # Default some useful fields
        "scale": 1.0,
        "layer": "instances" # Default sorting layer
    }

    entities[new_id] = new_entity

    return scene_json, new_id
