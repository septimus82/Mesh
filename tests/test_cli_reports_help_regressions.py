import sys

import pytest

from tests.subprocess_tools import run_checked


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())

@pytest.mark.parametrize("command, expected_substrings", [
    (["encounter-report", "--help"], [
        "usage: mesh_cli.py encounter-report",
        "Generate encounter balance report",
        "path",
        "--json",
        "--out OUT",
        "--themes THEMES",
        "--difficulty DIFFICULTY",
        "--only-dungeons",
        "--max-elite-delta MAX_ELITE_DELTA",
        "--max-spawn-delta MAX_SPAWN_DELTA",
        "--max-cost-overrun MAX_COST_OVERRUN",
        "--fail-on-overrun",
    ]),
    (["drift-check", "--help"], [
        "usage: mesh_cli.py drift-check",
        "Run encounter drift check with presets",
        "preset",
        "old_path",
        "new_path",
        "--json",
        "--out OUT",
    ]),
])
def test_reports_help_output(command, expected_substrings):
    """Verify that Reports commands help output contains expected substrings."""
    result = run_checked(
        [sys.executable, "mesh_cli.py"] + command,
    )
    assert result.returncode == 0
    output = _normalize_whitespace(result.stdout)

    for substring in expected_substrings:
        assert _normalize_whitespace(substring) in output
