import sys

import pytest

from tests.subprocess_tools import run_checked


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())

@pytest.mark.parametrize("command, expected_substrings", [
    (["pipeline", "--help"], [
        "usage: mesh_cli.py pipeline",
        "Apply plan, validate, and optionally run demo/preset",
        "plan_path",
        "path",
        "--plan PLAN_PATH_OPT",
        "--world PATH_OPT",
        "--ai-safe",
        "--dry-run",
        "--strict",
        "--strict-compact",
        "--check-reachability",
        "--check-orphans",
        "--check-refs",
        "--demo",
        "--preset PRESET",
    ]),
    (["recipes", "--help"], [
        "usage: mesh_cli.py recipes",
        "Show workflow recipes",
    ]),
    (["run-preset", "--help"], [
        "usage: mesh_cli.py run-preset",
        "Run a command preset",
        "name",
    ]),
    (["preset", "--help"], [
        "usage: mesh_cli.py preset",
        "Preset management",
        "{lint}",
    ]),
    (["preset", "lint", "--help"], [
        "usage: mesh_cli.py preset lint",
        "Lint presets in config",
    ]),
])
def test_pipeline_help_output(command, expected_substrings):
    """Verify that Pipeline commands help output contains expected substrings."""
    result = run_checked(
        [sys.executable, "mesh_cli.py"] + command,
    )
    assert result.returncode == 0
    output = _normalize_whitespace(result.stdout)
    
    for substring in expected_substrings:
        assert _normalize_whitespace(substring) in output
