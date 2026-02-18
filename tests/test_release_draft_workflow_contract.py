from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_release_draft_workflow_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github" / "workflows" / "release_draft.yml"
    assert workflow.exists()

    text = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "GITHUB_TOKEN" in text
    assert "release_notes.md" in text
    assert "release-preflight" in text
    assert '--tag "${{ inputs.tag }}"' in text
    assert "python -m mesh_cli artifacts-validate --artifacts artifacts_external" in text

    validate_idx = text.find("python -m mesh_cli artifacts-validate --artifacts artifacts_external")
    create_release_idx = text.find("Create draft GitHub release")
    assert validate_idx != -1
    assert create_release_idx != -1
    assert validate_idx < create_release_idx
