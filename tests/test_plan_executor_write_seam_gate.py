import json
import pytest
import builtins
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Plan
from engine.tooling.plan_linter import WRITING_ACTIONS, NON_WRITING_ACTIONS
import engine.paths

# --- Configuration ---

def get_all_actions():
    """Load all actions defined in plan_schema.json."""
    schema_path = Path("plan_schema.json")
    if not schema_path.exists():
        pytest.fail("plan_schema.json not found")
    
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    return set(data.get("actions", {}).keys())

def test_action_discovery_guard():
    """Ensure all known actions are categorized as writing or non-writing."""
    all_actions = get_all_actions()
    
    # Check for unknown actions
    uncategorized = all_actions - WRITING_ACTIONS - NON_WRITING_ACTIONS
    assert not uncategorized, f"New actions detected! Please categorize them in engine/tooling/plan_linter.py: {uncategorized}"
    
    # Check for removed actions (optional, but good for hygiene)
    missing = (WRITING_ACTIONS | NON_WRITING_ACTIONS) - all_actions
    if missing:
        print(f"Warning: Actions listed in linter but missing from schema: {missing}")

def test_all_writing_actions_use_seam(tmp_path, monkeypatch):
    """Verify that all writing actions use the _write_file seam."""
    
    # Clear path cache
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None
    
    monkeypatch.chdir(tmp_path)
    
    # --- Setup Environment ---
    pack_root = tmp_path / "packs" / "core"
    scenes_dir = pack_root / "scenes"
    scenes_dir.mkdir(parents=True)
    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    
    # 1. Create initial files needed for actions
    
    # Hub Scene (for add_npc, add_transition, polish_scene)
    hub_path = scenes_dir / "Hub.json"
    hub_data = {
        "name": "Hub",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "hub"},
        "entities": [
            {"name": "Guard", "x": 100, "y": 100, "behaviours": ["Dialogue"], "dialogue": {"lines": ["Old"]}}
        ]
    }
    hub_path.write_text(json.dumps(hub_data, indent=2), encoding="utf-8")
    
    # Interior Scene (for add_puzzle)
    interior_path = scenes_dir / "Interior.json"
    interior_data = {
        "name": "Interior",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "interior"},
        "entities": []
    }
    interior_path.write_text(json.dumps(interior_data, indent=2), encoding="utf-8")
    
    # World (for wire_world, auto_wire)
    world_path = worlds_dir / "world.json"
    world_data = {
        "scenes": {
            "hub": {"path": str(hub_path)},
            "interior": {"path": str(interior_path)}
        }
    }
    world_path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")
    
    # Quest file (for create_quest - usually it appends, but we can start empty or non-existent)
    quests_path = pack_root / "quests.json"
    
    # --- Construct Plan with ALL Writing Actions ---
    
    actions = [
        {
            "type": "init_pack",
            "args": {"path": str(tmp_path / "packs" / "new_pack"), "id": "new_pack"},
            "description": "Init Pack"
        },
        {
            "type": "create_scene",
            "args": {"path": str(scenes_dir / "NewScene.json"), "template": "empty"},
            "description": "Create Scene"
        },
        {
            "type": "add_npc",
            "args": {"scene_path": str(hub_path), "name": "Guard2", "role": "guard", "x": 100, "y": 100},
            "description": "Add NPC"
        },
        {
            "type": "create_quest",
            "args": {"path": str(quests_path), "id": "quest_1", "title": "Quest 1", "type": "main"},
            "description": "Create Quest"
        },
        {
            "type": "wire_world",
            "args": {"world_path": str(world_path), "scene_id": "new_scene", "scene_path": str(scenes_dir / "NewScene.json")},
            "description": "Wire World"
        },
        {
            "type": "polish_scene",
            "args": {"path": str(hub_path), "compact_only": True}, # Use compact_only to avoid validation issues in test
            "description": "Polish Scene"
        },
        {
            "type": "add_puzzle_switch_door",
            "args": {"scene_path": str(interior_path), "switch": {"x": 10, "y": 10}, "door": {"x": 20, "y": 20}},
            "description": "Add Puzzle"
        },
        {
            "type": "add_transition",
            "args": {"scene_path": str(hub_path), "target_scene": "packs/core/scenes/Interior.json", "x": 50, "y": 50},
            "description": "Add Transition"
        },
        {
            "type": "add_npc_dialogue",
            "args": {"scene_path": str(hub_path), "npc_name": "Guard", "lines": ["Hello"]},
            "description": "Add Dialogue"
        },
        # Auto wire is complex, it requires AutoWireController. 
        # We need to mock AutoWireController or ensure it uses the writer.
        # PlanExecutor._auto_wire_transitions passes self._write_file to AutoWireController.
        # So we just need to trigger it.
        {
            "type": "auto_wire_transitions",
            "args": {"world_path": str(world_path)},
            "description": "Auto Wire"
        }
    ]
    
    # Calculate touches for AI Safe Mode
    touches = [
        str(tmp_path / "packs" / "new_pack").replace("\\", "/"), # For init_pack
        str(tmp_path / "packs" / "new_pack" / "manifest.json").replace("\\", "/"), # For actual write (optional but good)
        str(scenes_dir / "NewScene.json").replace("\\", "/"),
        str(hub_path).replace("\\", "/"),
        str(quests_path).replace("\\", "/"),
        str(world_path).replace("\\", "/"),
        str(interior_path).replace("\\", "/")
    ]
    
    plan_dict = {
        "actions": actions,
        "inputs": {
            "meta": {
                "touches": touches
            }
        }
    }
    plan = Plan.from_dict(plan_dict)
    
    # --- Execution with Writer Capture ---
    captured_writes = {} # Map path -> list of contents
    def capture_writer(path: Path, content: str):
        p = str(path)
        if p not in captured_writes:
            captured_writes[p] = []
        captured_writes[p].append(content)
        
    executor = PlanExecutor(dry_run=False, writer=capture_writer)
    # Disable backups
    executor.backup_mgr.backup_file = lambda p: None
    
    # Mock AutoWireController to avoid complex logic but verify it receives writer
    # Actually, we want to test that PlanExecutor passes the writer.
    # If we mock it, we can verify the call args.
    # But if we want to verify it WRITES via seam, we need it to actually call writer.
    # Let's let it run. It might not write anything if no transitions are needed.
    # To force a write, we'd need a transition that needs wiring.
    # We added a transition in "Add Transition" step (hub -> interior).
    # So auto_wire should pick it up and try to modify hub/interior/world.
    
    # However, auto_wire loads scenes from disk. 
    # Since we are intercepting writes, the "Add Transition" change is NOT on disk.
    # So AutoWire will NOT see the new transition.
    # This is a limitation of the test structure (sequential actions where subsequent actions depend on previous writes).
    
    # To fix this, we can either:
    # 1. Update the disk files manually in the test before running (but we want to test the executor).
    # 2. Accept that auto_wire won't do anything, but verify it doesn't crash or write directly.
    # 3. Mock AutoWireController to just write a dummy file using the passed writer.
    
    with patch("engine.tooling.auto_wire.AutoWireController") as MockAutoWire:
        instance = MockAutoWire.return_value
        instance.process.return_value = [] # No changes reported
        instance.modified_scenes = []
        instance.scene_paths = {}
        
        # We want to verify it was initialized with our writer
        
        # --- Strong Check: Monkeypatch open ---
        original_open = builtins.open
        
        def guarded_open(file, mode="r", *args, **kwargs):
            if "w" in mode or "a" in mode or "x" in mode or "+" in mode:
                # Allow creating directories? No, open is for files.
                # Allow logging?
                raise RuntimeError(f"Direct write detected to {file} with mode {mode}")
            return original_open(file, mode, *args, **kwargs)
            
        def guarded_mkdir(self, *args, **kwargs):  # noqa: ARG001
            raise RuntimeError(f"Path.mkdir called in writer-capture mode: {self}")

        monkeypatch.setattr(Path, "mkdir", guarded_mkdir, raising=True)

        with patch("builtins.open", side_effect=guarded_open):
            executor.execute(plan, ai_safe=True)
            
        # Verify AutoWire got the writer
        # PlanExecutor instantiates AutoWireController(world_path, writer=self._write_file)
        # self._write_file is a bound method.
        # We can check if the writer arg was passed.
        args, kwargs = MockAutoWire.call_args
        assert "writer" in kwargs
        assert kwargs["writer"] == executor._write_file
        
    # --- Assertions ---
    
    # Verify all expected files were written to captured_writes
    
    # 1. Init Pack
    manifest_path = tmp_path / "packs" / "new_pack" / "manifest.json"
    assert str(manifest_path) in captured_writes
    
    # 2. Create Scene
    new_scene_path = scenes_dir / "NewScene.json"
    assert str(new_scene_path) in captured_writes
    
    # 3. Add NPC (Hub)
    assert str(hub_path) in captured_writes
    # Check that one of the writes contains Guard2
    hub_writes = captured_writes[str(hub_path)]
    assert any("Guard2" in w for w in hub_writes), "add_npc should write Guard2"
    
    # 4. Create Quest
    assert str(quests_path) in captured_writes
    
    # 5. Wire World (World)
    assert str(world_path) in captured_writes
    
    # 6. Polish Scene (Hub)
    # Should be in hub_writes
    
    # 7. Add Puzzle (Interior)
    assert str(interior_path) in captured_writes
    
    # 8. Add Transition (Hub)
    assert any("SceneTransition" in w for w in hub_writes), "add_transition should write SceneTransition"
    
    # 9. Add Dialogue (Hub)
    # Check that one of the writes contains the new dialogue
    # We updated "Guard" with "Hello"
    assert any("Hello" in w for w in hub_writes), "add_npc_dialogue should write Hello"
