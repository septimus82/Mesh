"""Tests for mesh_cli.debug_report (debug-report CLI command)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def artifacts_dir(tmp_path: Path) -> Path:
    """Create a temp artifacts directory with minimal JSON fixtures."""
    d = tmp_path / "artifacts"
    d.mkdir()

    (d / "exception_budget.json").write_text(
        json.dumps(
            {
                "baseline_count": 10,
                "current_count": 8,
                "ok": True,
                "schema_version": 1,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    (d / "verify_step_durations.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "steps": [
                    {"ms": 500, "name": "step-a", "ok": True},
                    {"ms": 300, "name": "step-b", "ok": True},
                ],
                "total_ms": 800,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    (d / "verify_step_budget_check.json").write_text(
        json.dumps(
            {
                "checked_steps": [
                    {
                        "budget_ms": 1000,
                        "current_ms": 500,
                        "delta_ms": -500,
                        "effective_ms": 500,
                        "median_ms": None,
                        "name": "step-a",
                        "ok": True,
                        "tolerance_ms": 50,
                    },
                ],
                "offenders": [],
                "ok": True,
                "schema_version": 2,
                "tolerance_ms": 50,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    (d / "shadow_backend.json").write_text(
        json.dumps(
            {
                "selected": "hard_shadow_v2",
                "reason": "gpu_capable",
                "fallbacks": ["soft_shadow", "none"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return d


@pytest.fixture()
def empty_artifacts_dir(tmp_path: Path) -> Path:
    """An artifacts directory with no files at all."""
    d = tmp_path / "empty_artifacts"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDebugReportWithAllArtifacts:
    """When all artifact JSON files are present, output is fully populated."""

    def test_stdout_contains_verify_health_snapshot(self, artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        rc = main(["--artifacts", str(artifacts_dir)])
        assert rc == 0
        out = capsys.readouterr().out

        assert "Verify Health Snapshot" in out
        assert "exception_budget: 8/10 ok=true" in out
        assert "verify_total_ms: 800" in out
        assert "step_budget_ok: true" in out
        assert "worst_step: none" in out

    def test_stdout_contains_shadow_backend(self, artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        main(["--artifacts", str(artifacts_dir)])
        out = capsys.readouterr().out

        assert "Shadow Backend" in out
        assert "selected: hard_shadow_v2" in out
        assert "reason: gpu_capable" in out
        assert "fallbacks: soft_shadow, none" in out

    def test_stdout_contains_swallowed_exceptions_unavailable(self, artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        main(["--artifacts", str(artifacts_dir)])
        out = capsys.readouterr().out

        assert "Swallowed Exceptions" in out
        assert "(unavailable)" in out

    def test_json_out_written(self, artifacts_dir: Path, tmp_path: Path) -> None:
        from mesh_cli.debug_report import main

        json_path = tmp_path / "out" / "report.json"
        rc = main(["--artifacts", str(artifacts_dir), "--json-out", str(json_path)])
        assert rc == 0
        assert json_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert isinstance(payload["verify_snapshot"], dict)
        assert payload["verify_snapshot"]["exception_current"] == 8
        assert payload["verify_snapshot"]["exception_baseline"] == 10
        assert payload["verify_snapshot"]["exception_ok"] is True
        assert payload["verify_snapshot"]["verify_total_ms"] == 800
        assert payload["verify_snapshot"]["step_budget_ok"] is True
        assert payload["shadow_backend"]["selected"] == "hard_shadow_v2"
        assert payload["shadow_backend"]["reason"] == "gpu_capable"
        assert payload["shadow_backend"]["fallbacks"] == ["soft_shadow", "none"]
        assert payload["swallowed_exceptions"] is None

    def test_deterministic_output(self, artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Running twice produces byte-identical stdout."""
        from mesh_cli.debug_report import main

        main(["--artifacts", str(artifacts_dir)])
        first = capsys.readouterr().out

        main(["--artifacts", str(artifacts_dir)])
        second = capsys.readouterr().out

        assert first == second


class TestDebugReportMissingArtifacts:
    """When artifact files are missing or corrupt, output uses '?' and '(unavailable)'."""

    def test_all_missing_does_not_raise(self, empty_artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        rc = main(["--artifacts", str(empty_artifacts_dir)])
        assert rc == 0

    def test_missing_files_yield_question_marks(self, empty_artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        main(["--artifacts", str(empty_artifacts_dir)])
        out = capsys.readouterr().out

        assert "exception_budget: ?/? ok=?" in out
        assert "verify_total_ms: ?" in out
        assert "step_budget_ok: ?" in out
        assert "worst_step: ? delta_ms=?" in out

    def test_missing_shadow_backend_yields_question_marks(self, empty_artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        main(["--artifacts", str(empty_artifacts_dir)])
        out = capsys.readouterr().out

        assert "selected: ?" in out
        assert "reason: ?" in out
        assert "fallbacks: ?" in out

    def test_missing_swallowed_yields_unavailable(self, empty_artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        main(["--artifacts", str(empty_artifacts_dir)])
        out = capsys.readouterr().out

        assert "Swallowed Exceptions" in out
        assert "(unavailable)" in out

    def test_corrupt_json_does_not_crash(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        d = tmp_path / "corrupt"
        d.mkdir()
        (d / "exception_budget.json").write_text("{invalid json", encoding="utf-8")
        (d / "verify_step_durations.json").write_text("null", encoding="utf-8")
        (d / "verify_step_budget_check.json").write_text("[1,2,3]", encoding="utf-8")
        (d / "shadow_backend.json").write_text("not json at all!", encoding="utf-8")

        rc = main(["--artifacts", str(d)])
        assert rc == 0

        out = capsys.readouterr().out
        assert "Verify Health Snapshot" in out
        assert "Shadow Backend" in out
        assert "Swallowed Exceptions" in out

    def test_json_out_with_missing_artifacts(self, empty_artifacts_dir: Path, tmp_path: Path) -> None:
        from mesh_cli.debug_report import main

        json_path = tmp_path / "report.json"
        rc = main(["--artifacts", str(empty_artifacts_dir), "--json-out", str(json_path)])
        assert rc == 0
        assert json_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["shadow_backend"] is None
        assert payload["swallowed_exceptions"] is None
        # verify_snapshot should still be a dict with None values
        vs = payload["verify_snapshot"]
        assert vs["exception_current"] is None
        assert vs["exception_baseline"] is None


class TestDebugReportWithSwallowedExceptions:
    """When swallowed_exceptions.json is present, its data is rendered."""

    def test_swallowed_per_site(self, artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from mesh_cli.debug_report import main

        (artifacts_dir / "swallowed_exceptions.json").write_text(
            json.dumps(
                {
                    "total": 5,
                    "distinct": 2,
                    "per_site": {
                        "engine.lighting.shadows": 3,
                        "engine.scene_controller": 2,
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        main(["--artifacts", str(artifacts_dir)])
        out = capsys.readouterr().out

        assert "total=5 distinct=2" in out
        assert "engine.lighting.shadows: count=3" in out
        assert "engine.scene_controller: count=2" in out

    def test_swallowed_per_site_list_format(self, artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The schema-v1 artifact uses per_site as a list of dicts."""
        from mesh_cli.debug_report import main

        (artifacts_dir / "swallowed_exceptions.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "total": 7,
                    "distinct": 2,
                    "per_site": [
                        {"site": "engine.lighting.shadows", "count": 5},
                        {"site": "engine.scene_controller", "count": 2},
                    ],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        main(["--artifacts", str(artifacts_dir)])
        out = capsys.readouterr().out

        assert "total=7 distinct=2" in out
        assert "engine.lighting.shadows: count=5" in out
        assert "engine.scene_controller: count=2" in out

    def test_swallowed_with_offenders(self, artifacts_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Budget check with offenders shows worst step."""
        from mesh_cli.debug_report import main

        (artifacts_dir / "verify_step_budget_check.json").write_text(
            json.dumps(
                {
                    "checked_steps": [],
                    "offenders": [
                        {"name": "step-slow", "delta_ms": 200},
                        {"name": "step-slower", "delta_ms": 500},
                    ],
                    "ok": False,
                    "schema_version": 2,
                    "tolerance_ms": 50,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        main(["--artifacts", str(artifacts_dir)])
        out = capsys.readouterr().out

        assert "step_budget_ok: false" in out
        assert "worst_step: step-slower delta_ms=500" in out


class TestBuildPayload:
    """Unit tests for the payload builder."""

    def test_payload_schema_version(self, artifacts_dir: Path) -> None:
        from mesh_cli.debug_report import build_debug_report_payload

        payload = build_debug_report_payload(artifacts_dir=artifacts_dir)
        assert payload["schema_version"] == 1

    def test_payload_verify_keys(self, artifacts_dir: Path) -> None:
        from mesh_cli.debug_report import build_debug_report_payload

        payload = build_debug_report_payload(artifacts_dir=artifacts_dir)
        vs = payload["verify_snapshot"]
        assert isinstance(vs, dict)
        expected_keys = {
            "exception_current",
            "exception_baseline",
            "exception_ok",
            "verify_total_ms",
            "step_budget_ok",
            "worst_step",
            "worst_delta_ms",
        }
        assert expected_keys <= set(vs.keys())

    def test_payload_nonexistent_dir(self, tmp_path: Path) -> None:
        from mesh_cli.debug_report import build_debug_report_payload

        payload = build_debug_report_payload(artifacts_dir=tmp_path / "does_not_exist")
        assert payload["schema_version"] == 1
        assert payload["shadow_backend"] is None
        assert payload["swallowed_exceptions"] is None


class TestFetchSwallowedExceptionsSnapshot:
    """Unit tests for the verify.py swallowed exceptions snapshot helper."""

    def test_snapshot_with_known_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import engine.swallowed_exceptions as se

        monkeypatch.setattr(
            se,
            "read_counts",
            lambda: {"engine.lighting.shadows": 3, "engine.scene_controller": 1},
        )
        from mesh_cli.verify import _fetch_swallowed_exceptions_snapshot

        result = _fetch_swallowed_exceptions_snapshot()

        assert result["schema_version"] == 1
        assert result["ok"] is True
        assert result["total"] == 4
        assert result["distinct"] == 2
        # per_site sorted by count desc, then site asc
        assert result["per_site"] == [
            {"site": "engine.lighting.shadows", "count": 3},
            {"site": "engine.scene_controller", "count": 1},
        ]

    def test_snapshot_deterministic_ordering(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sites with equal counts are sorted alphabetically."""
        import engine.swallowed_exceptions as se

        monkeypatch.setattr(
            se,
            "read_counts",
            lambda: {"z_site": 2, "a_site": 2, "m_site": 5},
        )
        from mesh_cli.verify import _fetch_swallowed_exceptions_snapshot

        result = _fetch_swallowed_exceptions_snapshot()

        sites = [r["site"] for r in result["per_site"]]
        assert sites == ["m_site", "a_site", "z_site"]

    def test_snapshot_empty_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import engine.swallowed_exceptions as se

        monkeypatch.setattr(se, "read_counts", lambda: {})
        from mesh_cli.verify import _fetch_swallowed_exceptions_snapshot

        result = _fetch_swallowed_exceptions_snapshot()

        assert result["ok"] is True
        assert result["total"] == 0
        assert result["distinct"] == 0
        assert result["per_site"] == []

    def test_snapshot_import_failure_returns_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import engine.swallowed_exceptions as se

        monkeypatch.setattr(se, "read_counts", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        from mesh_cli.verify import _fetch_swallowed_exceptions_snapshot

        result = _fetch_swallowed_exceptions_snapshot()

        assert result["schema_version"] == 1
        assert result["ok"] is False
        assert result["total"] == 0
        assert result["distinct"] == 0
        assert result["per_site"] == []

    def test_snapshot_twice_is_deterministic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import engine.swallowed_exceptions as se

        monkeypatch.setattr(
            se,
            "read_counts",
            lambda: {"b": 10, "a": 10, "c": 1},
        )
        from mesh_cli.verify import _fetch_swallowed_exceptions_snapshot

        first = _fetch_swallowed_exceptions_snapshot()
        second = _fetch_swallowed_exceptions_snapshot()
        assert first == second
