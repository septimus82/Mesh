from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_ci_workflow_contains_arcade3_canary_lane() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github" / "workflows" / "ci.yml"
    assert workflow.exists()

    text = workflow.read_text(encoding="utf-8")
    assert "arcade3-canary" in text
    assert "arcade3-canary (required, py3.11)" in text
    assert "python -m pip install \"arcade>=3,<4\"" in text
    assert "tests/test_shadow_backend_selection_determinism.py" in text
    # The live shadow path (Milestone 12's per-light compositor) replaced the composite path whose two tests
    # Milestone 13 retired (57182dd); the canary covers it now.
    assert "tests/test_shadow_shapes.py" in text
    assert "tests/test_lighting_module_path_resolution.py" in text
    assert "Arcade 3.x runtime replay smoke" in text
    assert "python -m mesh_cli replay-hash" in text
    assert "--replay replays/00_smoke_dump_state.json" in text
    assert "--expect replays/00_smoke_dump_state.hash.json" in text
    assert "Upload Arcade 3 canary artifacts" in text
    assert "name: arcade3-canary-artifacts" in text
    assert "artifacts/arcade3_canary/**" in text
    assert "Arcade 3 canary replay summary" in text
    assert "GITHUB_STEP_SUMMARY" in text
    assert "artifacts/arcade3_canary/replay_hash.json" in text
    assert "Arcade 3.x installed wheel replay smoke" in text
    assert "python -m build --wheel" in text
    assert "python -m venv .venv_arcade3_wheel" in text
    assert "--out artifacts/arcade3_canary/wheel_replay_hash.json" in text


def test_every_test_file_the_canary_runs_exists() -> None:
    """A deleted test left in the list stopped the whole canary at "file not found" (from M13 until this repair)."""
    import re

    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    listed = sorted(set(re.findall(r"tests/[A-Za-z0-9_]+\.py", text)))
    assert listed, "the workflow lists test files"
    missing = [path for path in listed if not (repo_root / path).is_file()]
    assert missing == []
