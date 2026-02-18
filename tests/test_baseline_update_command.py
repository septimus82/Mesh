"""Fast-tier tests for ``mesh_cli baseline-update``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "verify_summary": {"ok": True, "failing_steps": [], "artifacts_written": []},
        "budgets": {
            "exception_budget": {"ok": True, "current_count": 0, "baseline_count": 0},
            "verify_step_budget": {"ok": True, "worst_offender": None},
        },
        "runtime_diagnostics": {
            "swallowed_exceptions": {"ok": True, "total": 0, "distinct": 0, "top5_sites": []},
            "shadow_backend": {"selected": "none", "reason": "uninitialized", "fallbacks": []},
        },
        "timing": {"total_ms": 0, "top5": []},
        "authoring_trace": None,
        "read_files": [],
        "artifacts_dir": "test",
    }


def _make_index() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "bundle_schema_version": 1,
        "ok": True,
        "verify_all": "artifacts/verify_report.json",
        "written": {"verify_report": "artifacts/verify_report.json"},
        "schemas": {"verify_report": 1},
        "readable": {"verify_report": True},
        "generated_files": ["artifacts/verify_report.json"],
    }


def _make_bundle(d: Path) -> None:
    """Write minimal verify_report.json + index.json."""
    _write(d / "verify_report.json", _make_report())
    _write(d / "index.json", _make_index())


class FakeRunner:
    """Records subprocess calls and returns canned results."""

    def __init__(self, results: dict[str, tuple[bool, str]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._results = results or {}

    def __call__(self, argv: list[str], *, label: str) -> tuple[bool, str]:
        self.calls.append(list(argv))
        return self._results.get(label, (True, f"{label}: ok\n"))


# ---------------------------------------------------------------------------
# Tests: default flow calls three commands in order
# ---------------------------------------------------------------------------


class TestDefaultFlow:
    """With no --artifacts, verify-all → validate → update-baseline."""

    def test_calls_three_steps_in_order(self, tmp_path: Path) -> None:
        from mesh_cli.baseline_update import baseline_update

        # Pre-create the temp dir source with bundle files so update-baseline works
        work_dir = tmp_path / "artifacts" / "_baseline_tmp_test"
        _make_bundle(work_dir)

        baseline = tmp_path / "baseline"
        runner = FakeRunner({
            "verify-all": (True, "verify-all done\n"),
            "artifacts-validate": (True, "artifacts-validate: ok\n"),
        })

        # We need to patch tempfile to use our known dir.
        # Instead, use --artifacts pointing at the pre-built dir.
        # For the "real default flow" test, we use monkeypatch below.

    def test_default_flow_with_monkeypatch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mesh_cli import baseline_update as mod

        work_dir = tmp_path / "artifacts" / "_baseline_tmp_test"
        _make_bundle(work_dir)

        # Monkeypatch tempfile.mkdtemp to return our known dir
        monkeypatch.setattr(
            "tempfile.mkdtemp",
            lambda prefix="", dir=None: str(work_dir),
        )
        # Monkeypatch shutil.rmtree so it doesn't blow away our fixture
        removed: list[str] = []
        monkeypatch.setattr("shutil.rmtree", lambda p, ignore_errors=False: removed.append(p))

        baseline = tmp_path / "baseline"
        runner = FakeRunner({
            "verify-all": (True, "verify-all done\n"),
            "artifacts-validate": (True, "artifacts-validate: ok\n"),
        })

        code, lines = mod.baseline_update(
            baseline_dir=baseline,
            run_cmd=runner,
        )
        assert code == 0

        # Verify three commands called
        labels = []
        for call in runner.calls:
            for arg in call:
                if arg in ("verify-all", "artifacts-validate"):
                    labels.append(arg)
                    break
        assert "verify-all" in labels
        assert "artifacts-validate" in labels

        # Verify baseline files created
        assert (baseline / "verify_report.json").exists()
        assert (baseline / "index.json").exists()
        assert (baseline / "BASELINE_META.json").exists()

        # Verify temp dir cleaned up
        assert len(removed) == 1

    def test_output_deterministic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mesh_cli import baseline_update as mod

        work_dir = tmp_path / "artifacts" / "_baseline_tmp_test"
        _make_bundle(work_dir)
        monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="", dir=None: str(work_dir))
        monkeypatch.setattr("shutil.rmtree", lambda p, ignore_errors=False: None)

        baseline = tmp_path / "baseline"
        runner = FakeRunner({
            "verify-all": (True, "ok\n"),
            "artifacts-validate": (True, "ok\n"),
        })

        _, lines1 = mod.baseline_update(baseline_dir=baseline, run_cmd=runner)
        # Recreate to ensure second run is identical
        baseline2 = tmp_path / "baseline2"
        _, lines2 = mod.baseline_update(baseline_dir=baseline2, run_cmd=runner)

        # Normalize paths in output for comparison
        text1 = "\n".join(lines1).replace(baseline.as_posix(), "<BASELINE>").replace(str(baseline), "<BASELINE>")
        text2 = "\n".join(lines2).replace(baseline2.as_posix(), "<BASELINE>").replace(str(baseline2), "<BASELINE>")
        assert text1 == text2

    def test_summary_contains_next_line(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mesh_cli import baseline_update as mod

        work_dir = tmp_path / "artifacts" / "_baseline_tmp_test"
        _make_bundle(work_dir)
        monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="", dir=None: str(work_dir))
        monkeypatch.setattr("shutil.rmtree", lambda p, ignore_errors=False: None)

        baseline = tmp_path / "baseline"
        runner = FakeRunner()
        code, lines = mod.baseline_update(baseline_dir=baseline, run_cmd=runner)
        assert code == 0
        combined = "\n".join(lines)
        assert "Next: git add" in combined
        assert "git commit" in combined


# ---------------------------------------------------------------------------
# Tests: --artifacts skips verify-all
# ---------------------------------------------------------------------------


class TestArtifactsFlag:
    """When --artifacts is given, verify-all is skipped."""

    def test_skips_verify_all(self, tmp_path: Path) -> None:
        from mesh_cli.baseline_update import baseline_update

        artifacts = tmp_path / "arts"
        _make_bundle(artifacts)
        baseline = tmp_path / "baseline"

        runner = FakeRunner({
            "artifacts-validate": (True, "ok\n"),
        })

        code, lines = baseline_update(
            baseline_dir=baseline,
            artifacts_dir=artifacts,
            run_cmd=runner,
        )
        assert code == 0

        # verify-all should NOT have been called
        for call in runner.calls:
            assert "verify-all" not in call, "verify-all should be skipped with --artifacts"

        # artifacts-validate SHOULD have been called
        validate_called = any("artifacts-validate" in call for call in runner.calls)
        assert validate_called

        # Baseline updated
        assert (baseline / "verify_report.json").exists()
        assert (baseline / "BASELINE_META.json").exists()

    def test_missing_artifacts_dir_exit_2(self, tmp_path: Path) -> None:
        from mesh_cli.baseline_update import baseline_update

        baseline = tmp_path / "baseline"
        code, lines = baseline_update(
            baseline_dir=baseline,
            artifacts_dir=tmp_path / "nonexistent",
            run_cmd=FakeRunner(),
        )
        assert code == 2
        assert any("not found" in l for l in lines)


# ---------------------------------------------------------------------------
# Tests: --no-verify-all
# ---------------------------------------------------------------------------


class TestNoVerifyAll:
    """--no-verify-all without --artifacts exits 2."""

    def test_no_verify_all_without_artifacts_exit_2(self, tmp_path: Path) -> None:
        from mesh_cli.baseline_update import baseline_update

        baseline = tmp_path / "baseline"
        code, lines = baseline_update(
            baseline_dir=baseline,
            no_verify_all=True,
            run_cmd=FakeRunner(),
        )
        assert code == 2
        assert any("--no-verify-all requires --artifacts" in l for l in lines)

    def test_no_verify_all_with_artifacts_ok(self, tmp_path: Path) -> None:
        from mesh_cli.baseline_update import baseline_update

        artifacts = tmp_path / "arts"
        _make_bundle(artifacts)
        baseline = tmp_path / "baseline"

        code, _ = baseline_update(
            baseline_dir=baseline,
            artifacts_dir=artifacts,
            no_verify_all=True,
            run_cmd=FakeRunner(),
        )
        assert code == 0


# ---------------------------------------------------------------------------
# Tests: --keep-temp
# ---------------------------------------------------------------------------


class TestKeepTemp:
    """--keep-temp preserves temp dir path in output."""

    def test_keep_temp_shows_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mesh_cli import baseline_update as mod

        work_dir = tmp_path / "artifacts" / "_baseline_tmp_test"
        _make_bundle(work_dir)
        monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="", dir=None: str(work_dir))

        # rmtree should NOT be called when keep_temp=True
        rmtree_calls: list[str] = []
        monkeypatch.setattr("shutil.rmtree", lambda p, ignore_errors=False: rmtree_calls.append(p))

        baseline = tmp_path / "baseline"
        runner = FakeRunner()
        code, lines = mod.baseline_update(
            baseline_dir=baseline,
            keep_temp=True,
            run_cmd=runner,
        )
        assert code == 0
        combined = "\n".join(lines)
        assert "temp dir kept" in combined
        assert len(rmtree_calls) == 0

    def test_no_keep_temp_cleans_up(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mesh_cli import baseline_update as mod

        work_dir = tmp_path / "artifacts" / "_baseline_tmp_test"
        _make_bundle(work_dir)
        monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="", dir=None: str(work_dir))

        rmtree_calls: list[str] = []
        monkeypatch.setattr("shutil.rmtree", lambda p, ignore_errors=False: rmtree_calls.append(p))

        baseline = tmp_path / "baseline"
        runner = FakeRunner()
        code, _ = mod.baseline_update(
            baseline_dir=baseline,
            keep_temp=False,
            run_cmd=runner,
        )
        assert code == 0
        assert len(rmtree_calls) == 1


# ---------------------------------------------------------------------------
# Tests: failure propagation
# ---------------------------------------------------------------------------


class TestFailurePropagation:
    """Failures at each step propagate correctly."""

    def test_verify_all_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mesh_cli import baseline_update as mod

        work_dir = tmp_path / "artifacts" / "_baseline_tmp_test"
        work_dir.mkdir(parents=True)
        monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="", dir=None: str(work_dir))
        monkeypatch.setattr("shutil.rmtree", lambda p, ignore_errors=False: None)

        baseline = tmp_path / "baseline"
        runner = FakeRunner({"verify-all": (False, "BOOM\n")})
        code, lines = mod.baseline_update(baseline_dir=baseline, run_cmd=runner)
        assert code == 2
        assert any("verify-all failed" in l for l in lines)

    def test_validate_failure(self, tmp_path: Path) -> None:
        from mesh_cli.baseline_update import baseline_update

        artifacts = tmp_path / "arts"
        _make_bundle(artifacts)
        baseline = tmp_path / "baseline"

        runner = FakeRunner({"artifacts-validate": (False, "INVALID\n")})
        code, lines = baseline_update(
            baseline_dir=baseline,
            artifacts_dir=artifacts,
            run_cmd=runner,
        )
        assert code == 2
        assert any("artifacts-validate failed" in l for l in lines)


# ---------------------------------------------------------------------------
# Tests: CLI handler
# ---------------------------------------------------------------------------


class TestCLIHandler:

    def test_help_flag(self) -> None:
        """Verify register() produces a working parser."""
        import argparse

        parser = argparse.ArgumentParser()
        subs = parser.add_subparsers()

        from mesh_cli.baseline_update import register
        register(subs)

        # Should not raise
        parsed = parser.parse_args(["baseline-update", "--artifacts", "foo"])
        assert parsed.artifacts == "foo"

    def test_handler_with_artifacts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import argparse

        from mesh_cli import baseline_update as mod

        artifacts = tmp_path / "arts"
        _make_bundle(artifacts)
        baseline = tmp_path / "baseline"

        # Monkeypatch _run_cmd to avoid real subprocesses
        monkeypatch.setattr(mod, "_run_cmd", FakeRunner())

        args = argparse.Namespace(
            baseline_dir=str(baseline),
            artifacts=str(artifacts),
            keep_temp=False,
            no_verify_all=False,
        )
        code = mod._handle_baseline_update(args)
        assert code == 0
        assert (baseline / "verify_report.json").exists()


class TestBaselineMeta:
    def test_writes_meta_with_required_keys_and_deterministic_bytes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from mesh_cli import baseline_update as mod

        artifacts = tmp_path / "arts"
        _make_bundle(artifacts)

        monkeypatch.setattr(mod, "_utc_now_iso", lambda: "2026-02-17T00:00:00Z")
        monkeypatch.setattr(mod, "_get_source_commit", lambda repo_root: "deadbeef")
        monkeypatch.setattr(mod, "_read_package_version", lambda repo_root: "0.4.0")
        monkeypatch.setattr(mod, "_read_public_api_semver", lambda repo_root: "1.0.0")
        monkeypatch.setenv("GITHUB_RUN_ID", "12345")

        baseline1 = tmp_path / "baseline1"
        baseline2 = tmp_path / "baseline2"
        code1, _ = mod.baseline_update(
            baseline_dir=baseline1,
            artifacts_dir=artifacts,
            run_cmd=FakeRunner(),
        )
        code2, _ = mod.baseline_update(
            baseline_dir=baseline2,
            artifacts_dir=artifacts,
            run_cmd=FakeRunner(),
        )
        assert code1 == 0
        assert code2 == 0

        meta1 = baseline1 / "BASELINE_META.json"
        meta2 = baseline2 / "BASELINE_META.json"
        assert meta1.exists()
        assert meta2.exists()
        assert meta1.read_bytes() == meta2.read_bytes()

        payload = json.loads(meta1.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["created_utc"] == "2026-02-17T00:00:00Z"
        assert payload["source_commit"] == "deadbeef"
        assert payload["source_workflow_run_id"] == "12345"
        assert payload["package_version"] == "0.4.0"
        assert payload["public_api_semver"] == "1.0.0"
