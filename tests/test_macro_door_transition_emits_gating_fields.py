from __future__ import annotations

import json
from pathlib import Path


def test_macro_door_transition_emits_gating_fields(tmp_path: Path, monkeypatch) -> None:
    from engine.tooling_runtime.macro_apply_report import compute_scene_macro_report

    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    macro_path = tmp_path / "door_macro.json"
    macro_path.write_text(
        json.dumps(
            {
                "id": "door",
                "type": "macro",
                "macro_id": "macro.door_transition",
                "defaults": {"anchor": "cursor", "target_scene": "upper_hall", "spawn_id": "upper_entry"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    scene_payload = {"name": "Test", "entities": []}

    result = compute_scene_macro_report(
        scene_payload=scene_payload,
        scene_path="scenes/test_scene.json",
        macro_path=str(macro_path),
        raw_args=['require_flags=["demo.x"]', 'forbid_flags=["demo.y"]'],
        anchor_override=None,
        cursor_world_pos=(10.0, 20.0),
        primary_entity_id=None,
    )

    report = result.report
    assert int(report["will_create"]) == 1
    assert int(report["will_update"]) == 0
    created_id = report["create_ids"][0]

    created_ent = next(e for e in result.after_payload.get("entities", []) if isinstance(e, dict) and e.get("id") == created_id)
    assert created_ent.get("require_flags") == ["demo.x"]
    assert created_ent.get("forbid_flags") == ["demo.y"]

    row = next(r for r in report["entity_changes"] if r.get("id") == created_id)
    assert row.get("require_flags") == ["demo.x"]
    assert row.get("forbid_flags") == ["demo.y"]

    cfg_req = next(
        c for c in report["config_changes"] if c.get("id") == created_id and c.get("behaviour") == "Entity" and c.get("field") == "require_flags"
    )
    assert cfg_req.get("before") is None
    assert cfg_req.get("after") == ["demo.x"]

    cfg_forb = next(
        c for c in report["config_changes"] if c.get("id") == created_id and c.get("behaviour") == "Entity" and c.get("field") == "forbid_flags"
    )
    assert cfg_forb.get("before") is None
    assert cfg_forb.get("after") == ["demo.y"]

