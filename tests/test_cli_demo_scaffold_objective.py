from __future__ import annotations

import json
from pathlib import Path


def _write_scene(path: Path, scene: dict) -> None:
    path.write_text(json.dumps(scene, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_cli_demo_scaffold_objective_wires_three_scenes_and_is_idempotent(tmp_path: Path, capsys) -> None:
    import mesh_cli

    start = tmp_path / "start.json"
    interior = tmp_path / "interior.json"
    cellar = tmp_path / "cellar.json"

    _write_scene(
        start,
        {
            "name": "Start",
            "schema_version": 1,
            "version": 1,
            "settings": {},
            "entities": [
                {
                    "id": "speaker_1",
                    "name": "Speaker",
                    "x": 10.0,
                    "y": 20.0,
                    "behaviours": ["Dialogue"],
                    "behaviour_config": {
                        "Dialogue": {
                            "dialogue": {"speaker": "Speaker", "start": "intro", "nodes": {"intro": {"text": "Hi", "choices": []}}}
                        }
                    },
                }
            ],
        },
    )
    _write_scene(interior, {"name": "Interior", "schema_version": 1, "version": 1, "settings": {}, "entities": []})
    _write_scene(cellar, {"name": "Cellar", "schema_version": 1, "version": 1, "settings": {}, "entities": []})

    argv = [
        "demo",
        "scaffold-objective",
        "--start-scene",
        str(start),
        "--speaker-id",
        "speaker_1",
        "--choice-id",
        "start_choice",
        "--choice-text",
        "Start objective",
        "--interior-scene",
        str(interior),
        "--interior-x",
        "1",
        "--interior-y",
        "2",
        "--interior-radius",
        "48",
        "--cellar-scene",
        str(cellar),
        "--cellar-x",
        "3",
        "--cellar-y",
        "4",
        "--cellar-radius",
        "64",
        "--flag-started",
        "demo.objective_started",
        "--flag-mid",
        "demo.reached_interior",
        "--flag-done",
        "demo.reached_cellar",
    ]

    assert mesh_cli.main(argv) == 0
    capsys.readouterr()

    start_payload = json.loads(start.read_text(encoding="utf-8"))
    speaker = next(e for e in start_payload["entities"] if e.get("id") == "speaker_1")
    choices = speaker["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["intro"]["choices"]
    assert any(isinstance(c, dict) and c.get("id") == "start_choice" for c in choices)
    start_hook_id = "start_choiceflag_demo_objective_started_start_choice_0_0"
    assert any(e.get("id") == start_hook_id for e in start_payload["entities"])

    interior_payload = json.loads(interior.read_text(encoding="utf-8"))
    assert any("TriggerZone" in (e.get("behaviours") or []) for e in interior_payload["entities"])
    assert any("SetGameStateOnEvent" in (e.get("behaviours") or []) for e in interior_payload["entities"])

    cellar_payload = json.loads(cellar.read_text(encoding="utf-8"))
    assert any("TriggerZone" in (e.get("behaviours") or []) for e in cellar_payload["entities"])
    assert any("SetGameStateOnEvent" in (e.get("behaviours") or []) for e in cellar_payload["entities"])

    # Re-run should be idempotent (no duplicates)
    assert mesh_cli.main(argv) == 0
    capsys.readouterr()
    start_payload2 = json.loads(start.read_text(encoding="utf-8"))
    interior_payload2 = json.loads(interior.read_text(encoding="utf-8"))
    cellar_payload2 = json.loads(cellar.read_text(encoding="utf-8"))
    assert len(start_payload2["entities"]) == len(start_payload["entities"])
    assert len(interior_payload2["entities"]) == len(interior_payload["entities"])
    assert len(cellar_payload2["entities"]) == len(cellar_payload["entities"])


def test_cli_demo_scaffold_objective_errors_on_missing_speaker(tmp_path: Path, capsys) -> None:
    import mesh_cli

    start = tmp_path / "start.json"
    interior = tmp_path / "interior.json"
    cellar = tmp_path / "cellar.json"

    _write_scene(start, {"name": "Start", "schema_version": 1, "version": 1, "settings": {}, "entities": []})
    _write_scene(interior, {"name": "Interior", "schema_version": 1, "version": 1, "settings": {}, "entities": []})
    _write_scene(cellar, {"name": "Cellar", "schema_version": 1, "version": 1, "settings": {}, "entities": []})

    code = mesh_cli.main(
        [
            "demo",
            "scaffold-objective",
            "--start-scene",
            str(start),
            "--speaker-id",
            "missing",
            "--choice-id",
            "start_choice",
            "--choice-text",
            "Start objective",
            "--interior-scene",
            str(interior),
            "--interior-x",
            "1",
            "--interior-y",
            "2",
            "--interior-radius",
            "48",
            "--cellar-scene",
            str(cellar),
            "--cellar-x",
            "3",
            "--cellar-y",
            "4",
            "--cellar-radius",
            "64",
            "--flag-started",
            "demo.objective_started",
            "--flag-mid",
            "demo.reached_interior",
            "--flag-done",
            "demo.reached_cellar",
        ]
    )
    out = capsys.readouterr().out
    assert code != 0
    assert "speaker entity not found" in out

