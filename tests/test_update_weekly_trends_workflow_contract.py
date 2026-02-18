from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_update_weekly_trends_workflow_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github" / "workflows" / "update_weekly_trends.yml"
    assert workflow.exists()

    text = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "schedule" in text
    assert "python -m mesh_cli trends-update --artifacts artifacts --trend-file tooling/metrics/weekly_trends.json" in text
    assert "python -m mesh_cli trends-report --trend-file tooling/metrics/weekly_trends.json" in text
    assert "GITHUB_STEP_SUMMARY" in text
    assert "create-pull-request" in text
    assert "pull-requests: write" in text
