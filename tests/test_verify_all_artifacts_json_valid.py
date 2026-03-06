from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _stub_config():
    return type("C", (), {"world_file": "worlds/main_world.json"})()


def test_verify_all_artifacts_are_valid_json_objects_and_have_required_keys(monkeypatch, tmp_path) -> None:
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "worlds").mkdir()
    (repo / "scenes").mkdir()
    (repo / "worlds" / "main_world.json").write_text(
        json.dumps({"scenes": {"main": {"path": "scenes/main.json"}}, "start_scene": "main"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (repo / "scenes" / "main.json").write_text(json.dumps({"entities": []}, sort_keys=True) + "\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(
        mesh_cli.replay_suite,
        "run_replay_suite",
        lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []},
    )
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())

    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": [], "cache": {"hits": 0, "misses": 0, "entries": 0}},
    )
    monkeypatch.setattr(
        mesh_cli_legacy,
        "_inventory_list_scenes",
        lambda **_k: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}},
    )
    monkeypatch.setattr(
        mesh_cli_legacy,
        "_inventory_list_worlds",
        lambda **_k: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}},
    )

    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts"]) == 0

    artifacts_dir = repo / "artifacts"
    required = {
        "verify_all_summary.json": ["ok", "steps", "artifacts"],
        "verify_step_durations.json": ["schema_version", "total_ms", "steps"],
        "verify_step_budget_check.json": [
            "schema_version",
            "ok",
            "tolerance_ms",
            "candidates_used",
            "checked_steps",
            "offenders",
        ],
        "doctor_assets.json": ["ok", "errors", "warnings", "fixes", "cache"],
        "stamp_audit.json": ["ok", "case_count", "cases"],
        "brush_audit.json": ["ok", "case_count", "cases"],
        "macro_audit.json": ["ok", "case_count", "cases"],
        "room_audit.json": ["ok", "case_count", "cases"],
        "encounter_coverage_matrix.json": ["ok", "difficulties", "rows"],
        "exception_budget.json": [
            "schema_version",
            "ok",
            "baseline_count",
            "current_count",
            "files_scanned",
            "per_file_counts",
        ],
        "encounter_audit_summary.json": ["ok", "scene_count", "lines"],
        "encounter_audit_compact.json": ["ok", "scene_count", "rows"],
        "encounter_headroom.json": ["ok", "scene_count", "rows"],
        "shadow_backend.json": ["schema_version", "selected", "reason", "fallbacks"],
        "swallowed_exceptions.json": ["schema_version", "ok", "total", "distinct", "per_site"],
        "scenes_index.json": ["ok", "scenes"],
        "worlds_index.json": ["ok", "worlds"],
        "replays_summary.json": ["failed", "passed", "total", "results"],
    }

    for filename, keys in required.items():
        path = artifacts_dir / filename
        assert path.exists(), f"missing artifact: {filename}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{filename}: expected dict"
        for key in keys:
            assert key in data, f"{filename}: missing key {key!r}"

    # verify_report.json is only written with --report-json-artifact flag;
    # when present, validate its schema.
    verify_report_path = artifacts_dir / "verify_report.json"
    if verify_report_path.exists():
        report_data = json.loads(verify_report_path.read_text(encoding="utf-8"))
        assert isinstance(report_data, dict), "verify_report.json: expected dict"
        for key in [
            "schema_version",
            "artifacts_dir",
            "verify_summary",
            "budgets",
            "timing",
            "runtime_diagnostics",
            "authoring_trace",
            "read_files",
        ]:
            assert key in report_data, f"verify_report.json: missing key {key!r}"
        assert report_data["schema_version"] == 1

    # release_notes artifacts are optional via --release-notes-artifact;
    # when present, validate schema and markdown header.
    release_notes_json_path = artifacts_dir / "release_notes.json"
    if release_notes_json_path.exists():
        release_notes_data = json.loads(release_notes_json_path.read_text(encoding="utf-8"))
        assert isinstance(release_notes_data, dict), "release_notes.json: expected dict"
        for key in [
            "schema_version",
            "title",
            "package_version",
            "public_api_semver",
            "bundle",
            "snapshot",
            "files_read",
        ]:
            assert key in release_notes_data, f"release_notes.json: missing key {key!r}"
        assert release_notes_data["schema_version"] == 1
        release_notes_md_path = artifacts_dir / "release_notes.md"
        assert release_notes_md_path.exists(), "release_notes.md missing when release_notes.json exists"
        assert release_notes_md_path.read_text(encoding="utf-8").startswith("#")

    # baseline_diff.json is optional (written by CI baseline diff workflow steps);
    # when present, validate schema.
    baseline_diff_path = artifacts_dir / "baseline_diff.json"
    if baseline_diff_path.exists():
        baseline_diff_data = json.loads(baseline_diff_path.read_text(encoding="utf-8"))
        assert isinstance(baseline_diff_data, dict), "baseline_diff.json: expected dict"
        for key in [
            "schema_version",
            "regressions",
            "improvements",
            "changed",
            "counts",
            "ok",
        ]:
            assert key in baseline_diff_data, f"baseline_diff.json: missing key {key!r}"
        assert baseline_diff_data["schema_version"] == 1

    # overlay_perf.json is optional (written when --ci-bundle is enabled);
    # when present, validate schema.
    overlay_perf_path = artifacts_dir / "overlay_perf.json"
    if overlay_perf_path.exists():
        overlay_perf_data = json.loads(overlay_perf_path.read_text(encoding="utf-8"))
        assert isinstance(overlay_perf_data, dict), "overlay_perf.json: expected dict"
        for key in ["schema_version", "metrics"]:
            assert key in overlay_perf_data, f"overlay_perf.json: missing key {key!r}"
        assert overlay_perf_data["schema_version"] == 1
        metrics = overlay_perf_data["metrics"]
        assert isinstance(metrics, dict), "overlay_perf.json: metrics must be an object"
        for required in ["providers_total", "command_palette_provider"]:
            assert required in metrics, f"overlay_perf.json: missing metric {required!r}"

    perf_run_path = artifacts_dir / "perf_run.json"
    if perf_run_path.exists():
        perf_run_data = json.loads(perf_run_path.read_text(encoding="utf-8"))
        assert isinstance(perf_run_data, dict), "perf_run.json: expected dict"
        for key in ["schema_version", "mode", "ticks", "scenes", "totals"]:
            assert key in perf_run_data, f"perf_run.json: missing key {key!r}"
        assert perf_run_data["schema_version"] == 1

    perf_compare_path = artifacts_dir / "perf_compare.json"
    if perf_compare_path.exists():
        perf_compare_data = json.loads(perf_compare_path.read_text(encoding="utf-8"))
        assert isinstance(perf_compare_data, dict), "perf_compare.json: expected dict"
        for key in ["schema_version", "ok", "regressions", "diagnostics", "scene_count"]:
            assert key in perf_compare_data, f"perf_compare.json: missing key {key!r}"
        assert perf_compare_data["schema_version"] == 1

    # mypy_budget_diagnostic artifacts are optional (written when step budget
    # guard fails specifically due to mypy-gate slowness); when present,
    # validate minimal schema/text.
    mypy_diag_json_path = artifacts_dir / "mypy_budget_diagnostic.json"
    if mypy_diag_json_path.exists():
        mypy_diag_data = json.loads(mypy_diag_json_path.read_text(encoding="utf-8"))
        assert isinstance(mypy_diag_data, dict), "mypy_budget_diagnostic.json: expected dict"
        for key in [
            "schema_version",
            "step",
            "command_argv",
            "command_line",
            "wall_time_seconds",
            "files_checked",
            "summary",
            "cache",
            "python_version",
            "budget_row",
        ]:
            assert key in mypy_diag_data, f"mypy_budget_diagnostic.json: missing key {key!r}"
        assert mypy_diag_data["schema_version"] == 1
        mypy_diag_txt_path = artifacts_dir / "mypy_budget_diagnostic.txt"
        assert mypy_diag_txt_path.exists(), "mypy_budget_diagnostic.txt missing when json exists"

    # pytest_fast_budget_diagnostic artifacts are optional (written when step
    # budget guard fails specifically due to pytest-fast slowness); when
    # present, validate minimal schema/text.
    pytest_fast_diag_json_path = artifacts_dir / "pytest_fast_budget_diagnostic.json"
    if pytest_fast_diag_json_path.exists():
        pytest_fast_diag_data = json.loads(pytest_fast_diag_json_path.read_text(encoding="utf-8"))
        assert isinstance(pytest_fast_diag_data, dict), "pytest_fast_budget_diagnostic.json: expected dict"
        for key in [
            "schema_version",
            "step",
            "command_argv",
            "command_line",
            "wall_time_seconds",
            "threshold_ms",
            "current_ms",
            "python_version",
            "diagnostic_command_argv",
            "diagnostic_command_line",
            "diagnostic_returncode",
        ]:
            assert key in pytest_fast_diag_data, f"pytest_fast_budget_diagnostic.json: missing key {key!r}"
        assert pytest_fast_diag_data["schema_version"] == 1
        pytest_fast_diag_txt_path = artifacts_dir / "pytest_fast_budget_diagnostic.txt"
        assert pytest_fast_diag_txt_path.exists(), "pytest_fast_budget_diagnostic.txt missing when json exists"

    # index.json is only written with --artifact-index flag;
    # when present, validate its schema.
    index_path = artifacts_dir / "index.json"
    if index_path.exists():
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        assert isinstance(index_data, dict), "index.json: expected dict"
        for key in [
            "schema_version",
            "bundle_schema_version",
            "ok",
            "verify_all",
            "written",
            "readable",
            "generated_files",
        ]:
            assert key in index_data, f"index.json: missing key {key!r}"
        assert index_data["schema_version"] == 1
        assert index_data["bundle_schema_version"] == 1
        assert "artifact_index" in index_data["written"]
        assert isinstance(index_data["generated_files"], list)
        assert index_data["generated_files"] == sorted(index_data["generated_files"])
