from __future__ import annotations

import json
from pathlib import Path


def test_cli_scene_add_triggerzone_objective_inserts_and_is_idempotent(tmp_path: Path, capsys) -> None:
    import mesh_cli

    scene_path = tmp_path / "demo_scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "name": "Demo Scene",
                "schema_version": 1,
                "version": 1,
                "settings": {},
                "entities": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    argv = [
        "scene",
        "add-triggerzone-objective",
        str(scene_path),
        "--x",
        "10",
        "--y",
        "20",
        "--radius",
        "48",
        "--zone-id",
        "DemoObjectiveInteriorZone",
        "--set-flag",
        "demo.reached_interior",
        "--require",
        "demo.objective_started",
        "--forbid",
        "demo.reached_interior",
        "--toast",
        "Objective: Find the cellar",
        "--toast-seconds",
        "3",
    ]
    assert mesh_cli.main(argv) == 0
    capsys.readouterr()

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    entities = payload.get("entities")
    assert isinstance(entities, list)
    assert len(entities) == 2

    trigger = next(e for e in entities if e.get("id") == "demo_scene_triggerzone_DemoObjectiveInteriorZone_10_20_0_0")
    setter = next(
        e for e in entities if e.get("id") == "demo_scene_setflag_demo_reached_interior_DemoObjectiveInteriorZone_10_20_0_0"
    )

    assert trigger["behaviour_config"]["TriggerZone"]["zone_id"] == "DemoObjectiveInteriorZone"
    assert trigger["behaviour_config"]["TriggerZone"]["trigger_target"] == "Player"
    assert float(trigger["behaviour_config"]["TriggerZone"]["trigger_radius"]) == 48.0

    cfg = setter["behaviour_config"]["SetGameStateOnEvent"]
    assert cfg["event_type"] == "entered_zone"
    assert cfg["payload_field"] == "zone"
    assert cfg["payload_value"] == "DemoObjectiveInteriorZone"
    assert cfg["once"] is True
    assert cfg["set_flags"] == {"demo.reached_interior": True}
    assert cfg["require_flags"] == ["demo.objective_started"]
    assert cfg["forbid_flags"] == ["demo.reached_interior"]
    assert cfg["toast"] == "Objective: Find the cellar"
    assert float(cfg["toast_seconds"]) == 3.0

    # Re-run should be no-op (no duplicates)
    assert mesh_cli.main(argv) == 0
    capsys.readouterr()
    payload2 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert isinstance(payload2.get("entities"), list)
    assert len(payload2["entities"]) == 2


def test_cli_scene_add_triggerzone_objective_errors_on_mismatch(tmp_path: Path, capsys) -> None:
    import mesh_cli

    scene_path = tmp_path / "demo_scene.json"
    preexisting = {
        "name": "Demo Scene",
        "schema_version": 1,
        "version": 1,
        "settings": {},
        "entities": [
            {
                "id": "demo_scene_triggerzone_DemoObjectiveInteriorZone_10_20_0_0",
                "x": 10.0,
                "y": 20.0,
                "behaviours": ["TriggerZone"],
                "behaviour_config": {
                    "TriggerZone": {
                        "on_trigger": "objective_trigger",
                        "trigger_radius": 12.0,
                        "trigger_target": "Player",
                        "zone_id": "DemoObjectiveInteriorZone",
                    }
                },
            }
        ],
    }
    scene_path.write_text(json.dumps(preexisting, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    code = mesh_cli.main(
        [
            "scene",
            "add-triggerzone-objective",
            str(scene_path),
            "--x",
            "10",
            "--y",
            "20",
            "--radius",
            "48",
            "--zone-id",
            "DemoObjectiveInteriorZone",
            "--set-flag",
            "demo.reached_interior",
        ]
    )
    out = capsys.readouterr().out
    assert code != 0
    assert "differs" in out

