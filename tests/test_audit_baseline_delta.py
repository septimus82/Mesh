import json
from argparse import Namespace
from pathlib import Path

import pytest

from engine.content_audit import audit_world
from engine.tooling.content_commands import _check_thresholds


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_minimal_content_tree(root: Path) -> None:
    _write_json(root / "assets/data/events.json", {"events": [{"name": "ep.entered", "description": "e", "payload": {}}]})
    _write_json(root / "assets/data/quests.json", {"quests": [{"id": "q1", "title": "q", "description": "d", "stages": []}]})
    _write_json(root / "cutscenes.json", {"cutscenes": [{"id": "c1", "steps": []}]})
    _write_json(
        root / "assets/data/dialogues.json",
        {
            "dialogues": [
                {
                    "id": "d1",
                    "schema_version": 1,
                    "start_node": "start",
                    "script": {"start": {"speaker": "n", "text": "t", "choices": []}},
                }
            ]
        },
    )
    _write_json(root / "assets/prefabs.json", [{"id": "player", "entity": {"behaviours": [], "behaviour_config": {}}}])
    _write_json(root / "scenes/s1.json", {"name": "s1", "entities": [{"id": "player", "prefab_id": "player", "x": 0, "y": 0}]})


def test_audit_categories(tmp_path: Path, monkeypatch) -> None:
    _build_minimal_content_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    report = audit_world()
    stats = report["stats"]
    assert set(stats["unused_by_category"].keys()) == {"audio", "data", "texture"}
    assert isinstance(stats["unused_by_category"]["data"], int)


def test_audit_allow_packs_is_adapter_warning(tmp_path: Path, monkeypatch) -> None:
    _build_minimal_content_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    report = audit_world(allow_packs=["mod_pack"])
    codes = [row.get("code", "") for row in report["integrity_issues"]]
    assert "content.audit_legacy.allow_packs_ignored" in codes

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
