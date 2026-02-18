from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_update_ci_baseline_workflow_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github" / "workflows" / "update_ci_baseline.yml"
    assert workflow.exists()

    text = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "verify-all --artifacts artifacts --ci-bundle --release-notes-artifact" in text
    assert "baseline-update --baseline-dir tooling/metrics/ci_baseline_artifacts --artifacts artifacts --no-verify-all" in text
    assert "create-pull-request" in text
    assert "pull-requests: write" in text
