import sys

import pytest

from tests.subprocess_tools import run_checked


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())

@pytest.mark.parametrize("command, expected_substrings", [
    (["check", "--help"], [
        "usage: mesh_cli.py check",
        "Run quality checks",
        "--world WORLD",
        "--full",
        "--replay-trace",
        "--frozen",
    ]),
    (["validate-all", "--help"], [
        "usage: mesh_cli.py validate-all",
        "Run all validators",
        "--path PATH",
        "--strict",
        "--schema-strict",
        "--strict-compact",
        "--check-reachability",
        "--check-orphans",
        "--check-refs",
    ]),
    (["validate-events", "--help"], [
        "usage: mesh_cli.py validate-events",
        "Validate event definitions",
    ]),
    (["doctor", "--help"], [
        "usage: mesh_cli.py doctor",
        "Diagnose project health",
        "--world WORLD",
        "--quiet",
        "--explain",
        "--json",
    ]),
    (["explain", "--help"], [
        "usage: mesh_cli.py explain",
        "Explain doctor/validation failures",
        "--world WORLD",
        "--last",
        "--json",
    ]),
    (["cli-smoke", "--help"], [
        "usage: mesh_cli.py cli-smoke",
        "Run CLI smoke tests",
    ]),
])
def test_qa_help_output(command, expected_substrings):
    """Verify that QA commands help output contains expected substrings."""
    result = run_checked(
        [sys.executable, "mesh_cli.py"] + command,
    )
    assert result.returncode == 0
    output = _normalize_whitespace(result.stdout)
    
    for substring in expected_substrings:
        assert _normalize_whitespace(substring) in output
