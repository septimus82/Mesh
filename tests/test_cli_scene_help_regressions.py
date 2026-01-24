from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def test_scene_help_text_is_stable() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cp = subprocess.run(
        [sys.executable, "-m", "mesh_cli", "scene", "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=True,
    )

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    out = _norm(cp.stdout)

    # Shape: top-level scene command + core subcommands.
    assert " scene " in out
    assert "create" in out
    assert "tilemap" in out
    assert "stamp" in out
    assert "stamp-report" in out
    assert "macro-apply" in out
    assert "macro-report" in out
    assert "add-placeholder" in out
    assert "add-entity" in out
    assert "add-triggerzone-objective" in out
    assert "add-dialogue-choice-flag" in out
    assert "validate-backgrounds" in out
    assert "backgrounds" in out

    def assert_in_order(haystack: str, needles: list[str]) -> None:
        idx = 0
        for needle in needles:
            j = haystack.find(needle, idx)
            assert j != -1, f"missing: {needle}"
            idx = j + len(needle)

    # Enforce subcommand presentation order (don’t overfit exact spacing/line-wrapping).
    assert_in_order(
        out,
        [
            "create",
            "add-placeholder",
            "add-entity",
            "add-triggerzone-objective",
            "add-dialogue-choice-flag",
            "validate-backgrounds",
            "backgrounds",
            "tilemap",
            "stamp",
            "stamp-report",
            "macro-apply",
            "macro-report",
        ],
    )
