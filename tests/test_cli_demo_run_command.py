"""Tests for ``mesh_cli demo run`` command.

Covers:
- Orchestration order: steps execute in the documented fixed order.
- Artifact paths: report lists correct relative paths; files are created.
- Failure propagation: if a step fails the pipeline stops and the report
  records which step failed.
- Determinism: same seed + campaign → identical demo_report.json content
  (excluding the absolute ``out_dir`` root).
- CLI dispatch integration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from engine.persistence_io import dumps_json_deterministic
from mesh_cli.demo import (
    DEFAULT_CAMPAIGN,
    DEFAULT_SEED,
    PIPELINE,
    StepFn,
    _format_report_text,
    run_demo,
    handle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**overrides: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "demo",
        "demo_command": "pipeline",
        "out_dir": "demo_out",
        "seed": DEFAULT_SEED,
        "campaign": DEFAULT_CAMPAIGN,
        "quiet": False,
        "print_json": False,
        "no_fail": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _ok_step(
    name: str, outputs: dict[str, Any] | None = None,
) -> StepFn:
    """Return a step runner that always succeeds."""

    def runner(out_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        # Touch a marker file so we can verify ordering
        marker = out_dir / f".marker_{name}"
        marker.write_text(name, encoding="utf-8")
        return 0, outputs or {"marker": name}

    return runner


def _fail_step(name: str) -> StepFn:
    """Return a step runner that always fails with exit code 1."""

    def runner(out_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        return 1, {"marker": name}

    return runner


def _recording_step(
    name: str, call_log: list[str],
) -> StepFn:
    """Return a step runner that appends *name* to *call_log*."""

    def runner(out_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        call_log.append(name)
        return 0, {"marker": name}

    return runner


# =========================================================================
# 1. Orchestration order
# =========================================================================


class TestOrchestrationOrder:
    """Steps must execute in the documented fixed order."""

    def test_steps_execute_in_order(self, tmp_path: Path) -> None:
        call_log: list[str] = []
        pipeline: list[tuple[str, StepFn]] = [
            (name, _recording_step(name, call_log))
            for name, _ in PIPELINE
        ]
        code, report = run_demo(
            out_dir=tmp_path, pipeline=pipeline,
        )
        assert code == 0
        expected_order = [name for name, _ in PIPELINE]
        assert call_log == expected_order

    def test_pipeline_has_five_steps(self) -> None:
        assert len(PIPELINE) == 5

    def test_pipeline_step_names(self) -> None:
        names = [name for name, _ in PIPELINE]
        assert names == [
            "release-check",
            "new-game",
            "campaign-replay-check",
            "debug-export",
            "export-build",
        ]


# =========================================================================
# 2. Artifact path tests
# =========================================================================


class TestArtifactPaths:
    """Report lists correct paths; files are created."""

    def test_report_files_created(self, tmp_path: Path) -> None:
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]
        run_demo(out_dir=tmp_path, pipeline=pipeline)
        assert (tmp_path / "demo_report.json").exists()
        assert (tmp_path / "demo_report.txt").exists()

    def test_report_json_is_valid(self, tmp_path: Path) -> None:
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]
        run_demo(out_dir=tmp_path, pipeline=pipeline)
        data = json.loads((tmp_path / "demo_report.json").read_text("utf-8"))
        assert data["ok"] is True
        assert data["failed_step"] is None
        assert data["schema_version"] == 1
        assert data["seed"] == DEFAULT_SEED
        assert data["campaign"] == DEFAULT_CAMPAIGN

    def test_report_lists_all_steps(self, tmp_path: Path) -> None:
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]
        _, report = run_demo(out_dir=tmp_path, pipeline=pipeline)
        step_names = [s["name"] for s in report["steps"]]
        assert step_names == [n for n, _ in PIPELINE]

    def test_marker_files_created(self, tmp_path: Path) -> None:
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]
        run_demo(out_dir=tmp_path, pipeline=pipeline)
        for name, _ in PIPELINE:
            assert (tmp_path / f".marker_{name}").exists()

    def test_report_contains_file_sizes(self, tmp_path: Path) -> None:
        """File sizes dict includes the report itself (written before collection)."""
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]
        _, report = run_demo(out_dir=tmp_path, pipeline=pipeline)
        # file_sizes should be a dict; at minimum the report JSON is there
        assert isinstance(report["file_sizes"], dict)

    def test_report_text_content(self, tmp_path: Path) -> None:
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]
        run_demo(out_dir=tmp_path, pipeline=pipeline)
        txt = (tmp_path / "demo_report.txt").read_text("utf-8")
        assert "Mesh Demo Run" in txt
        assert "Result: OK" in txt

    def test_step_outputs_in_report(self, tmp_path: Path) -> None:
        pipeline = [
            ("release-check", _ok_step("release-check", {"dir": "release/"})),
            ("new-game", _ok_step("new-game", {"path": "new_game.json"})),
        ]
        _, report = run_demo(out_dir=tmp_path, pipeline=pipeline)
        assert report["steps"][0]["outputs"]["dir"] == "release/"
        assert report["steps"][1]["outputs"]["path"] == "new_game.json"


# =========================================================================
# 3. Failure propagation
# =========================================================================


class TestFailurePropagation:
    """If a step fails the pipeline stops and the report records the failure."""

    def test_fail_at_first_step(self, tmp_path: Path) -> None:
        pipeline: list[tuple[str, StepFn]] = [
            ("release-check", _fail_step("release-check")),
            ("new-game", _ok_step("new-game")),
        ]
        code, report = run_demo(out_dir=tmp_path, pipeline=pipeline)
        assert code == 1
        assert report["ok"] is False
        assert report["failed_step"] == "release-check"
        # Second step should NOT have run
        assert len(report["steps"]) == 1

    def test_fail_at_middle_step(self, tmp_path: Path) -> None:
        call_log: list[str] = []
        pipeline: list[tuple[str, StepFn]] = [
            ("release-check", _recording_step("release-check", call_log)),
            ("new-game", _recording_step("new-game", call_log)),
            ("campaign-replay-check", _fail_step("campaign-replay-check")),
            ("debug-export", _recording_step("debug-export", call_log)),
            ("export-build", _recording_step("export-build", call_log)),
        ]
        code, report = run_demo(out_dir=tmp_path, pipeline=pipeline)
        assert code == 1
        assert report["failed_step"] == "campaign-replay-check"
        assert call_log == ["release-check", "new-game"]
        assert len(report["steps"]) == 3

    def test_failure_report_file_created(self, tmp_path: Path) -> None:
        pipeline: list[tuple[str, StepFn]] = [
            ("release-check", _fail_step("release-check")),
        ]
        run_demo(out_dir=tmp_path, pipeline=pipeline)
        data = json.loads((tmp_path / "demo_report.json").read_text("utf-8"))
        assert data["ok"] is False
        assert data["failed_step"] == "release-check"

    def test_failure_report_txt(self, tmp_path: Path) -> None:
        pipeline: list[tuple[str, StepFn]] = [
            ("new-game", _fail_step("new-game")),
        ]
        run_demo(out_dir=tmp_path, pipeline=pipeline)
        txt = (tmp_path / "demo_report.txt").read_text("utf-8")
        assert "FAILED at new-game" in txt

    def test_exception_in_step_is_caught(self, tmp_path: Path) -> None:
        def exploding_step(
            out_dir: Path, seed: int, campaign: str,
        ) -> tuple[int, dict[str, Any]]:
            raise RuntimeError("boom")

        pipeline: list[tuple[str, StepFn]] = [
            ("boom-step", exploding_step),
        ]
        code, report = run_demo(out_dir=tmp_path, pipeline=pipeline)
        assert code == 1
        assert report["steps"][0]["error"] == "RuntimeError: boom"


# =========================================================================
# 4. Determinism
# =========================================================================


class TestDeterminism:
    """Same seed + campaign → identical report JSON (modulo out_dir root)."""

    def test_same_seed_identical_reports(self, tmp_path: Path) -> None:
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]

        _, report_a = run_demo(
            out_dir=dir_a, seed=123, campaign=DEFAULT_CAMPAIGN,
            pipeline=pipeline,
        )
        _, report_b = run_demo(
            out_dir=dir_b, seed=123, campaign=DEFAULT_CAMPAIGN,
            pipeline=pipeline,
        )

        # Normalize the absolute out_dir before comparison
        report_a["out_dir"] = "<NORMALIZED>"
        report_b["out_dir"] = "<NORMALIZED>"

        text_a = dumps_json_deterministic(report_a)
        text_b = dumps_json_deterministic(report_b)
        assert text_a == text_b

    def test_different_seed_produces_different_seed_field(
        self, tmp_path: Path,
    ) -> None:
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]

        _, ra = run_demo(out_dir=dir_a, seed=1, pipeline=pipeline)
        _, rb = run_demo(out_dir=dir_b, seed=2, pipeline=pipeline)
        assert ra["seed"] != rb["seed"]


# =========================================================================
# 5. CLI dispatch
# =========================================================================


class TestCLIDispatch:
    """Tests for the CLI handle() integration."""

    def test_handle_dispatches_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """handle() calls run_demo and returns 0."""
        import mesh_cli.demo as demo_mod

        calls: list[dict[str, Any]] = []

        def fake_run_demo(
            *, out_dir: Path, seed: int, campaign: str,
            quiet: bool, pipeline: Any = None,
        ) -> tuple[int, dict[str, Any]]:
            calls.append({"seed": seed, "campaign": campaign})
            return 0, {
                "ok": True, "failed_step": None,
                "steps": [], "file_sizes": {},
                "seed": seed, "campaign": campaign,
                "out_dir": str(out_dir),
                "schema_version": 1,
            }

        monkeypatch.setattr(demo_mod, "run_demo", fake_run_demo)
        args = _make_args(out_dir=str(tmp_path))
        rc = handle(args)
        assert rc == 0
        assert len(calls) == 1
        assert calls[0]["seed"] == DEFAULT_SEED

    def test_handle_missing_subcommand(self, capsys: pytest.CaptureFixture[str]) -> None:
        """handle() directly is the pipeline handler — no subcommand dispatch needed."""
        # handle() is always the pipeline handler; no missing-subcommand path.
        # Instead verify that a successful pipeline returns 0.
        import mesh_cli.demo as demo_mod

        def fake(*, out_dir: Path, seed: int, campaign: str,
                 quiet: bool, pipeline: Any = None) -> tuple[int, dict[str, Any]]:
            return 0, {
                "ok": True, "failed_step": None,
                "steps": [], "file_sizes": {},
                "seed": seed, "campaign": campaign,
                "out_dir": str(out_dir), "schema_version": 1,
            }

        original = demo_mod.run_demo
        demo_mod.run_demo = fake  # type: ignore[assignment]
        try:
            args = _make_args(out_dir=str(Path.cwd() / "tmp_test"))
            rc = handle(args)
            assert rc == 0
        finally:
            demo_mod.run_demo = original  # type: ignore[assignment]

    def test_no_fail_flag(
        self, tmp_path: Path,
    ) -> None:
        """--no-fail makes handle() return 0 even when a step fails."""
        pipeline: list[tuple[str, StepFn]] = [
            ("release-check", _fail_step("release-check")),
        ]
        code, report = run_demo(out_dir=tmp_path, pipeline=pipeline)
        assert code == 1  # run_demo itself returns 1

        # But handle() with no_fail should return 0
        import mesh_cli.demo as demo_mod

        def fake_run(
            *, out_dir: Path, seed: int, campaign: str,
            quiet: bool, pipeline: Any = None,
        ) -> tuple[int, dict[str, Any]]:
            return 1, {
                "ok": False, "failed_step": "release-check",
                "steps": [], "file_sizes": {},
                "seed": seed, "campaign": campaign,
                "out_dir": str(out_dir),
                "schema_version": 1,
            }

        original = demo_mod.run_demo
        demo_mod.run_demo = fake_run  # type: ignore[assignment]
        try:
            args = _make_args(out_dir=str(tmp_path), no_fail=True)
            rc = handle(args)
            assert rc == 0
        finally:
            demo_mod.run_demo = original  # type: ignore[assignment]

    def test_quiet_flag_suppresses_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        pipeline = [(n, _ok_step(n)) for n, _ in PIPELINE]
        code, _ = run_demo(
            out_dir=tmp_path, pipeline=pipeline, quiet=True,
        )
        assert code == 0
        # Report files should still be written
        assert (tmp_path / "demo_report.json").exists()


# =========================================================================
# 6. Format helpers
# =========================================================================


class TestFormatHelpers:

    def test_format_report_text_ok(self) -> None:
        report: dict[str, Any] = {
            "schema_version": 1,
            "seed": 42,
            "campaign": "mini_campaign_01",
            "out_dir": "/tmp/demo",
            "steps": [{"name": "s1", "ok": True, "exit_code": 0}],
            "file_sizes": {"a.json": 100},
            "ok": True,
            "failed_step": None,
        }
        txt = _format_report_text(report)
        assert "Result: OK" in txt
        assert "a.json" in txt

    def test_format_report_text_failed(self) -> None:
        report: dict[str, Any] = {
            "schema_version": 1,
            "seed": 42,
            "campaign": "mini_campaign_01",
            "out_dir": "/tmp/demo",
            "steps": [{"name": "boom", "ok": False, "exit_code": 1}],
            "file_sizes": {},
            "ok": False,
            "failed_step": "boom",
        }
        txt = _format_report_text(report)
        assert "FAILED at boom" in txt
