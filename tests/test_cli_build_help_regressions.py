import subprocess
import sys
import pytest

def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())

@pytest.mark.parametrize("command, expected_substrings", [
    (["build-demo", "--help"], [
        "usage: mesh_cli.py build-demo",
        "--diff-from DIFF_FROM",
        "--strict-audit",
    ]),
    (["dist", "--help"], [
        "usage: mesh_cli.py dist",
        "--profile PROFILE",
        "--world WORLD",
        "--out OUT",
    ]),
])
def test_build_help_output(command, expected_substrings):
    """Verify that Build commands help output contains expected substrings."""
    result = subprocess.run(
        [sys.executable, "mesh_cli.py"] + command,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = _normalize_whitespace(result.stdout)
    
    for substring in expected_substrings:
        assert _normalize_whitespace(substring) in output
