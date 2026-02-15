"""Fast-tier tests for ``mesh_cli artifacts-diff``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_report(
    *,
    ok: bool = True,
    exception_budget_ok: bool = True,
    step_budget_ok: bool = True,
    trace_budget_ok: bool | None = None,
    swallowed_total: int = 0,
    swallowed_distinct: int = 0,
    swallowed_ok: bool = True,
    shadow_selected: str = "opengl",
    shadow_reason: str = "preferred",
    total_ms: int = 100,
) -> dict:
    """Build a minimal verify_report.json payload for testing."""
    report: dict = {
        "schema_version": 1,
        "verify_summary": {"ok": ok},
        "budgets": {
            "exception_budget": {"ok": exception_budget_ok, "current_count": 0, "baseline_count": 0},
            "verify_step_budget": {"ok": step_budget_ok, "worst_offender": None},
        },
        "runtime_diagnostics": {
            "swallowed_exceptions": {
                "ok": swallowed_ok,
                "total": swallowed_total,
                "distinct": swallowed_distinct,
            },
            "shadow_backend": {
                "selected": shadow_selected,
                "reason": shadow_reason,
            },
        },
        "timing": {"total_ms": total_ms, "top5": []},
    }
    if trace_budget_ok is not None:
        report["budgets"]["authoring_trace_budget"] = {"ok": trace_budget_ok}
    return report


def _make_bundle(d: Path, report: dict, schemas: dict | None = None) -> None:
    """Write verify_report.json and index.json into *d*."""
    _write(d / "verify_report.json", report)
    written = {"verify_report": "artifacts/verify_report.json"}
    _write(
        d / "index.json",
        {
            "schema_version": 1,
            "bundle_schema_version": 1,
            "ok": True,
            "verify_all": "artifacts/verify_report.json",
            "written": written,
            "schemas": schemas or {},
            "readable": {"verify_report": True},
            "generated_files": ["artifacts/verify_report.json"],
        },
    )


# ---------------------------------------------------------------------------
# compute_diff unit tests
# ---------------------------------------------------------------------------


class TestRegressionDetection:
    """Regressions: ok flips true→false, budget ok flips, counts increase."""

    def test_verify_ok_flip_true_to_false(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(ok=True)
        curr = _make_report(ok=False)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "verify_summary.ok" for it in reg)

    def test_verify_ok_flip_none_to_false(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report()
        base["verify_summary"]["ok"] = None
        curr = _make_report(ok=False)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "verify_summary.ok" for it in reg)

    def test_exception_budget_ok_flip(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(exception_budget_ok=True)
        curr = _make_report(exception_budget_ok=False)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "budgets.exception_budget.ok" for it in reg)

    def test_step_budget_ok_flip(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(step_budget_ok=True)
        curr = _make_report(step_budget_ok=False)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "budgets.verify_step_budget.ok" for it in reg)

    def test_trace_budget_ok_flip(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(trace_budget_ok=True)
        curr = _make_report(trace_budget_ok=False)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "budgets.authoring_trace_budget.ok" for it in reg)

    def test_swallowed_total_increase(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(swallowed_total=5)
        curr = _make_report(swallowed_total=10)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "swallowed_exceptions.total" for it in reg)

    def test_swallowed_distinct_increase(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(swallowed_distinct=2)
        curr = _make_report(swallowed_distinct=5)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "swallowed_exceptions.distinct" for it in reg)

    def test_swallowed_ok_flip(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(swallowed_ok=True)
        curr = _make_report(swallowed_ok=False)
        items = compute_diff(base, curr)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "swallowed_exceptions.ok" for it in reg)

    def test_timing_total_ms_regression(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(total_ms=100)
        curr = _make_report(total_ms=200)
        items = compute_diff(base, curr, timing_threshold_ms=50)
        reg = [it for it in items if it.category == "regression"]
        assert any(it.field == "timing.total_ms" for it in reg)


class TestImprovementDetection:
    """Improvements: ok flips false→true, counts decrease."""

    def test_verify_ok_flip_false_to_true(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(ok=False)
        curr = _make_report(ok=True)
        items = compute_diff(base, curr)
        imp = [it for it in items if it.category == "improvement"]
        assert any(it.field == "verify_summary.ok" for it in imp)

    def test_swallowed_total_decrease(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(swallowed_total=10)
        curr = _make_report(swallowed_total=5)
        items = compute_diff(base, curr)
        imp = [it for it in items if it.category == "improvement"]
        assert any(it.field == "swallowed_exceptions.total" for it in imp)

    def test_timing_total_ms_improvement(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(total_ms=200)
        curr = _make_report(total_ms=100)
        items = compute_diff(base, curr, timing_threshold_ms=50)
        imp = [it for it in items if it.category == "improvement"]
        assert any(it.field == "timing.total_ms" for it in imp)

    def test_exception_budget_ok_improvement(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(exception_budget_ok=False)
        curr = _make_report(exception_budget_ok=True)
        items = compute_diff(base, curr)
        imp = [it for it in items if it.category == "improvement"]
        assert any(it.field == "budgets.exception_budget.ok" for it in imp)


class TestMissingFields:
    """Graceful handling of missing/None fields."""

    def test_empty_reports(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        items = compute_diff({}, {})
        assert items == []

    def test_missing_budgets(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = {"verify_summary": {"ok": True}}
        curr = {"verify_summary": {"ok": True}}
        items = compute_diff(base, curr)
        assert items == []

    def test_partial_runtime_diagnostics(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report()
        curr = {"verify_summary": {"ok": True}}
        items = compute_diff(base, curr)
        # Should not crash — missing fields are simply skipped
        assert isinstance(items, list)

    def test_missing_timing(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(total_ms=100)
        curr = {"verify_summary": {"ok": True}}
        # Missing timing in curr — no timing diff
        items = compute_diff(base, curr)
        assert not any(it.field == "timing.total_ms" for it in items)

    def test_none_ok_values_no_diff(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report()
        base["verify_summary"]["ok"] = None
        curr = _make_report()
        curr["verify_summary"]["ok"] = None
        items = compute_diff(base, curr)
        assert not any(it.field == "verify_summary.ok" for it in items)


class TestDeterminism:
    """Output must be deterministic across runs."""

    def test_items_sorted_deterministically(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(ok=True, exception_budget_ok=True, swallowed_total=0)
        curr = _make_report(ok=False, exception_budget_ok=False, swallowed_total=5)
        items1 = compute_diff(base, curr)
        items2 = compute_diff(base, curr)
        assert [(it.field, it.category) for it in items1] == [(it.field, it.category) for it in items2]

    def test_text_output_deterministic(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff, format_text

        base = _make_report(ok=True, swallowed_total=0)
        curr = _make_report(ok=False, swallowed_total=5)
        items = compute_diff(base, curr)
        assert format_text(items) == format_text(items)

    def test_regressions_before_improvements(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(ok=False, exception_budget_ok=True)
        curr = _make_report(ok=True, exception_budget_ok=False)
        items = compute_diff(base, curr)
        categories = [it.category for it in items]
        assert categories == sorted(categories, key=lambda c: {"regression": 0, "improvement": 1, "changed": 2}[c])


class TestNoChange:
    """Identical reports should produce no diff items."""

    def test_identical_reports(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        report = _make_report()
        items = compute_diff(report, report)
        assert items == []

    def test_timing_within_threshold(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(total_ms=100)
        curr = _make_report(total_ms=130)
        items = compute_diff(base, curr, timing_threshold_ms=50)
        assert not any(it.field == "timing.total_ms" for it in items)

    def test_timing_sentinel_zero_skipped(self) -> None:
        """Base total_ms=0 is a sentinel — timing diff is skipped."""
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(total_ms=0)
        curr = _make_report(total_ms=50000)
        items = compute_diff(base, curr, timing_threshold_ms=50)
        assert not any(it.field == "timing.total_ms" for it in items)


class TestSchemaChanges:
    """Schema version diffs from index.json."""

    def test_schema_version_change_detected(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report()
        curr = _make_report()
        items = compute_diff(
            base, curr,
            base_schemas={"exception_budget": 1},
            curr_schemas={"exception_budget": 2},
        )
        chg = [it for it in items if it.category == "changed"]
        assert any(it.field == "schema.exception_budget" for it in chg)

    def test_schema_version_same_no_diff(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report()
        curr = _make_report()
        items = compute_diff(
            base, curr,
            base_schemas={"exception_budget": 1},
            curr_schemas={"exception_budget": 1},
        )
        assert not any(it.field.startswith("schema.") for it in items)


class TestShadowBackendChanges:
    """Shadow backend field changes show as 'changed'."""

    def test_selected_changed(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(shadow_selected="opengl")
        curr = _make_report(shadow_selected="vulkan")
        items = compute_diff(base, curr)
        chg = [it for it in items if it.category == "changed"]
        assert any(it.field == "shadow_backend.selected" for it in chg)

    def test_reason_changed(self) -> None:
        from mesh_cli.artifacts_diff import compute_diff

        base = _make_report(shadow_reason="preferred")
        curr = _make_report(shadow_reason="fallback")
        items = compute_diff(base, curr)
        chg = [it for it in items if it.category == "changed"]
        assert any(it.field == "shadow_backend.reason" for it in chg)


# ---------------------------------------------------------------------------
# diff_artifacts integration tests (file I/O)
# ---------------------------------------------------------------------------


class TestDiffArtifactsIntegration:
    """End-to-end tests with real filesystem bundles."""

    def test_no_regressions(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        report = _make_report()
        _make_bundle(base_dir, report)
        _make_bundle(curr_dir, report)
        output, has_reg = diff_artifacts(base_dir, curr_dir)
        assert has_reg is False
        assert "No differences" in output

    def test_regression_detected(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        _make_bundle(base_dir, _make_report(ok=True))
        _make_bundle(curr_dir, _make_report(ok=False))
        output, has_reg = diff_artifacts(base_dir, curr_dir)
        assert has_reg is True
        assert "REGRESSION" in output.upper()

    def test_markdown_format(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        _make_bundle(base_dir, _make_report(ok=True))
        _make_bundle(curr_dir, _make_report(ok=False))
        output, _ = diff_artifacts(base_dir, curr_dir, fmt="markdown")
        assert "# Artifacts Diff" in output
        assert "## Regressions" in output

    def test_missing_report_error(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        base_dir.mkdir()
        curr_dir.mkdir()
        output, has_reg = diff_artifacts(base_dir, curr_dir)
        assert "error" in output.lower()
        assert has_reg is False

    def test_fallback_without_index(self, tmp_path: Path) -> None:
        """Reads verify_report.json directly when index.json is absent."""
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        _write(base_dir / "verify_report.json", _make_report(ok=True))
        _write(curr_dir / "verify_report.json", _make_report(ok=False))
        output, has_reg = diff_artifacts(base_dir, curr_dir)
        assert has_reg is True

    def test_schema_diff_from_indexes(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        _make_bundle(base_dir, _make_report(), schemas={"exception_budget": 1})
        _make_bundle(curr_dir, _make_report(), schemas={"exception_budget": 2})
        output, _ = diff_artifacts(base_dir, curr_dir)
        assert "schema.exception_budget" in output


# ---------------------------------------------------------------------------
# Exit code tests
# ---------------------------------------------------------------------------


class TestExitCodes:
    """``--fail-on-regression`` exit code behaviour."""

    def test_no_regression_exit_0(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        report = _make_report()
        _make_bundle(base_dir, report)
        _make_bundle(curr_dir, report)
        _output, has_reg = diff_artifacts(base_dir, curr_dir)
        # Simulate: exit 0 when no regression
        assert has_reg is False

    def test_regression_exit_2(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import diff_artifacts

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        _make_bundle(base_dir, _make_report(ok=True))
        _make_bundle(curr_dir, _make_report(ok=False))
        _output, has_reg = diff_artifacts(base_dir, curr_dir)
        # Simulate: exit 2 when --fail-on-regression
        assert has_reg is True

    def test_handle_exit_code_no_regression(self, tmp_path: Path) -> None:
        """CLI handler returns 0 when no regressions and --fail-on-regression is set."""
        import argparse

        from mesh_cli.artifacts_diff import _handle_artifacts_diff

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        report = _make_report()
        _make_bundle(base_dir, report)
        _make_bundle(curr_dir, report)
        args = argparse.Namespace(
            base=str(base_dir), curr=str(curr_dir),
            format="text", fail_on_regression=True,
        )
        assert _handle_artifacts_diff(args) == 0

    def test_handle_exit_code_regression(self, tmp_path: Path) -> None:
        """CLI handler returns 2 when regressions and --fail-on-regression is set."""
        import argparse

        from mesh_cli.artifacts_diff import _handle_artifacts_diff

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        _make_bundle(base_dir, _make_report(ok=True))
        _make_bundle(curr_dir, _make_report(ok=False))
        args = argparse.Namespace(
            base=str(base_dir), curr=str(curr_dir),
            format="text", fail_on_regression=True,
        )
        assert _handle_artifacts_diff(args) == 2

    def test_handle_exit_code_no_flag(self, tmp_path: Path) -> None:
        """CLI handler returns 0 even with regressions when flag is not set."""
        import argparse

        from mesh_cli.artifacts_diff import _handle_artifacts_diff

        base_dir = tmp_path / "base"
        curr_dir = tmp_path / "curr"
        _make_bundle(base_dir, _make_report(ok=True))
        _make_bundle(curr_dir, _make_report(ok=False))
        args = argparse.Namespace(
            base=str(base_dir), curr=str(curr_dir),
            format="text", fail_on_regression=False,
        )
        assert _handle_artifacts_diff(args) == 0


# ---------------------------------------------------------------------------
# Format output tests
# ---------------------------------------------------------------------------


class TestFormatOutput:
    """Verify text and markdown formatters produce expected content."""

    def test_text_no_diff(self) -> None:
        from mesh_cli.artifacts_diff import format_text

        output = format_text([])
        assert "No differences" in output
        assert "0 regression(s)" in output

    def test_text_with_items(self) -> None:
        from mesh_cli.artifacts_diff import DiffItem, format_text

        items = [
            DiffItem("verify_summary.ok", True, False, "regression"),
            DiffItem("swallowed_exceptions.total", 10, 5, "improvement"),
        ]
        output = format_text(items)
        assert "REGRESSIONS:" in output
        assert "IMPROVEMENTS:" in output
        assert "verify_summary.ok" in output
        assert "1 regression(s)" in output

    def test_markdown_with_items(self) -> None:
        from mesh_cli.artifacts_diff import DiffItem, format_markdown

        items = [
            DiffItem("verify_summary.ok", True, False, "regression"),
        ]
        output = format_markdown(items)
        assert "# Artifacts Diff" in output
        assert "## Regressions" in output
        assert "| `verify_summary.ok`" in output
        assert "1 regression(s)" in output

    def test_markdown_no_diff(self) -> None:
        from mesh_cli.artifacts_diff import format_markdown

        output = format_markdown([])
        assert "No differences" in output


# ---------------------------------------------------------------------------
# update_baseline tests
# ---------------------------------------------------------------------------


class TestUpdateBaseline:
    """Tests for the --update-baseline copy logic."""

    def test_copies_required_files(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import update_baseline

        curr = tmp_path / "curr"
        baseline = tmp_path / "baseline"
        report = _make_report()
        _make_bundle(curr, report)

        code, messages = update_baseline(baseline, curr)
        assert code == 0
        assert (baseline / "verify_report.json").exists()
        assert (baseline / "index.json").exists()
        assert any("updated" in m for m in messages)

    def test_content_matches_source(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import update_baseline

        curr = tmp_path / "curr"
        baseline = tmp_path / "baseline"
        report = _make_report()
        _make_bundle(curr, report)

        update_baseline(baseline, curr)

        src_report = (curr / "verify_report.json").read_bytes()
        dst_report = (baseline / "verify_report.json").read_bytes()
        assert src_report == dst_report

        src_index = (curr / "index.json").read_bytes()
        dst_index = (baseline / "index.json").read_bytes()
        assert src_index == dst_index

    def test_missing_curr_files_exit_2(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import update_baseline

        curr = tmp_path / "curr"
        curr.mkdir()
        baseline = tmp_path / "baseline"

        code, messages = update_baseline(baseline, curr)
        assert code == 2
        assert any("error" in m for m in messages)
        assert not (baseline / "verify_report.json").exists()

    def test_missing_index_only_exit_2(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import update_baseline

        curr = tmp_path / "curr"
        curr.mkdir()
        _write(curr / "verify_report.json", _make_report())
        # No index.json
        baseline = tmp_path / "baseline"

        code, messages = update_baseline(baseline, curr)
        assert code == 2

    def test_overwrites_existing_baseline(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import update_baseline

        curr = tmp_path / "curr"
        baseline = tmp_path / "baseline"

        # First write
        _make_bundle(curr, _make_report(ok=True))
        update_baseline(baseline, curr)
        v1 = json.loads((baseline / "verify_report.json").read_text(encoding="utf-8"))
        assert v1["verify_summary"]["ok"] is True

        # Overwrite with different data
        _make_bundle(curr, _make_report(ok=False))
        code, _ = update_baseline(baseline, curr)
        assert code == 0
        v2 = json.loads((baseline / "verify_report.json").read_text(encoding="utf-8"))
        assert v2["verify_summary"]["ok"] is False

    def test_determinism_same_bytes(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import update_baseline

        curr = tmp_path / "curr"
        report = _make_report()
        _make_bundle(curr, report)

        b1 = tmp_path / "b1"
        b2 = tmp_path / "b2"
        update_baseline(b1, curr)
        update_baseline(b2, curr)

        assert (b1 / "verify_report.json").read_bytes() == (b2 / "verify_report.json").read_bytes()
        assert (b1 / "index.json").read_bytes() == (b2 / "index.json").read_bytes()

    def test_creates_baseline_dir(self, tmp_path: Path) -> None:
        from mesh_cli.artifacts_diff import update_baseline

        curr = tmp_path / "curr"
        _make_bundle(curr, _make_report())
        baseline = tmp_path / "deep" / "nested" / "baseline"

        code, _ = update_baseline(baseline, curr)
        assert code == 0
        assert baseline.is_dir()

    def test_diff_against_updated_baseline(self, tmp_path: Path) -> None:
        """Round-trip: update baseline, then diff against it."""
        from mesh_cli.artifacts_diff import diff_artifacts, update_baseline

        curr = tmp_path / "curr"
        baseline = tmp_path / "baseline"
        report = _make_report()
        _make_bundle(curr, report)
        update_baseline(baseline, curr)

        output, has_reg = diff_artifacts(baseline, curr)
        assert has_reg is False
        assert "No differences" in output

    def test_cli_handler_update_baseline(self, tmp_path: Path) -> None:
        """CLI handler in update-baseline mode returns 0 on success."""
        import argparse

        from mesh_cli.artifacts_diff import _handle_artifacts_diff

        curr = tmp_path / "curr"
        baseline = tmp_path / "baseline"
        _make_bundle(curr, _make_report())

        args = argparse.Namespace(
            base=str(baseline), curr=str(curr),
            format="text", fail_on_regression=False,
            update_baseline=True,
        )
        assert _handle_artifacts_diff(args) == 0
        assert (baseline / "verify_report.json").exists()

    def test_cli_handler_update_baseline_missing_curr(self, tmp_path: Path) -> None:
        """CLI handler in update-baseline mode returns 2 when curr dir missing."""
        import argparse

        from mesh_cli.artifacts_diff import _handle_artifacts_diff

        baseline = tmp_path / "baseline"
        args = argparse.Namespace(
            base=str(baseline), curr=str(tmp_path / "nonexistent"),
            format="text", fail_on_regression=False,
            update_baseline=True,
        )
        assert _handle_artifacts_diff(args) == 2
