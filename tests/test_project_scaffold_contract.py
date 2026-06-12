"""Contract tests for project scaffolding."""

import json
from pathlib import Path

from engine.project_scaffold import create_project, validate_new_project_target


def test_validate_new_project_target(tmp_path: Path) -> None:
    # 1. Non-existent path is valid
    target = tmp_path / "new_project"
    valid, msg = validate_new_project_target(target)
    assert valid, f"Non-existent path should be valid: {msg}"

    # 2. Empty directory is valid
    target.mkdir()
    valid, msg = validate_new_project_target(target)
    assert valid, f"Empty directory should be valid: {msg}"

    # 3. Non-empty directory is invalid
    (target / "some_file.txt").touch()
    valid, msg = validate_new_project_target(target)
    assert not valid, "Non-empty directory should be invalid"
    assert "not empty" in msg

    # 4. Git/VsCode folders are ignored
    target_ignored = tmp_path / "ignored_test"
    target_ignored.mkdir()
    (target_ignored / ".git").mkdir()
    (target_ignored / ".vscode").mkdir()
    valid, msg = validate_new_project_target(target_ignored)
    assert valid, f"Directory with only .git/.vscode should be valid: {msg}"

def test_create_project(tmp_path: Path) -> None:
    target = tmp_path / "my_game"
    create_project(target, "My Game")

    # Check directory structure
    assert (target / "config.json").exists()
    assert (target / "packs/core_regions/scenes/start.json").exists()
    assert (target / "packs/core_regions/worlds/main.json").exists()
    assert (target / "assets/images").exists()
    assert (target / "artifacts").exists()

    # Check config content
    config = json.loads((target / "config.json").read_text(encoding="utf-8"))
    assert config["project_name"] == "My Game"
    assert config["start_scene"] == "packs/core_regions/scenes/start.json"

    # Check scene content
    scene = json.loads((target / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
    assert scene["scene_id"] == "start"

    # Check world content
    world = json.loads((target / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
    assert world["id"] == "main"
