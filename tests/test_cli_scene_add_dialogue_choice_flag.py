from __future__ import annotations

import json
from pathlib import Path


def test_cli_scene_add_dialogue_choice_flag_inserts_choice_and_hook(tmp_path: Path, capsys) -> None:
    import mesh_cli

    scene_path = tmp_path / "demo_scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "name": "Demo Scene",
                "schema_version": 1,
                "version": 1,
                "settings": {},
                "entities": [
                    {
                        "id": "speaker_1",
                        "name": "Speaker",
                        "x": 1.0,
                        "y": 2.0,
                        "behaviours": ["Dialogue"],
                        "behaviour_config": {
                            "Dialogue": {
                                "dialogue": {
                                    "speaker": "Speaker",
                                    "start": "intro",
                                    "nodes": {"intro": {"text": "Hello", "choices": []}},
                                }
                            }
                        },
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    argv = [
        "scene",
        "add-dialogue-choice-flag",
        str(scene_path),
        "--speaker-id",
        "speaker_1",
        "--choice-id",
        "demo_objective_start",
        "--choice-text",
        "Where should I go for the demo?",
        "--set-flag",
        "demo.objective_started",
        "--forbid",
        "demo.objective_started",
        "--toast",
        "Objective: Enter the cellar",
        "--toast-seconds",
        "3",
    ]

    assert mesh_cli.main(argv) == 0
    capsys.readouterr()

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    entities = payload.get("entities")
    assert isinstance(entities, list)

    speaker = next(e for e in entities if e.get("id") == "speaker_1")
    choices = speaker["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["intro"]["choices"]
    assert any(isinstance(c, dict) and c.get("id") == "demo_objective_start" for c in choices)

    hook_id = "demo_scene_choiceflag_demo_objective_started_demo_objective_start_0_0"
    hook = next(e for e in entities if e.get("id") == hook_id)
    cfg = hook["behaviour_config"]["SetGameStateOnEvent"]
    assert cfg["event_type"] == "dialogue_choice"
    assert cfg["payload_field"] == "choice_id"
    assert cfg["payload_value"] == "demo_objective_start"
    assert cfg["once"] is True
    assert cfg["set_flags"] == {"demo.objective_started": True}
    assert cfg["forbid_flags"] == ["demo.objective_started"]
    assert cfg["toast"] == "Objective: Enter the cellar"
    assert float(cfg["toast_seconds"]) == 3.0

    # Re-run: no-op
    assert mesh_cli.main(argv) == 0
    capsys.readouterr()
    payload2 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert len(payload2.get("entities", [])) == len(entities)


def test_cli_scene_add_dialogue_choice_flag_errors_on_missing_speaker(tmp_path: Path, capsys) -> None:
    import mesh_cli

    scene_path = tmp_path / "demo_scene.json"
    scene_path.write_text(
        json.dumps({"name": "Demo", "schema_version": 1, "version": 1, "entities": []}, indent=2) + "\n",
        encoding="utf-8",
    )

    code = mesh_cli.main(
        [
            "scene",
            "add-dialogue-choice-flag",
            str(scene_path),
            "--speaker-id",
            "missing",
            "--choice-id",
            "c1",
            "--choice-text",
            "Hi",
            "--set-flag",
            "demo.objective_started",
        ]
    )
    out = capsys.readouterr().out
    assert code != 0
    assert "speaker entity not found" in out


def test_cli_scene_add_dialogue_choice_flag_errors_on_hook_mismatch(tmp_path: Path, capsys) -> None:
    import mesh_cli

    scene_path = tmp_path / "demo_scene.json"
    preexisting = {
        "name": "Demo Scene",
        "schema_version": 1,
        "version": 1,
        "settings": {},
        "entities": [
            {
                "id": "speaker_1",
                "x": 1.0,
                "y": 2.0,
                "behaviours": ["Dialogue"],
                "behaviour_config": {"Dialogue": {"dialogue": {"start": "intro", "nodes": {"intro": {"text": "", "choices": []}}}}},
            },
            {
                "id": "demo_scene_choiceflag_demo_objective_started_demo_objective_start_0_0",
                "x": 0.0,
                "y": 0.0,
                "behaviours": ["SetGameStateOnEvent"],
                "behaviour_config": {
                    "SetGameStateOnEvent": {
                        "event_type": "dialogue_choice",
                        "once": True,
                        "payload_field": "choice_id",
                        "payload_value": "something_else",
                        "set_flags": {"demo.objective_started": True},
                    }
                },
            },
        ],
    }
    scene_path.write_text(json.dumps(preexisting, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    code = mesh_cli.main(
        [
            "scene",
            "add-dialogue-choice-flag",
            str(scene_path),
            "--speaker-id",
            "speaker_1",
            "--choice-id",
            "demo_objective_start",
            "--choice-text",
            "Where should I go for the demo?",
            "--set-flag",
            "demo.objective_started",
        ]
    )
    out = capsys.readouterr().out
    assert code != 0
    assert "existing hook entity differs" in out

