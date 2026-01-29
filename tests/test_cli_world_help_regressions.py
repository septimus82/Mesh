import sys

import pytest

from tests.subprocess_tools import run_checked


def normalize_help_output(output: str) -> str:
    """Normalize help output for comparison."""
    lines = output.splitlines()
    # Remove empty lines and strip whitespace
    lines = [line.strip() for line in lines if line.strip()]
    return "\n".join(lines)

def test_world_help_output():
    """Test that 'mesh world --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "world", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    normalized = normalize_help_output(result.stdout)
    
    expected_substrings = [
        "usage:",
        "world",
        "World authoring utilities",
        "add-scene",
        "Add or update a scene entry in a world file",
        "link-scenes",
        "Insert SceneTransition entities linking two scenes",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"

def test_validate_world_help_output():
    """Test that 'mesh validate-world --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "validate-world", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "validate-world",
        "Validate world structure",
        "world_path",
        "Path to world file",
        "--no-events",
        "Skip event validation",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"

def test_auto_wire_transitions_help_output():
    """Test that 'mesh auto-wire-transitions --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "auto-wire-transitions", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "auto-wire-transitions",
        "Auto-wire scene transitions",
        "world_path",
        "World file",
        "--apply",
        "Apply changes",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"

def test_world_graph_help_output():
    """Test that 'mesh world-graph --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "world-graph", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "world-graph",
        "Export world graph",
        "world_path",
        "World file",
        "output",
        "Output DOT file",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"
