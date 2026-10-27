import contextlib
import io
import subprocess


def run_cli_help(command):
    # In process: each subprocess cost ~2.4 s of interpreter start and imports for a parser lookup (27 s for this
    # file). A fresh interpreter's `mesh_cli --help` is still checked, in test_cli_commands_scaffold_guard.py.
    from mesh_cli.main import main

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            code = main(command + ["--help"])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return subprocess.CompletedProcess(command, code, out.getvalue(), "")

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
