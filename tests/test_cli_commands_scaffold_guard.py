import pytest


def test_mesh_cli_commands_package_has_no_command_modules() -> None:
    """Regression guard.

    We use the top-level module convention (mesh_cli/<group>.py). The legacy
    mesh_cli/commands/ scaffolds must not reappear.
    """

    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    commands_dir = repo_root / "mesh_cli" / "commands"
    assert commands_dir.is_dir(), "mesh_cli/commands/ package should exist"

    offenders: list[str] = []
    for p in commands_dir.iterdir():
        if p.name == "__init__.py":
            continue
        if p.name == "__pycache__":
            continue
        if p.suffix == ".py":
            offenders.append(p.name)

    assert not offenders, f"Unexpected command modules under mesh_cli/commands/: {sorted(offenders)}"


@pytest.mark.parametrize(
    "module_name",
    [
        "mesh_cli.commands.scene",
        "mesh_cli.commands.room",
        "mesh_cli.commands.verify",
        "mesh_cli.commands.macro",
    ],
)
def test_legacy_scaffold_command_modules_do_not_exist(module_name: str) -> None:
    """Regression guard.

    These modules were previously present as incomplete scaffolds. They must not be
    importable; real commands live in mesh_cli/{scene,room,verify,macro}.py.
    """

    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)



def test_mesh_cli_help_contains_no_placeholder_markers() -> None:
    """Regression guard.

    If a placeholder command is exposed, it tends to leak "TO-DO" / "placeholder"
    strings into the help text.
    """

    import sys
    from pathlib import Path

    from tests.subprocess_tools import run_checked

    repo_root = Path(__file__).resolve().parent.parent
    res = run_checked(
        [sys.executable, "-m", "mesh_cli", "--help"],
        cwd=str(repo_root),
    )
    assert res.returncode == 0, (res.stdout + "\n" + res.stderr).strip()
    help_text = (res.stdout + "\n" + res.stderr).lower()
    assert "todo" not in help_text
    assert "placeholder" not in help_text
