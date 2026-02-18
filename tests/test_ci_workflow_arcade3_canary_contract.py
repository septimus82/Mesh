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
    assert "tests/test_hard_shadows_composite_activate_fallback.py" in text
    assert "tests/test_hard_shadows_composite_draw_signature_fallback.py" in text
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
