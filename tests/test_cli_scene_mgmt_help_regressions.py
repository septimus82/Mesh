import sys

import pytest

from tests.subprocess_tools import run_checked


def test_new_scene_help_output():
    """Test that 'mesh new-scene --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "new-scene", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "new-scene",
        "Create a new scene",
        "name",
        "Scene name",
        "--template",
        "Scene template",
        "--encounter-layout",
        "Encounter layout preset",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"

def test_edit_scene_help_output():
    """Test that 'mesh edit-scene --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "edit-scene", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "edit-scene",
        "Edit scene properties",
        "path",
        "Path to scene file",
        "--budget",
        "Set encounter budget",
        "--elite-cap",
        "Set elite cap",
        "--allow-elites",
        "Set allow elites",
        "--boss-reserve",
        "Set boss budget reserve",
        "--add-transition",
        "Target scene for new transition",
        "--at",
        "Coordinates x,y",
        "--spawn-id",
        "Spawn ID in target scene",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"

def test_tidy_scene_help_output():
    """Test that 'mesh tidy-scene --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "tidy-scene", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "tidy-scene",
        "Format and compact scene file",
        "scene_path",
        "Path to scene file",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"

def test_list_scenes_help_output():
    """Test that 'mesh list-scenes --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "list-scenes", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "list-scenes",
        "List all scenes in the project",
        "--out",
        "Optional path to write JSON output",
    ]

    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"
def test_validate_help_output():
    """Test that 'mesh validate --help' output is stable."""
    cmd = [sys.executable, "-m", "mesh_cli", "validate", "--help"]
    result = run_checked(cmd)
    assert result.returncode == 0
    
    expected_substrings = [
        "usage:",
        "validate",
        "Validate a scene",
        "scene_path",
        "Path to scene file",
    ]
    
    for substring in expected_substrings:
        assert substring in result.stdout, f"Missing substring: {substring}"
