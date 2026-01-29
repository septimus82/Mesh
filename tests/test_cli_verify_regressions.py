from __future__ import annotations

import re
import sys
from pathlib import Path

from tests.subprocess_tools import run_checked


def test_verify_all_help_text_is_stable() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cp = run_checked(
        [sys.executable, "-m", "mesh_cli", "verify-all", "--help"],
        cwd=str(repo_root),
        check=True,
    )

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    out = _norm(cp.stdout)

    # 1) Usage line shape (don’t overfit argv0/prog).
    assert " verify-all " in out
    assert "--out-dir OUT_DIR" in out
    assert "--artifacts ARTIFACTS" in out
    assert "--no-index" in out

    # 2) Lock important semantics text.
    assert "Optional pytest args after `--` for verify-demo only" in out
    assert "(selection-changing args are blocked)" in out
    assert "Optional directory to write scene/world indices" in out
    assert "Optional directory to write CI-friendly JSON artifacts" in out
    assert "Disable writing indices even if --out-dir is provided" in out

    # 3) Enforce option order (substring order, not exact formatting).
    def assert_in_order(haystack: str, needles: list[str]) -> None:
        idx = 0
        for needle in needles:
            j = haystack.find(needle, idx)
            assert j != -1, f"missing: {needle}"
            idx = j + len(needle)

    assert_in_order(
        out,
        [
            "-h, --help",
            "--out-dir OUT_DIR",
            "--artifacts ARTIFACTS",
            "--no-index",
        ],
    )


def test_verify_demo_output_is_stable(monkeypatch, capsys) -> None:
    import engine.tooling.verify_demo
    import mesh_cli

    monkeypatch.setattr(engine.tooling.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)

    rc = mesh_cli.main(["verify-demo"])
    assert rc == 0

    out = capsys.readouterr().out.replace("\r\n", "\n")
    expected = "{\n  \"code\": 0,\n  \"ok\": true\n}\n"
    assert out == expected
