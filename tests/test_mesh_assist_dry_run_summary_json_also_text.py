import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import engine.paths
from engine.tooling import assist_command


def test_mesh_assist_dry_run_summary_json_also_text(tmp_path, monkeypatch):
    """Verify dry-run summary JSON output with --also-text."""

    # Clear path cache
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None

    monkeypatch.chdir(tmp_path)

    # --- Setup ---
    # Create a dummy plan
    plan_path = tmp_path / "artifacts" / "assist_plan.json"
    plan_path.parent.mkdir(parents=True)

    # Create a file that will be modified
    existing_file = tmp_path / "existing.json"
    existing_file.write_text('{"foo": "bar"}', encoding="utf-8")

    plan_data = {
        "actions": [
            {
                "type": "create_scene",
                "args": {"path": str(tmp_path / "new.json"), "template": "empty"},
                "description": "Create New"
            },
            {
                "type": "add_npc",
                "args": {"scene_path": str(existing_file), "name": "Guard", "x": 100, "y": 100},
                "description": "Modify Existing"
            }
        ],
        "inputs": {
            "meta": {
                "touches": [
                    str(tmp_path / "new.json").replace("\\", "/"),
                    str(existing_file).replace("\\", "/")
                ]
            }
        }
    }
    plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")

    # Mock triage command to just return success
    with patch("engine.tooling.triage_command.run_triage_command", return_value=0):

        # Run command with --dry-run, --summary-json, and --also-text
        args = SimpleNamespace()
        args.world = "test_world"
        args.dry_run = True
        args.diff = False
        args.summary_json = True
        args.also_text = True

        # Capture stdout
        from io import StringIO

        captured_out = StringIO()
        with patch("sys.stdout", captured_out):
            exit_code = assist_command.run_assist_command(args)

        output = captured_out.getvalue()

        assert exit_code == 0

        # Verify delimiter exists
        delimiter = "---JSON---"
        assert delimiter in output

        # Split output
        parts = output.split(delimiter)
        assert len(parts) == 2
        text_part = parts[0].strip()
        json_part = parts[1].strip()

        # Verify text part
        assert "[ASSIST] Would write: 2 files" in text_part
        assert "[ASSIST] Write:" in text_part
        assert "(+added)" in text_part
        assert "(~changed)" in text_part

        # Verify JSON part
        try:
            data = json.loads(json_part)
        except json.JSONDecodeError:
            pytest.fail(f"JSON part is not valid JSON:\n{json_part}")

        assert data["version"] == 1
        assert data["world"] == "test_world"
        assert len(data["would_write"]) == 2

def test_mesh_assist_also_text_requires_summary_json(tmp_path, monkeypatch):
    """Verify --also-text requires --summary-json."""

    args = SimpleNamespace()
    args.world = "test_world"
    args.dry_run = True
    args.diff = False
    args.summary_json = False
    args.also_text = True

    # Capture stdout
    from io import StringIO

    captured_out = StringIO()
    with patch("sys.stdout", captured_out):
        exit_code = assist_command.run_assist_command(args)

    output = captured_out.getvalue()

    assert exit_code == 1
    assert "Error: --also-text requires --summary-json" in output
