from __future__ import annotations

from pathlib import Path

import pytest

from mesh_cli.shipping_policy import (
    SHIPPING_VERIFY_STEP_NAMES,
    build_verify_summary_key_artifacts,
    iter_ship_check_artifact_specs,
)
from mesh_cli.verify_steps import STEP_ORDER


pytestmark = [pytest.mark.fast]


def test_shipping_verify_steps_are_canonical_and_present() -> None:
    assert SHIPPING_VERIFY_STEP_NAMES == (
        "runtime-player-smoke",
        "player-package-gate",
        "web-smoke",
        "perf-baseline-compare",
    )
    indexes = [STEP_ORDER.index(name) for name in SHIPPING_VERIFY_STEP_NAMES]
    assert indexes == sorted(indexes)


def test_shipping_artifact_semantics_match_verify_summary_and_ship_check() -> None:
    key_artifacts = build_verify_summary_key_artifacts(
        {
            "player_package_manifest": "artifacts/player_pkg/manifest.json",
            "player_package_check": "artifacts/player_pkg/package_check.json",
            "player_package_runtime_smoke": "artifacts/player_pkg/runtime_smoke.json",
            "player_package_runtime_diagnostics_snapshot": "artifacts/player_pkg/runtime_diagnostics_snapshot.json",
            "web_smoke": "artifacts/web_smoke.json",
            "perf_compare": "artifacts/perf_compare.json",
            "swallow_scan": "artifacts/swallow_scan.json",
            "runtime_smoke": "artifacts/runtime_smoke.json",
            "runtime_diagnostics_snapshot": "artifacts/runtime_diagnostics_snapshot.json",
        }
    )
    assert list(key_artifacts.keys()) == [
        "player_pkg_manifest",
        "player_pkg_check",
        "player_pkg_runtime_smoke",
        "player_pkg_runtime_diagnostics_snapshot",
        "web_smoke",
        "perf_compare",
        "swallow_scan",
        "runtime_smoke",
        "runtime_diagnostics_snapshot",
    ]
    ship_specs = iter_ship_check_artifact_specs()
    assert ("web_smoke", "web_smoke.json", True, "web") in ship_specs
    assert ("perf_compare", "perf_compare.json", True, "perf") in ship_specs


def test_shipping_docs_reference_the_same_web_gate_contract() -> None:
    shipping_doc = Path("docs/ShippingReadiness.md").read_text(encoding="utf-8")
    commands_doc = Path("docs/Commands.md").read_text(encoding="utf-8")
    assert "- `web-smoke`" in shipping_doc
    assert "- `web-smoke` via the `verify-all --ci-bundle` shipping gate" in commands_doc
