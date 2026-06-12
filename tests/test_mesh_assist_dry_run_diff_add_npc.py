import argparse
import json
from unittest.mock import patch

from engine.tooling import assist_command


def test_mesh_assist_dry_run_diff_add_npc(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    # Create a dummy scene
    scene_path = tmp_path / "scenes" / "dummy.json"
    scene_path.parent.mkdir()
    scene_data = {
        "name": "dummy",
        "version": 1,
        "entities": []
    }
    scene_path.write_text(json.dumps(scene_data, indent=2), encoding="utf-8")

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply:

        # Mock triage to return a plan with add_npc
        def _mock_triage(args, root):
            plan = {
                "actions": [
                    {
                        "type": "add_npc",
                        "args": {
                            "scene_path": str(scene_path),
                            "name": "TestNPC",
                            "x": 100,
                            "y": 200,
                            "role": "Villager"
                        },
                        "description": "Add NPC"
                    }
                ],
                "meta": {"touches": ["scenes/dummy.json"]},
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

        assert exit_code == 0

        # Check for diff output
        assert f"--- {scene_path}" in output
        assert f"+++ {scene_path}" in output
        assert '"name": "TestNPC",' in output
        assert '"tag": "npc",' in output
        assert '"Dialogue": {' in output
        assert '"role": "Villager"' in output

        # Ensure file on disk is UNCHANGED
        current_content = scene_path.read_text(encoding="utf-8")
        assert json.loads(current_content) == scene_data
        assert "TestNPC" not in current_content

def test_mesh_assist_dry_run_diff_add_npc_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage:

        def _mock_triage(args, root):
            plan = {
                "actions": [
                    {
                        "type": "add_npc",
                        "args": {
                            "scene_path": "scenes/missing.json",
                            "name": "TestNPC"
                        },
                        "description": "Add NPC"
                    }
                ]
            }
            (root / "artifacts" / "assist_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            return 0

        mock_triage.side_effect = lambda args: _mock_triage(args, tmp_path)

        args = argparse.Namespace(world="worlds/test.json", dry_run=True, diff=True)

        import sys
        from io import StringIO
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        assist_command.run_assist_command(args)

        output = captured_out.getvalue()

        assert "(skipped) add_npc scenes/missing.json (file not found)" in output
