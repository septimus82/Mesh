import argparse
import json
from unittest.mock import patch

import engine.paths
from engine.tooling import assist_command


def test_mesh_assist_dry_run_diff_multifile(tmp_path, monkeypatch):
    # Clear path cache to ensure we use tmp_path
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None

    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    # Setup World and Scenes for auto_wire_transitions
    # We need a Hub and an Interior that are not linked

    world_path = tmp_path / "worlds" / "test.json"
    world_path.parent.mkdir()

    hub_path = tmp_path / "scenes" / "region_hub.json"
    interior_path = tmp_path / "scenes" / "region_interior.json"
    hub_path.parent.mkdir(exist_ok=True)

    world_data = {
        "scenes": {
            "region_hub": {"path": str(hub_path)},
            "region_interior": {"path": str(interior_path)}
        }
    }
    world_path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")

    hub_data = {
        "name": "region_hub",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "hub"},
        "entities": []
    }
    hub_path.write_text(json.dumps(hub_data, indent=2), encoding="utf-8")

    interior_data = {
        "name": "region_interior",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "interior"},
        "entities": []
    }
    interior_path.write_text(json.dumps(interior_data, indent=2), encoding="utf-8")

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage:

        # Mock triage to return a plan with auto_wire_transitions
        def _mock_triage(args, root):
            plan = {
                "actions": [
                    {
                        "type": "auto_wire_transitions",
                        "args": {
                            "world_path": str(world_path)
                        },
                        "description": "Auto Wire"
                    }
                ],
                "meta": {"touches": ["scenes/region_hub.json", "scenes/region_interior.json"]},
            }
            (root / "artifacts" / "assist_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            return 0

        mock_triage.side_effect = lambda args: _mock_triage(args, tmp_path)

        args = argparse.Namespace(world="worlds/test.json", dry_run=True, diff=True)

        import sys
        from io import StringIO
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        exit_code = assist_command.run_assist_command(args)

        output = captured_out.getvalue()

        if exit_code != 0:
             print(output)

        assert exit_code == 0

        # Check for diff output for BOTH files
        # Hub should have transition to Interior
        if f"[ASSIST] Diff: {hub_path}" not in output:
            assert False, f"Hub diff missing. Output:\n{output}"

        assert f"[ASSIST] Diff: {hub_path}" in output
        assert f"+++ {hub_path}" in output

        # Interior should have transition to Hub
        assert f"[ASSIST] Diff: {interior_path}" in output
        assert f"+++ {interior_path}" in output
        assert '"target_scene": "scenes/region_hub.json"' in output.replace("\\", "/")

        # Ensure files on disk are UNCHANGED
        assert json.loads(hub_path.read_text(encoding="utf-8")) == hub_data
        assert json.loads(interior_path.read_text(encoding="utf-8")) == interior_data
