import json
from pathlib import Path

import engine.tooling_runtime.asset_doctor as runtime


def test_asset_doctor_fix_is_idempotent_and_bytes_stable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text("[]\n", encoding="utf-8")
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")
    (repo / "scenes").mkdir()

    scene_path = repo / "scenes" / "a.json"
    scene_path.write_text(
        json.dumps(
            {"entities": [{"id": "E1", "behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {}}}]},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload1 = runtime.doctor_assets(repo_root=repo, fix=True, strict=False)
    assert payload1["ok"] is True
    assert payload1["errors"] == []
    assert payload1["warnings"] == []
    assert payload1["fixes"] == [
        {
            "code": "trigger_zone.zone_id.autofix",
            "path": "scenes/a.json",
            "message": "set TriggerZone.zone_id from entity.id for entity 'E1'",
        }
    ]

    bytes_after_first = scene_path.read_bytes()

    payload2 = runtime.doctor_assets(repo_root=repo, fix=True, strict=False)
    assert payload2["ok"] is True
    assert payload2["errors"] == []
    assert payload2["warnings"] == []
    assert payload2["fixes"] == []
    cache = payload2.get("cache")
    assert isinstance(cache, dict)

    bytes_after_second = scene_path.read_bytes()
    assert bytes_after_second == bytes_after_first
