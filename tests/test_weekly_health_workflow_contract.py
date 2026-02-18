from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_weekly_health_workflow_includes_trends_update() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github" / "workflows" / "weekly_health.yml"
    assert workflow.exists()

    text = workflow.read_text(encoding="utf-8")
    assert "python -m mesh_cli trends-update --artifacts artifacts" in text
    assert "Weekly trends to Step Summary" in text
    assert "verify_total_ms (last 8)" in text
    assert "swallowed_total (last 8)" in text
