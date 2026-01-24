import json
import os
import pytest
from pathlib import Path
from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Plan
import engine.paths

def test_auto_wire_target_scene_contract(tmp_path, monkeypatch):
    # Clear path cache to ensure we use tmp_path
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None
    
    monkeypatch.chdir(tmp_path)
    
    # Setup directory structure
    pack_root = tmp_path / "packs" / "core_regions"
    scenes_dir = pack_root / "scenes"
    scenes_dir.mkdir(parents=True)
    
    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    
    # Create scenes
    hub_path = scenes_dir / "Hub.json"
    interior_path = scenes_dir / "Interior.json"
    world_path = worlds_dir / "w.json"
    
    hub_data = {
        "name": "Hub",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "hub"},
        "entities": []
    }
    hub_path.write_text(json.dumps(hub_data, indent=2), encoding="utf-8")
    
    interior_data = {
        "name": "Interior",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "interior"},
        "entities": []
    }
    interior_path.write_text(json.dumps(interior_data, indent=2), encoding="utf-8")
    
    # Create world
    world_data = {
        "scenes": {
            "region_hub": {"path": str(hub_path)},
            "region_interior": {"path": str(interior_path)}
        }
    }
    world_path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")
    
    # Create Plan
    plan_dict = {
        "actions": [
            {
                "type": "auto_wire_transitions",
                "args": {
                    "world_path": str(world_path)
                },
                "description": "Auto Wire"
            }
        ],
        "inputs": {
            "meta": {
                "touches": [
                    str(hub_path).replace("\\", "/"), 
                    str(interior_path).replace("\\", "/"),
                    str(world_path).replace("\\", "/")
                ]
            }
        }
    }
    plan = Plan.from_dict(plan_dict)
    
    # Execute Plan
    executor = PlanExecutor(dry_run=False)
    # Disable backups to avoid MAX_PATH issues with deep tmp paths
    executor.backup_mgr.backup_file = lambda p: None
    executor.execute(plan, ai_safe=True)
    
    # Verify Contract
    def verify_scene(path: Path):
        content = json.loads(path.read_text(encoding="utf-8"))
        transitions = []
        
        # Helper to extract transitions
        def check_entities(entity_list):
            for entity in entity_list:
                # Check behaviours list
                if "SceneTransition" in entity.get("behaviours", []):
                    cfg = entity.get("behaviour_config", {}).get("SceneTransition", {})
                    if "target_scene" in cfg:
                        transitions.append(cfg["target_scene"])
        
        if "entities" in content:
            check_entities(content["entities"])
            
        if "layers" in content:
            for layer in content["layers"]:
                if isinstance(layer, dict) and "entities" in layer:
                    # entities in layer can be dict or list
                    ents = layer["entities"]
                    if isinstance(ents, dict):
                        check_entities(ents.values())
                    elif isinstance(ents, list):
                        check_entities(ents)
                        
        assert len(transitions) > 0, f"No transitions found in {path}"
        
        for target in transitions:
            print(f"Checking target: {target}")
            
            # 1. Not absolute
            assert not os.path.isabs(target), f"Target is absolute: {target}"
            
            # 2. No '..'
            assert ".." not in target, f"Target contains '..': {target}"
            
            # 3. Forward slashes only
            assert "\\" not in target, f"Target contains backslashes: {target}"
            
            # 4. Starts with packs/ (since we put them in packs/)
            assert target.startswith("packs/"), f"Target does not start with packs/: {target}"
            
            # 5. Ends with .json
            assert target.endswith(".json"), f"Target does not end with .json: {target}"

    verify_scene(hub_path)
    verify_scene(interior_path)
