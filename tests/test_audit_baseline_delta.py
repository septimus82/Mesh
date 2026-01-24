import pytest
import json
from pathlib import Path
from engine.content_audit import ContentAuditor, audit_world
from engine.tooling.content_commands import _check_thresholds
from argparse import Namespace

def test_audit_categories(tmp_path):
    """Test that assets are correctly categorized."""
    # Setup a mock world and assets
    world_file = tmp_path / "world.json"
    world_file.write_text(json.dumps({"scenes": {}}))
    
    # Create dummy assets
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/tex.png").touch()
    (tmp_path / "assets/sound.wav").touch()
    (tmp_path / "assets/data.json").touch()
    (tmp_path / "assets/unknown.xyz").touch()
    
    # Mock available files in auditor
    auditor = ContentAuditor(str(world_file))
    auditor.available_files = {
        str(tmp_path / "assets/tex.png"): "core",
        str(tmp_path / "assets/sound.wav"): "core",
        str(tmp_path / "assets/data.json"): "core",
        str(tmp_path / "assets/unknown.xyz"): "core"
    }
    # No references
    
    report = auditor._build_report()
    stats = report["stats"]
    
    assert stats["unused_assets_count"] == 3 # .xyz is skipped by extension filter in _build_report?
    # Wait, _build_report filters by extension.
    # asset_extensions = {".png", ".jpg", ".wav", ".ogg", ".mp3", ".json"}
    # So .xyz is skipped.
    
    cats = stats["unused_by_category"]
    assert cats["texture"] == 1
    assert cats["audio"] == 1
    assert cats["data"] == 1
    assert "other" not in cats

def test_audit_allow_packs(tmp_path):
    """Test that allow_packs excludes assets from audit."""
    world_file = tmp_path / "world.json"
    world_file.write_text(json.dumps({"scenes": {}}))
    
    auditor = ContentAuditor(str(world_file))
    auditor.available_files = {
        "assets/core_tex.png": "core",
        "assets/mod_tex.png": "mod_pack"
    }
    
    # Audit with allow_packs
    report = auditor._build_report(allow_packs=["mod_pack"])
    stats = report["stats"]
    
    assert stats["unused_assets_count"] == 1
    assert report["unused_assets"][0]["path"] == "assets/core_tex.png"

def test_check_thresholds_delta():
    """Test delta threshold enforcement."""
    stats = {"unused_assets_count": 105}
    deltas = {"unused_assets_count": 5}
    policy = {}
    
    # Case 1: No limit
    args = Namespace(
        max_unused_assets=None, max_unused_prefabs=None, 
        max_unused_items=None, max_unused_quests=None,
        max_unused_textures=None, max_unused_audio=None, max_unused_data=None,
        max_unused_delta=None, fail_on_unused=False
    )
    assert not _check_thresholds(args, stats, policy, deltas, silent=True)
    
    # Case 2: Delta limit exceeded
    args.max_unused_delta = 2
    assert _check_thresholds(args, stats, policy, deltas, silent=True)
    
    # Case 3: Delta limit met
    args.max_unused_delta = 5
    assert not _check_thresholds(args, stats, policy, deltas, silent=True)
    
    # Case 4: Delta limit met (higher)
    args.max_unused_delta = 10
    assert not _check_thresholds(args, stats, policy, deltas, silent=True)

def test_check_thresholds_category():
    """Test category threshold enforcement."""
    stats = {
        "unused_assets_count": 10,
        "unused_by_category": {
            "texture": 8,
            "audio": 2
        }
    }
    policy = {}
    deltas = {}
    
    args = Namespace(
        max_unused_assets=None, max_unused_prefabs=None, 
        max_unused_items=None, max_unused_quests=None,
        max_unused_textures=5, max_unused_audio=None, max_unused_data=None,
        max_unused_delta=None, fail_on_unused=False
    )
    
    # Texture limit 5, actual 8 -> Fail
    assert _check_thresholds(args, stats, policy, deltas, silent=True)
    
    # Audio limit 5, actual 2 -> Pass
    args.max_unused_textures = None
    args.max_unused_audio = 5
    assert not _check_thresholds(args, stats, policy, deltas, silent=True)
