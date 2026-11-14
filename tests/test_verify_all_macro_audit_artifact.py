from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_macro_audit_artifact(verify_all_audit_artifacts: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    path = artifacts_dir / "macro_audit.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert int(payload["case_count"]) >= 2
    cases = payload["cases"]
    assert isinstance(cases, list) and cases

    expected = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))["macro_audit_cases"][0]
    expected_scene = expected["scene_path"]
    expected_macro = expected["macro_path"]
    match = next((c for c in cases if c.get("scene_path") == expected_scene and c.get("macro_path") == expected_macro), None)
    assert match is not None
    assert match["args"]["target_scene"] == "scenes/upper_hall.json"
    assert match["args"]["spawn_id"] == "upper_hall_entry"
    assert match["args"]["anchor"] == "player"

    assert int(match["will_create"]) == 1
    assert int(match["will_update"]) == 0
    assert match["create_ids_first"] == ["door_field_macro_transition_upper_hall_0_0_0_0"]
    assert match["update_ids_first"] == []


def test_macro_audit_ordering_is_deterministic(verify_all_audit_artifacts: Path) -> None:
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    payload = json.loads((artifacts_dir / "macro_audit.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True

    cases = payload["cases"]
    keys = [
        (
            str(c.get("scene_path") or ""),
            str(c.get("macro_path") or ""),
            json.dumps(c.get("args") or {}, sort_keys=True),
        )
        for c in cases
    ]
    assert keys == sorted(keys)

    for case in cases:
        create_ids = case.get("create_ids_first") or []
        update_ids = case.get("update_ids_first") or []
        assert isinstance(create_ids, list)
        assert isinstance(update_ids, list)
        assert create_ids == sorted(create_ids)
        assert update_ids == sorted(update_ids)
        assert len(create_ids) <= 5
        assert len(update_ids) <= 5
