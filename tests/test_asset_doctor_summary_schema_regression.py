import json
from pathlib import Path

import engine.tooling.asset_doctor as facade
import engine.tooling_runtime.asset_doctor as runtime


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_asset_doctor_summary_schema_and_ordering_regression(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    # Required files.
    (repo / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text("[]\n", encoding="utf-8")
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")

    # Scene with a warning in non-strict mode.
    _write(
        repo / "scenes" / "a.json",
        {"entities": [{"behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {}}}]},
    )

    # Scene with an error.
    _write(
        repo / "scenes" / "b.json",
        {"entities": [{"behaviours": ["SceneTransition"], "behaviour_config": {"SceneTransition": {}}}]},
    )

    # World references one existing scene and one missing file, and has an unknown start_scene.
    _write(
        repo / "worlds" / "w.json",
        {
            "id": "w",
            "start_scene": "unknown",
            "scenes": {
                "s1": {"path": "scenes/a.json"},
                "s2": {"path": "scenes/missing.json"},
            },
        },
    )

    expected = {
        "ok": False,
        "errors": [
            {
                "code": "scene_transition.target_scene.required",
                "path": "scenes/b.json",
                "message": "SceneTransition missing target_scene (entity index 0)",
            },
            {
                "code": "world.scene.file.missing",
                "path": "scenes/missing.json",
                "message": "referenced by worlds/w.json (scene id 's2')",
            },
            {
                "code": "world.start_scene.unknown",
                "path": "worlds/w.json",
                "message": "start_scene refers to unknown scene id: unknown",
            },
        ],
        "warnings": [
            {
                "code": "trigger_zone.zone_id.required",
                "path": "scenes/a.json",
                "message": "TriggerZone missing zone_id (entity index 0)",
            }
        ],
        "fixes": [],
        "cache": {"hits": 0, "misses": 0, "entries": 0},
        "missing_prefab_assets": [],
        "missing_prefab_assets_warnings": [],
    }

    payload_runtime = runtime.doctor_assets(repo_root=repo, fix=False, strict=False)
    payload_facade = facade.doctor_assets(repo_root=repo, fix=False, strict=False)

    assert set(payload_runtime.keys()) == {
        "ok",
        "errors",
        "warnings",
        "fixes",
        "cache",
        "missing_prefab_assets",
        "missing_prefab_assets_warnings",
    }
    assert payload_runtime == expected
    assert payload_facade == expected
