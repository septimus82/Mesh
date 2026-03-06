"""Contract test for tooling/scan_exception_policies.py.

Verifies:
1. Artifact schema shape   – all expected keys present with correct types.
2. Determinism             – two scans produce identical output.
3. Baseline ratchet fidelity – the baseline file matches the running totals.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_scan() -> dict:
    from tooling.scan_exception_policies import scan

    return scan(["engine", "mesh_cli", "tooling"], repo_root=_REPO_ROOT)


# ------------------------------------------------------------------
# 1. Schema shape
# ------------------------------------------------------------------

_EXPECTED_KEYS = {
    "schema_version",
    "ble001_count_total",
    "except_pass_count_total",
    "broad_catch_count_total",
    "silent_broad_catch_count_total",
    "top_offenders",
    "silent_broad_catches",
    "files_scanned",
    "roots",
}


def test_schema_shape() -> None:
    result = _run_scan()
    missing = _EXPECTED_KEYS - set(result)
    assert not missing, f"Missing keys in scan result: {sorted(missing)}"

    # Type spot-checks
    assert isinstance(result["schema_version"], int)
    assert isinstance(result["ble001_count_total"], int)
    assert isinstance(result["silent_broad_catch_count_total"], int)
    assert isinstance(result["broad_catch_count_total"], int)
    assert isinstance(result["except_pass_count_total"], int)
    assert isinstance(result["files_scanned"], int)
    assert isinstance(result["roots"], list)
    assert isinstance(result["top_offenders"], dict)
    assert "ble001" in result["top_offenders"]
    assert "silent_broad_catch" in result["top_offenders"]
    assert isinstance(result["silent_broad_catches"], list)

    # Each silent_broad_catch entry has {file, line, kind}
    if result["silent_broad_catches"]:
        entry = result["silent_broad_catches"][0]
        assert "file" in entry
        assert "line" in entry
        assert "kind" in entry


# ------------------------------------------------------------------
# 2. Determinism
# ------------------------------------------------------------------


def test_determinism() -> None:
    a = _run_scan()
    b = _run_scan()
    # Compare the serialised form to catch ordering differences
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ------------------------------------------------------------------
# 3. Baseline fidelity
# ------------------------------------------------------------------

_BASELINE_PATH = _REPO_ROOT / "tooling" / "exception_policy_baseline.json"


def test_baseline_matches_scan() -> None:
    assert _BASELINE_PATH.exists(), "Baseline file missing"
    baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    result = _run_scan()

    # Baseline must have the keys we compare against
    assert "ble001_count_total" in baseline
    assert "silent_broad_catch_count_total" in baseline
    assert "silent_broad_catch_max" in baseline, "baseline missing silent_broad_catch_max"

    # silent_broad_catch_max must be >= silent_broad_catch_count_total
    assert baseline["silent_broad_catch_max"] >= baseline["silent_broad_catch_count_total"], (
        "silent_broad_catch_max must be >= silent_broad_catch_count_total"
    )

    # Current scan must be <= baseline (ratchet invariant)
    assert result["ble001_count_total"] <= baseline["ble001_count_total"], (
        f"BLE001 count {result['ble001_count_total']} exceeds baseline {baseline['ble001_count_total']}"
    )
    assert result["silent_broad_catch_count_total"] <= baseline["silent_broad_catch_count_total"], (
        f"Silent broad catches {result['silent_broad_catch_count_total']} exceeds baseline {baseline['silent_broad_catch_count_total']}"
    )
    assert result["silent_broad_catch_count_total"] <= baseline["silent_broad_catch_max"], (
        f"Silent broad catches {result['silent_broad_catch_count_total']} exceeds max {baseline['silent_broad_catch_max']}"
    )
