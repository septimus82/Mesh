from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def test_plan_help_text_is_stable() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cp = subprocess.run(
        [sys.executable, "-m", "mesh_cli", "plan", "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=True,
    )

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    out = _norm(cp.stdout)
    out_ws_stripped = re.sub(r"\s+", "", cp.stdout)

    assert " plan " in out
    assert "usage:__main__.pyplan" in out_ws_stripped

    # Argparse can hard-wrap help output (sometimes splitting words). Ignore whitespace.
    for token in [
        "fix-from-doctor",
        "lint",
        "lint-ai",
        "diff",
        "history",
        "show",
        "test",
        "test-ai",
        "summarize",
        "schema",
    ]:
        assert token in out_ws_stripped

    def assert_in_order(haystack: str, needles: list[str]) -> None:
        idx = 0
        for needle in needles:
            j = haystack.find(needle, idx)
            assert j != -1, f"missing: {needle}"
            idx = j + len(needle)

    # Lock broad presentation order, without overfitting spacing.
    assert_in_order(
        out_ws_stripped,
        [
            "fix-from-doctor",
            "lint",
            "lint-ai",
            "diff",
            "history",
            "show",
            "test",
            "test-ai",
            "summarize",
            "schema",
        ],
    )
