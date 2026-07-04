"""Blank-project monster boot contract tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.behaviours import load_builtin_behaviours
from engine.game import GameWindow
from engine.monster.data_load import load_monster_catalog
from engine.paths import reset_path_caches, resolve_monster_data_dir
from engine.project_scaffold import create_project
from engine.scene_loader import SceneLoader
from engine.schema_validation import validate
from tests._typing import as_any


@pytest.mark.fast
def test_blank_project_scaffold_is_schema_valid(tmp_path: Path) -> None:
    root = tmp_path / "monster_game"
    create_project(root, "Monster Game", template_id="blank")

    config = __import__("json").loads((root / "config.json").read_text(encoding="utf-8"))
    validate(config, "config.schema.json", root / "config.json")

    scene_path = root / "packs/core_regions/scenes/start.json"
    scene = __import__("json").loads(scene_path.read_text(encoding="utf-8"))
    validate(scene, "scene.schema.json", scene_path)

    assert (root / "main.py").is_file()
    assert (root / "assets/data/monster_species.json").is_file()
    assert (root / "assets/sprites/sproutling.png").is_file()
    assert (root / "assets/sprites/shelltide.png").is_file()


@pytest.mark.fast
def test_blank_project_loads_scene_and_monster_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "monster_game"
    create_project(root, "Monster Game", template_id="blank")

    monkeypatch.chdir(root)
    reset_path_caches()
    load_builtin_behaviours(force=True)

    scene = SceneLoader().load_scene("packs/core_regions/scenes/start.json")
    players = [entity for entity in scene["entities"] if entity.get("tag") == "player"]
    assert len(players) == 1

    catalog, validation = load_monster_catalog(resolve_monster_data_dir())
    assert validation.ok, validation.errors
    assert catalog is not None
    assert "sproutling" in catalog.species
    assert "shelltide" in catalog.species


@pytest.mark.fast
def test_blank_project_f8_companion_battle_starts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "monster_game"
    create_project(root, "Monster Game", template_id="blank")

    monkeypatch.chdir(root)
    reset_path_caches()

    window = SimpleNamespace()
    window.console_log = MagicMock()
    window.monster_battle_mode = SimpleNamespace(active=False)
    window.game_state_controller = __import__(
        "engine.game_state_controller", fromlist=["GameStateController"]
    ).GameStateController(window)
    window.scene_controller = SimpleNamespace(current_scene_path="packs/core_regions/scenes/start.json")
    captured: dict[str, object] = {}

    def _capture_start_monster_battle(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    window.start_monster_battle = _capture_start_monster_battle

    GameWindow.start_debug_companion_monster_battle(as_any(window))

    assert captured.get("companion_mode") is True
    assert captured.get("companion_mind") is not None
    player = captured.get("player_monster")
    assert player is not None
    assert player.species.id == "sproutling"
    opponent = captured.get("opponent_monster")
    assert opponent is not None
    assert opponent.species.id == "shelltide"


@pytest.mark.fast
def test_resolve_monster_data_dir_falls_back_to_engine_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "bare_project"
    root.mkdir()
    (root / "config.json").write_text(
        __import__("json").dumps(
            {
                "content_roots": ["."],
                "width": 800,
                "height": 600,
                "title": "Bare",
                "start_scene": "packs/core_regions/scenes/start.json",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(root)
    reset_path_caches()

    data_dir = resolve_monster_data_dir()
    catalog, validation = load_monster_catalog(data_dir)
    assert validation.ok, validation.errors
    assert catalog is not None
    assert "sproutling" in catalog.species
