import sys

import pytest

from tests.subprocess_tools import run_checked


def run_cli_help(command):
    cmd = [sys.executable, "-m", "mesh_cli"] + command + ["--help"]
    result = run_checked(cmd)
    return result

def test_authoring_commands_help():
    commands = [
        "new-npc",
        "place-npc",
        "new-quest",
        "new-behaviour",
        "add-puzzle",
    ]
    for cmd in commands:
        result = run_cli_help([cmd])
        assert result.returncode == 0, f"{cmd} help failed"
        # Check for usage string which usually contains the command name
        assert "usage:" in result.stdout

def test_misc_commands_help():
    commands = [
        "play",
        "demo",
        "wizard",
        "docs",
        "dump-state",
    ]
    for cmd in commands:
        result = run_cli_help([cmd])
        assert result.returncode == 0, f"{cmd} help failed"
        assert "usage:" in result.stdout

def test_demo_subcommands_help():
    result = run_cli_help(["demo", "run"])
    assert result.returncode == 0
    
    result = run_cli_help(["demo", "scaffold-objective"])
    assert result.returncode == 0
