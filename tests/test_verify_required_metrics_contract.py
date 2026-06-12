from __future__ import annotations

import pytest

from mesh_cli.verify import _missing_required_verify_metric_artifacts

pytestmark = [pytest.mark.fast]


def test_missing_required_verify_metric_artifacts_reports_stable_names(tmp_path) -> None:
    assert _missing_required_verify_metric_artifacts(tmp_path) == [
        "verify_step_budget_check.json",
        "verify_step_durations.json",
    ]

    (tmp_path / "verify_step_durations.json").write_text("{}", encoding="utf-8")
    assert _missing_required_verify_metric_artifacts(tmp_path) == ["verify_step_budget_check.json"]

    (tmp_path / "verify_step_budget_check.json").write_text("{}", encoding="utf-8")
    assert _missing_required_verify_metric_artifacts(tmp_path) == []
