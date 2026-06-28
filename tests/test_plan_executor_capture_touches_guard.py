import json
from pathlib import Path

import pytest

import engine.paths
from engine.paths import reset_path_caches, set_content_roots
from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Plan


def _write_world_and_scenes(tmp_path: Path) -> None:
    (tmp_path / "worlds").mkdir()
    (tmp_path / "scenes").mkdir()

    world_path = tmp_path / "worlds" / "w.json"
    hub_path = tmp_path / "scenes" / "region_hub.json"
    interior_path = tmp_path / "scenes" / "region_interior.json"

    world_data = {
        "scenes": {
            "region_hub": {"path": "scenes/region_hub.json"},
            "region_interior": {"path": "scenes/region_interior.json"},
        }
    }
    world_path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")

    hub_data = {
        "name": "region_hub",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "hub"},
        "entities": [
            {
                "name": "to_interior",
                "x": 0,
                "y": 0,
                "behaviours": ["SceneTransition"],
                "behaviour_config": {"SceneTransition": {"target_scene": "scenes/region_interior.json"}},
            }
        ],
    }
    hub_path.write_text(json.dumps(hub_data, indent=2), encoding="utf-8")

    interior_data = {
        "name": "region_interior",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "interior"},
        "entities": [],
    }
    interior_path.write_text(json.dumps(interior_data, indent=2), encoding="utf-8")


def test_plan_executor_capture_touches_guard_fails_on_missing(tmp_path, monkeypatch):
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None
    reset_path_caches()
    set_content_roots([tmp_path])
    monkeypatch.chdir(tmp_path)
    _write_world_and_scenes(tmp_path)

    plan_data = {
        "version": 1,
        "inputs": {"meta": {"touches": ["worlds/w.json"]}},
        "actions": [
            {
                "type": "auto_wire_transitions",
                "args": {"world_path": "worlds/w.json"},
                "description": "auto-wire",
            }
        ],
    }
    plan = Plan.from_dict(plan_data)

    captured = {}

    def capture_writer(path: Path, content: str):
        captured[str(path)] = content

    executor = PlanExecutor(dry_run=False, writer=capture_writer)
    with pytest.raises(ValueError, match=r"touches mismatch: missing"):
        executor.execute(plan, ai_safe=True)

    assert "scenes/region_interior.json" in executor.captured_writes


def test_plan_executor_capture_touches_guard_ok_when_covered(tmp_path, monkeypatch):
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None
    reset_path_caches()
    set_content_roots([tmp_path])
    monkeypatch.chdir(tmp_path)
    _write_world_and_scenes(tmp_path)

    plan_data = {
        "version": 1,
        "inputs": {"meta": {"touches": ["worlds/w.json", "scenes/region_interior.json"]}},
        "actions": [
            {
                "type": "auto_wire_transitions",
                "args": {"world_path": "worlds/w.json"},
                "description": "auto-wire",
            }
        ],
    }
    plan = Plan.from_dict(plan_data)

    captured = {}

    def capture_writer(path: Path, content: str):
        captured[str(path)] = content

    executor = PlanExecutor(dry_run=False, writer=capture_writer)
    executor.execute(plan, ai_safe=True)

    assert "scenes/region_interior.json" in executor.captured_writes

