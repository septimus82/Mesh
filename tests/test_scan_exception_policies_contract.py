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


def test_schema_shape(exception_policy_scan: dict) -> None:
    result = exception_policy_scan
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


def test_determinism(exception_policy_scan: dict) -> None:
    a = exception_policy_scan  # an earlier, independent scan
    b = _run_scan()
    # Compare the serialised form to catch ordering differences
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ------------------------------------------------------------------
# 3. Baseline fidelity
# ------------------------------------------------------------------

_BASELINE_PATH = _REPO_ROOT / "tooling" / "exception_policy_baseline.json"


def test_baseline_matches_scan(exception_policy_scan: dict) -> None:
    assert _BASELINE_PATH.exists(), "Baseline file missing"
    baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    result = exception_policy_scan

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


def test_statement_walk_finds_every_handler_in_ast_walk_order() -> None:
    import ast
    import textwrap

    from tooling.scan_exception_policies import _statements

    source = textwrap.dedent(
        """
        try:
            x = [lambda: 1 for _ in range(2)]
        except Exception:
            pass
        def f():
            match x:
                case [1, *rest] if rest:
                    try:
                        pass
                    except (ValueError, TypeError):
                        raise
                case _:
                    class C:
                        def g(self):
                            try:
                                pass
                            except* OSError:
                                pass
        try:
            pass
        finally:
            try:
                pass
            except BaseException:
                pass
        """
    )
    tree = ast.parse(source)
    walked = [n.lineno for n in ast.walk(tree) if isinstance(n, (ast.ExceptHandler, ast.Raise))]
    assert len(walked) == 5
    assert [n.lineno for n in _statements(tree) if isinstance(n, (ast.ExceptHandler, ast.Raise))] == walked
