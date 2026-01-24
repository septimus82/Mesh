import time
import pytest
from engine.scene_loader import SceneLoader


pytestmark = pytest.mark.builtin_behaviours

SCENES_TO_TEST = [
    "packs/core_regions/scenes/Ridge Outpost_hub.json",
    "packs/core_regions/scenes/Ridge Outpost_interior.json",
    "packs/core_regions/scenes/Ridge Outpost_dungeon.json",
    "packs/core_regions/scenes/Hollow Grove_hub.json",
    "packs/core_regions/scenes/Hollow Grove_interior.json",
    "packs/core_regions/scenes/Hollow Grove_dungeon.json",
    "packs/core_regions/scenes/Ashen_hub.json",
    "packs/core_regions/scenes/Ashen_interior.json",
    "packs/core_regions/scenes/Ashen_dungeon.json",
]

def test_core_region_load_perf():
    loader = SceneLoader()
    
    total_time = 0
    for scene_path in SCENES_TO_TEST:
        start = time.perf_counter()
        
        report = loader.validate_scene_file(scene_path)
        
        duration = time.perf_counter() - start
        total_time += duration
        
        assert report.ok, f"Scene {scene_path} failed validation: {report.errors}"
        
        # Assert reasonable load time (e.g. < 200ms per scene for JSON parsing + validation)
        # This is generous for JSON parsing.
        assert duration < 0.2, f"Scene {scene_path} took too long to load: {duration:.4f}s"
        
    print(f"\nTotal load time for {len(SCENES_TO_TEST)} scenes: {total_time:.4f}s")
