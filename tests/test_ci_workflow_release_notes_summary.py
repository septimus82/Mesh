from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_ci_workflow_includes_release_notes_verify_flags_and_summary_step() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow_path = repo_root / ".github" / "workflows" / "ci.yml"
    text = workflow_path.read_text(encoding="utf-8")

    assert "--ci-bundle --release-notes-artifact" in text
    assert "release_notes.md" in text
    assert "GITHUB_STEP_SUMMARY" in text
