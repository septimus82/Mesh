from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_stamp_audit_tile_and_entity_ordering_is_deterministic(verify_all_audit_artifacts: Path) -> None:
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    payload = json.loads((artifacts_dir / "stamp_audit.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True

    for case in payload["cases"]:
        tile_changes = case.get("tile_changes") or []
        entity_changes = case.get("entity_changes") or []

        assert isinstance(tile_changes, list)
        assert isinstance(entity_changes, list)

        tile_keys = [(str(r.get("layer_id") or ""), int(r.get("y") or 0), int(r.get("x") or 0)) for r in tile_changes]
        assert tile_keys == sorted(tile_keys)

        entity_ids = [str(r.get("id") or "") for r in entity_changes]
        assert entity_ids == sorted(entity_ids)
