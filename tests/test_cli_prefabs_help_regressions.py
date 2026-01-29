import sys

import pytest

from tests.subprocess_tools import run_checked


def run_help(command):
    """Run a command with --help and return the output."""
    cmd = [sys.executable, "-m", "mesh_cli"] + command + ["--help"]
    result = run_checked(cmd)
    return result.stdout

def test_new_prefab_help():
    output = run_help(["new-prefab"])
    assert "Extract prefab from scene" in output
    assert "--prefab-id" in output
    assert "--from-scene" in output
    assert "--entity-name" in output
    assert "--remove-source" in output

def test_place_prefab_help():
    output = run_help(["place-prefab"])
    assert "Place prefab in scene" in output
    assert "--prefab-id" in output
    assert "--into" in output
    assert "--x" in output
    assert "--y" in output
    assert "--from-encounter-set" in output
    assert "--as-placeholder" in output

def test_prefab_help():
    output = run_help(["prefab"])
    assert "Manage prefabs" in output
    assert "prefab_args" in output
