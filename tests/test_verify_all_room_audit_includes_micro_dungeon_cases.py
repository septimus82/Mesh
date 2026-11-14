from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_room_audit_includes_micro_dungeon_cases(verify_all_audit_artifacts: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    expected_cases = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))["room_audit_cases"]
    assert len(expected_cases) == 3

    payload = json.loads((artifacts_dir / "room_audit.json").read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) == 3

    expected_keys = sorted(
        [
            (
                c["from_scene"],
                c["to_scene"],
                c["stamp_path"],
                c["door_macro"],
            )
            for c in expected_cases
        ]
    )
    actual_keys = sorted(
        [
            (
                c["from_scene"],
                c["to_scene"],
                c["stamp_path"],
                c["door_macro"],
            )
            for c in cases
        ]
    )
    assert actual_keys == expected_keys
