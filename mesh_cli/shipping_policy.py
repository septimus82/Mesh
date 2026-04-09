from __future__ import annotations

from typing import Mapping


SHIPPING_VERIFY_STEP_NAMES: tuple[str, ...] = (
    "runtime-player-smoke",
    "player-package-gate",
    "web-smoke",
    "perf-baseline-compare",
)


_VERIFY_SUMMARY_ARTIFACT_SPECS: tuple[tuple[str, str], ...] = (
    ("player_pkg_manifest", "player_package_manifest"),
    ("player_pkg_check", "player_package_check"),
    ("player_pkg_runtime_smoke", "player_package_runtime_smoke"),
    ("player_pkg_runtime_diagnostics_snapshot", "player_package_runtime_diagnostics_snapshot"),
    ("web_smoke", "web_smoke"),
    ("perf_compare", "perf_compare"),
    ("swallow_scan", "swallow_scan"),
    ("runtime_smoke", "runtime_smoke"),
    ("runtime_diagnostics_snapshot", "runtime_diagnostics_snapshot"),
)


_SHIP_CHECK_ARTIFACT_SPECS: tuple[tuple[str, str, bool, str], ...] = (
    ("player_manifest", "player_pkg/manifest.json", True, "package"),
    ("player_package_check", "player_pkg/package_check.json", True, "package"),
    ("player_runtime_smoke", "player_pkg/runtime_smoke.json", True, "package"),
    ("runtime_diagnostics_snapshot", "runtime_diagnostics_snapshot.json", True, "verify"),
    ("web_smoke", "web_smoke.json", True, "web"),
    ("perf_compare", "perf_compare.json", True, "perf"),
    ("perf_run", "perf_run.json", False, "perf"),
    ("verify_bundle", "verify_all_summary.json", False, "verify"),
)


def build_verify_summary_key_artifacts(
    artifacts_written: Mapping[str, str | None],
) -> dict[str, str | None]:
    payload: dict[str, str | None] = {}
    for summary_key, written_key in _VERIFY_SUMMARY_ARTIFACT_SPECS:
        value = artifacts_written.get(written_key)
        payload[summary_key] = value.strip() if isinstance(value, str) and value.strip() else None
    return payload


def iter_ship_check_artifact_specs() -> tuple[tuple[str, str, bool, str], ...]:
    return _SHIP_CHECK_ARTIFACT_SPECS


def shipping_required_verify_steps(
    *,
    skip_package: bool,
    skip_web: bool,
    skip_perf: bool,
) -> tuple[str, ...]:
    steps: list[str] = []
    for name in SHIPPING_VERIFY_STEP_NAMES:
        if skip_package and name == "player-package-gate":
            continue
        if skip_web and name == "web-smoke":
            continue
        if skip_perf and name == "perf-baseline-compare":
            continue
        steps.append(name)
    return tuple(steps)


__all__ = [
    "SHIPPING_VERIFY_STEP_NAMES",
    "build_verify_summary_key_artifacts",
    "iter_ship_check_artifact_specs",
    "shipping_required_verify_steps",
]
