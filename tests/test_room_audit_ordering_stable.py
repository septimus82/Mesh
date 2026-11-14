from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_room_audit_ordering_stable(verify_all_audit_artifacts: Path) -> None:
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    payload = json.loads((artifacts_dir / "room_audit.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    cases = payload["cases"]
    assert isinstance(cases, list)

    last = None
    for case in cases:
        key = (
            str(case.get("from_scene") or ""),
            str(case.get("to_scene") or ""),
            str(case.get("stamp_path") or ""),
            str(case.get("door_macro") or ""),
        )
        if last is not None:
            assert last <= key
        last = key
        for field in ("will_create", "will_update", "entity_change_count", "config_change_count"):
            assert isinstance(case.get(field), int)
            assert int(case.get(field)) >= 0
