from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_cli_parser_registers_ship_check_command_contract() -> None:
    from mesh_cli.main import create_parser

    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    choices = set(subparsers_action.choices.keys())
    assert "ship-check" in choices


def test_ship_check_help_includes_required_flags_contract() -> None:
    from mesh_cli.main import create_parser

    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    ship_parser = subparsers_action.choices["ship-check"]
    help_text = ship_parser.format_help()
    for flag in (
        "--artifacts",
        "--skip-package",
        "--skip-web",
        "--skip-perf",
        "--skip-verify",
        "--continue-on-web-fail",
        "--quiet",
    ):
        assert flag in help_text


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def _write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def test_ship_check_summary_format_and_presence_contract(tmp_path: Path) -> None:
    from mesh_cli.ship_check import build_ship_check_summary

    artifacts = tmp_path / "artifacts"
    _touch(artifacts / "player_pkg" / "manifest.json")
    _touch(artifacts / "player_pkg" / "package_check.json")
    _touch(artifacts / "player_pkg" / "runtime_smoke.json")
    _touch(artifacts / "runtime_diagnostics_snapshot.json")
    _write_json(
        artifacts / "web_smoke.json",
        '{"diagnostics":[{"code":"WEB_BUILD_TOOLING_FAILED"},{"code":"WEB_INDEX_MISSING"}]}',
    )
    _touch(artifacts / "perf_compare.json")
    _touch(artifacts / "verify_all_summary.json")

    summary = build_ship_check_summary(
        artifacts_root=artifacts,
        artifacts_display_root="artifacts",
        skip_verify=False,
        skip_package=False,
        skip_web=False,
        skip_perf=False,
        gate_ok=True,
    )

    assert summary.ok is True
    assert summary.lines[0] == "Shipping Readiness Summary"
    assert "SHIP_CHECK_OK: true" in summary.lines
    assert "ARTIFACT: player_manifest artifacts/player_pkg/manifest.json present:true" in summary.lines
    assert "ARTIFACT: player_package_check artifacts/player_pkg/package_check.json present:true" in summary.lines
    assert "ARTIFACT: player_runtime_smoke artifacts/player_pkg/runtime_smoke.json present:true" in summary.lines
    assert "ARTIFACT: runtime_diagnostics_snapshot artifacts/runtime_diagnostics_snapshot.json present:true" in summary.lines
    assert "ARTIFACT: web_smoke artifacts/web_smoke.json present:true" in summary.lines
    assert "ARTIFACT: perf_compare artifacts/perf_compare.json present:true" in summary.lines
    assert "ARTIFACT: verify_bundle artifacts/verify_all_summary.json present:true" in summary.lines
    assert "WEB_SMOKE_ARTIFACT: artifacts/web_smoke.json" in summary.lines
    assert "WEB_SMOKE_CODES: WEB_BUILD_TOOLING_FAILED,WEB_INDEX_MISSING" in summary.lines


def test_ship_check_summary_marks_skipped_sections_contract(tmp_path: Path) -> None:
    from mesh_cli.ship_check import build_ship_check_summary

    artifacts = tmp_path / "artifacts"
    _touch(artifacts / "player_pkg" / "manifest.json")
    _touch(artifacts / "player_pkg" / "package_check.json")
    _touch(artifacts / "player_pkg" / "runtime_smoke.json")
    _touch(artifacts / "runtime_diagnostics_snapshot.json")

    summary = build_ship_check_summary(
        artifacts_root=artifacts,
        artifacts_display_root="artifacts",
        skip_verify=False,
        skip_package=False,
        skip_web=True,
        skip_perf=True,
        gate_ok=True,
    )

    assert summary.ok is True
    assert "SECTION: web SKIPPED" in summary.lines
    assert "SECTION: perf SKIPPED" in summary.lines
    assert "ARTIFACT: runtime_diagnostics_snapshot artifacts/runtime_diagnostics_snapshot.json present:true" in summary.lines
    assert "ARTIFACT: web_smoke artifacts/web_smoke.json present:false" in summary.lines
    assert "ARTIFACT: perf_compare artifacts/perf_compare.json present:false" in summary.lines
    assert "WEB_SMOKE_ARTIFACT: artifacts/web_smoke.json" in summary.lines
    assert "WEB_SMOKE_CODES: -" in summary.lines
    assert "SHIP_CHECK_OK: true" in summary.lines


def test_ship_check_summary_requires_runtime_diagnostics_when_smoke_runs_contract(tmp_path: Path) -> None:
    from mesh_cli.ship_check import build_ship_check_summary

    artifacts = tmp_path / "artifacts"
    _touch(artifacts / "player_pkg" / "manifest.json")
    _touch(artifacts / "player_pkg" / "package_check.json")
    _touch(artifacts / "player_pkg" / "runtime_smoke.json")
    _touch(artifacts / "web_smoke.json")
    _touch(artifacts / "perf_compare.json")

    summary = build_ship_check_summary(
        artifacts_root=artifacts,
        artifacts_display_root="artifacts",
        skip_verify=False,
        skip_package=False,
        skip_web=False,
        skip_perf=False,
        gate_ok=True,
    )

    assert summary.ok is False
    assert "ARTIFACT: runtime_diagnostics_snapshot artifacts/runtime_diagnostics_snapshot.json present:false" in summary.lines
