from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_encounter_coverage_matrix_artifact(verify_all_audit_artifacts: Path) -> None:
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    matrix_path = artifacts_dir / "encounter_coverage_matrix.json"
    assert matrix_path.exists()
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))

    assert payload["ok"] is True
    assert payload["difficulties"] == ["easy", "hard"]
    rows = payload["rows"]
    assert rows

    def _require_row(encounter_set_id: str, difficulty: str) -> dict:
        row = next(
            (r for r in rows if r.get("encounter_set_id") == encounter_set_id and r.get("difficulty") == difficulty),
            None,
        )
        assert row is not None
        return row

    def _assert_easy_has_cheap_candidates(encounter_set_id: str) -> None:
        row = _require_row(encounter_set_id, "easy")
        assert int(row.get("eligible_count", 0)) >= 1
        cheapest = row.get("cheapest_candidate_cost")
        assert cheapest is not None
        assert float(cheapest) <= 2.0

    for encounter_set_id in (
        "moss_encounters",
        "crypt_encounters",
        "ruins_encounters",
        "forge_encounters",
        "magma_encounters",
        "void_encounters",
    ):
        _assert_easy_has_cheap_candidates(encounter_set_id)
        _require_row(encounter_set_id, "hard")

    ordering = [(row.get("encounter_set_id"), row.get("difficulty")) for row in rows]
    assert ordering == sorted(ordering)
