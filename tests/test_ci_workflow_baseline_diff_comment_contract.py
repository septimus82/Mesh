from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_ci_workflow_contains_baseline_diff_comment_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github" / "workflows" / "ci.yml"
    assert workflow.exists()

    text = workflow.read_text(encoding="utf-8")
    assert "Baseline diff markdown artifact" in text
    assert "artifacts/baseline_diff.md" in text
    assert "Baseline diff JSON artifact" in text
    assert "artifacts/baseline_diff.json" in text
    assert "--format json" in text
    assert "<!-- mesh-baseline-diff -->" in text
    assert "github.event_name == 'pull_request'" in text
    assert "pull-requests: write" in text
    assert "create-or-update-comment" in text
    assert "if regressions > 0" in text
