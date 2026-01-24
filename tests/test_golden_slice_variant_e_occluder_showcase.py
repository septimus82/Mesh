import pytest
import json
from pathlib import Path

def test_golden_slice_variant_e_occluder_showcase():
    """
    Strict invariant for Variant E:
    - Must have at least 3 occluders.
    - Must have at least one occluder strictly between Entrance and Boss.
    """
    scene_path = Path("packs/core_regions/scenes/Ridge Outpost_dungeon_variant_e.json")
    if not scene_path.exists():
        pytest.fail(f"Scene file not found: {scene_path}")

    with open(scene_path, "r") as f:
        scene_data = json.load(f)

    # 1. Find Entities
    entities = scene_data.get("entities", [])
    boss = next((e for e in entities if e.get("name") == "Boss"), None)
    entrance = next((e for e in entities if e.get("name") == "Entrance"), None)

    assert boss is not None, "Boss entity missing from Variant E"
    
    # If Entrance is missing, we assume 0 as per instructions, but let's try to find it first.
    entrance_x = entrance["x"] if entrance else 0
    boss_x = boss["x"]

    # Ensure we have a valid range (Entrance should be left of Boss for this test to make sense)
    # If boss is to the left, we swap for the check range, but the requirement says "between entrance and boss".
    # Usually entrance is left (x=50) and boss is right (x=600).
    min_x = min(entrance_x, boss_x)
    max_x = max(entrance_x, boss_x)

    # 2. Check Occluder Count
    occluders = scene_data.get("occluders", [])
    assert len(occluders) >= 3, f"Variant E must have at least 3 occluders, found {len(occluders)}"

    # 3. Check for Blocking Occluder
    # "Assert there exists at least one occluder whose bounding box x-range lies strictly between entrance x and boss x."
    # Strictly between means: occluder_min_x > min_x AND occluder_max_x < max_x
    
    blocking_occluder_found = False
    
    for occluder in occluders:
        occ_type = occluder.get("type")
        occ_min_x = 0
        occ_max_x = 0
        
        if occ_type == "rect":
            x = occluder.get("x", 0)
            w = occluder.get("width", 0)
            # In Mesh engine, rects are usually defined by bottom-left or center? 
            # Looking at previous files (e.g. Ridge Outpost_dungeon_variant_e.json):
            # "x": 200, "y": 200, "width": 20, "height": 200
            # Standard Arcade/Mesh rects are often bottom-left origin for Tiled, but let's assume x is left edge 
            # or check engine code. However, for "x..x+w" logic, let's assume x is min_x.
            # If x was center, it would be x - w/2. 
            # Let's check how other tests or engine handles it. 
            # But the prompt says: "For rect occluders: use x..x+w" -> This implies x is left edge.
            occ_min_x = x
            occ_max_x = x + w
            
        elif occ_type == "poly":
            points = occluder.get("points", [])
            if not points:
                continue
            xs = [p[0] for p in points]
            occ_min_x = min(xs)
            occ_max_x = max(xs)
        else:
            continue

        # Check strictly between
        if occ_min_x > min_x and occ_max_x < max_x:
            blocking_occluder_found = True
            break

    assert blocking_occluder_found, (
        f"No occluder found strictly between Entrance (x={entrance_x}) and Boss (x={boss_x}). "
        f"Occluders: {occluders}"
    )
