import argparse
import json
from pathlib import Path
from unittest.mock import patch

import engine.paths
from engine.tooling import assist_command


def test_mesh_assist_dry_run_summary_json_touches_guard(tmp_path, monkeypatch, capsys):
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None

    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
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

    def mock_triage(args):
        plan = {
            "wizard": "fix-from-doctor",
            "version": 1,
            "actions": [
                {
                    "type": "auto_wire_transitions",
                    "args": {"world_path": "worlds/w.json"},
                    "description": "auto-wire",
                }
            ],
            "meta": {
                "unfixable": [],
                "touches": ["worlds/w.json"],
            },
        }
        Path(args.out).write_text(json.dumps(plan), encoding="utf-8")
        print(json.dumps({"plan_meta": {}, "warnings": []}))
        return 0

    with patch("engine.tooling.triage_command.run_triage_command", side_effect=mock_triage):
        args = argparse.Namespace(world="worlds/w.json", dry_run=True, diff=False, summary_json=True, also_text=True)
        exit_code = assist_command.run_assist_command(args)

    assert exit_code == 3
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["stage"] == "triage_refuse"
    assert payload["reason"] == "touches_mismatch"
    assert payload["ok"] is False
    assert "scenes/region_interior.json" in payload["missing"]
