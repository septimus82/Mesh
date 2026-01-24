import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.content_audit import ContentAuditor, audit_world

@pytest.fixture
def mock_index():
    with patch("engine.content_audit.get_content_index") as mock:
        index = MagicMock()
        mock.return_value = index
        
        # Mock entries
        index.entries = {
            "assets/sprites/used.png": MagicMock(providing_pack_id="core"),
            "assets/sprites/unused.png": MagicMock(providing_pack_id="core"),
            "assets/prefabs.json": MagicMock(providing_pack_id="core"),
            "config.json": MagicMock(providing_pack_id="core")
        }
        index.roots = [Path(".")]
        yield index

@pytest.fixture
def mock_resolve():
    with patch("engine.content_audit.resolve_path") as mock:
        def side_effect(path):
            return MagicMock(exists=lambda: False)
        mock.side_effect = side_effect
        yield mock

def test_audit_assets(mock_index, mock_resolve):
    # Setup mocks for file existence and content
    files = {
        "worlds/main_world.json": json.dumps({
            "initial_scene": "scenes/start.json"
        }),
        "scenes/start.json": json.dumps({
            "entities": [
                {"sprite": "assets/sprites/used.png"}
            ]
        })
    }
    
    def resolve_side_effect(path):
        m = MagicMock()
        if path in files:
            m.exists.return_value = True
            m.read_text.return_value = files[path]
        elif path == "assets/sprites/used.png" or path == "assets/sprites/unused.png":
             m.exists.return_value = True
        else:
            m.exists.return_value = False
        return m
        
    mock_resolve.side_effect = resolve_side_effect
    
    auditor = ContentAuditor("worlds/main_world.json")
    report = auditor.audit()
    
    # Check used vs unused
    assert "assets/sprites/used.png" in auditor.ref_assets
    assert "assets/sprites/unused.png" not in auditor.ref_assets
    
    # Check report
    unused_paths = [u["path"] for u in report["unused_assets"]]
    assert "assets/sprites/unused.png" in unused_paths
    assert "assets/sprites/used.png" not in unused_paths
    
    # Config files should be ignored
    assert "config.json" not in unused_paths

def test_audit_prefabs(mock_index, mock_resolve):
    files = {
        "assets/prefabs.json": json.dumps([
            {"id": "used_prefab", "entity": {}},
            {"id": "unused_prefab", "entity": {}}
        ]),
        "worlds/main_world.json": json.dumps({
            "initial_scene": "scenes/start.json"
        }),
        "scenes/start.json": json.dumps({
            "entities": [
                {"prefab_id": "used_prefab"}
            ]
        })
    }
    
    def resolve_side_effect(path):
        m = MagicMock()
        if path in files:
            m.exists.return_value = True
            m.read_text.return_value = files[path]
        else:
            m.exists.return_value = False
        return m
        
    mock_resolve.side_effect = resolve_side_effect
    
    auditor = ContentAuditor("worlds/main_world.json")
    report = auditor.audit()
    
    unused_ids = [u["id"] for u in report["unused_prefabs"]]
    assert "unused_prefab" in unused_ids
    assert "used_prefab" not in unused_ids

def test_audit_items_heuristic(mock_index, mock_resolve):
    files = {
        "assets/data/items.json": json.dumps({
            "items": [
                {"id": "potion"},
                {"id": "sword"}
            ]
        }),
        "worlds/main_world.json": json.dumps({
            "initial_scene": "scenes/start.json"
        }),
        "scenes/start.json": json.dumps({
            "entities": [
                # Heuristic usage in dialogue
                {"dialogue": "Here, take this potion."}
            ]
        })
    }
    
    def resolve_side_effect(path):
        m = MagicMock()
        if path in files:
            m.exists.return_value = True
            m.read_text.return_value = files[path]
        else:
            m.exists.return_value = False
        return m
        
    mock_resolve.side_effect = resolve_side_effect
    
    auditor = ContentAuditor("worlds/main_world.json")
    report = auditor.audit()
    
    unused_ids = [u["id"] for u in report["unused_items"]]
    assert "sword" in unused_ids
    assert "potion" not in unused_ids # Should be found via heuristic
