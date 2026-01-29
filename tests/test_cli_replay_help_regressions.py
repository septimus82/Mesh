import sys

import pytest

from tests.subprocess_tools import run_checked


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())

@pytest.mark.parametrize("command, expected_substrings", [
    (["replay-script", "--help"], [
        "usage: mesh_cli.py replay-script",
        "Run a deterministic replay script",
        "path",
        "--out OUT",
    ]),
    (["replay-suite", "--help"], [
        "usage: mesh_cli.py replay-suite",
        "Run all deterministic replay scripts in a folder and print a summary",
        "folder",
        "--out OUT",
    ]),
    (["trace", "--help"], [
        "usage: mesh_cli.py trace",
        "Record or replay traces",
        "--record RECORD",
        "--replay REPLAY",
        "--world WORLD",
        "--overlay",
        "--assert-file ASSERT_FILE",
    ]),
])
def test_replay_help_output(command, expected_substrings):
    """Verify that Replay commands help output contains expected substrings."""
    result = run_checked(
        [sys.executable, "mesh_cli.py"] + command,
    )
    assert result.returncode == 0
    output = _normalize_whitespace(result.stdout)
    
    for substring in expected_substrings:
        assert _normalize_whitespace(substring) in output
