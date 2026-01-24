from __future__ import annotations

import os
from pathlib import Path

from engine.persistence_io import read_json, write_json_atomic
from engine.validators.schema_validation import validate_scene
import mesh_cli


def test_schema_fix_ids_idempotent_bytes_and_schema_strict(tmp_path: Path) -> None:
    # Create an isolated workspace on disk.
    scene_dir = tmp_path / "scenes"
    scene_dir.mkdir(parents=True)
    scene_path = scene_dir / "demo_scene.json"

    # Minimal scene with one entity missing id and TriggerZone.zone_id.
    payload = {
        "name": "Demo Scene",
        "entities": [
            {
                "name": "Zone",
                "x": 10.0,
                "y": 20.0,
                "behaviours": ["TriggerZone"],
                "behaviour_config": {
                    "TriggerZone": {
                        "trigger_radius": 5,
                        "trigger_target": "player",
                    }
                },
            }
        ],
    }
    write_json_atomic(scene_path, payload, indent=2, sort_keys=True, trailing_newline=True)

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # First run should update file.
        rc1 = mesh_cli.main(["schema-fix-ids", "--paths", "scenes/*.json"])
        assert rc1 == 0
        b1 = scene_path.read_bytes()

        # Strict schema validation should pass after first run.
        data1 = read_json(scene_path)
        assert validate_scene(scene_path, data1, strict=True) == []

        # Second run should be a no-op with identical bytes.
        rc2 = mesh_cli.main(["schema-fix-ids", "--paths", "scenes/*.json"])
        assert rc2 == 0
        b2 = scene_path.read_bytes()
        assert b2 == b1

        # Still strict-valid.
        data2 = read_json(scene_path)
        assert validate_scene(scene_path, data2, strict=True) == []
    finally:
        os.chdir(old_cwd)
