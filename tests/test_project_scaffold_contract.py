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
    assert config["title"] == "My Game"
    assert config["start_scene"] == "packs/core_regions/scenes/start.json"
    assert (target / "main.py").exists()
    assert (target / "assets/data/monster_species.json").exists()

    # Check scene content
    scene = json.loads((target / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
    assert scene["name"] == "Start Scene"

    # Check world content
    world = json.loads((target / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
    assert world["id"] == "main"
    assert isinstance(world["scenes"], dict)
    assert world["start_scene"] == "start"
    assert world["scenes"]["start"]["tags"] == ["start"]


def test_create_project_copies_default_battle_audio_assets(tmp_path: Path) -> None:
    from engine.monster.battle_audio import default_battle_audio_asset_paths

    target = tmp_path / "battle_audio_project"
    create_project(target, "Battle Audio Game")

    for rel_path in default_battle_audio_asset_paths():
        copied = target / rel_path
        assert copied.is_file(), f"missing scaffolded battle audio asset: {rel_path}"
        assert copied.stat().st_size > 0, f"empty scaffolded battle audio asset: {rel_path}"


def test_scaffold_battle_audio_paths_track_mapping_contract(tmp_path: Path) -> None:
    from engine.monster.battle_audio import (
        BATTLE_MUSIC_PATH,
        DEFAULT_BATTLE_SOUND_MAP,
        default_battle_audio_asset_paths,
    )

    expected = {spec.path for spec in DEFAULT_BATTLE_SOUND_MAP.values()}
    expected.add(BATTLE_MUSIC_PATH)
    assert set(default_battle_audio_asset_paths()) == expected

    target = tmp_path / "mapping_contract_project"
    create_project(target, "Mapping Contract")
    for rel_path in default_battle_audio_asset_paths():
        assert (target / rel_path).is_file()


def test_create_project_keeps_monster_starter_json_and_sprites(tmp_path: Path) -> None:
    target = tmp_path / "monster_starter_project"
    create_project(target, "Monster Starter")

    for rel_path in (
        "assets/data/monster_species.json",
        "assets/data/monster_moves.json",
        "assets/data/monster_type_chart.json",
        "assets/sprites/sproutling.png",
        "assets/sprites/shelltide.png",
        "assets/sprites/animated_player.png",
    ):
        assert (target / rel_path).is_file()
        assert (target / rel_path).stat().st_size > 0
