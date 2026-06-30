"""Paintable collision tilemap and standalone editor entry."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engine.assets import AssetManager
from engine.game_launch import launch_editor, resolve_project_root
from engine.paths import get_content_roots, reset_path_caches
from engine.project_scaffold import create_project
from engine.repo_root import clear_launched_project_root, get_launched_project_root
from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision
from engine.scene_controller_parts.tilemap_state import set_tile
from engine.scene_runtime.scene_load_apply import load_tilemap_layers
from engine.tilemap import TilemapManager

pytestmark = pytest.mark.fast

_REPO = Path(__file__).resolve().parents[1]
_TILE_W = 32
_TILE_H = 32
_GRID_W = 6
_GRID_H = 4


def _write_mini_passability_map(tilemap_dir: Path) -> Path:
    tilemap_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(_REPO / "assets" / "tilemaps" / "basic_tiles.png", tilemap_dir / "blocked_tile.png")
    count = _GRID_W * _GRID_H
    map_path = tilemap_dir / "passability.json"
    map_path.write_text(
        json.dumps(
            {
                "type": "map",
                "orientation": "orthogonal",
                "width": _GRID_W,
                "height": _GRID_H,
                "tilewidth": _TILE_W,
                "tileheight": _TILE_H,
                "tilesets": [
                    {
                        "firstgid": 1,
                        "name": "blocked",
                        "tilewidth": _TILE_W,
                        "tileheight": _TILE_H,
                        "tilecount": 1,
                        "columns": 1,
                        "image": "blocked_tile.png",
                        "imagewidth": 128,
                        "imageheight": 32,
                    }
                ],
                "layers": [
                    {
                        "name": "blocked",
                        "type": "tilelayer",
                        "width": _GRID_W,
                        "height": _GRID_H,
                        "data": [0] * count,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return map_path


def _scene_with_painted_wall(*, painted_index: int) -> dict[str, Any]:
    tiles = [0] * (_GRID_W * _GRID_H)
    if painted_index >= 0:
        tiles[painted_index] = 1
    return {
        "entities": [],
        "tilemap": {
            "path": "assets/tilemaps/passability.json",
            "collision_layer_id": "blocked",
            "width": _GRID_W,
            "height": _GRID_H,
            "tilewidth": _TILE_W,
            "tileheight": _TILE_H,
            "tile_layers": [
                {
                    "id": "blocked",
                    "draw": False,
                    "collision": True,
                    "z": -200,
                    "tiles": tiles,
                }
            ],
        },
    }


def _load_instance(tmp_path: Path, scene: dict[str, Any]):
    tilemap_dir = tmp_path / "assets" / "tilemaps"
    _write_mini_passability_map(tilemap_dir)
    scene_path = tmp_path / "scenes" / "test.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text(json.dumps(scene), encoding="utf-8")

    manager = TilemapManager(AssetManager())
    controller = SimpleNamespace(
        window=SimpleNamespace(tilemap_manager=manager),
        tilemap_instance=None,
        navigation=SimpleNamespace(invalidate=MagicMock()),
        solid_sprites=[],
        _tilemap_background_layers=[],
        _tilemap_foreground_layers=[],
        _tilemap_draw_layers=[],
        _init_tilemap_batching=lambda _instance: None,
        _apply_tilemap_world_bounds=lambda _instance: None,
    )
    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        load_tilemap_layers(
            controller,
            scene,
            scene_path.parent,
            load_tilemap_func=manager.load_map,
        )
    finally:
        os.chdir(previous)
    return controller


@pytest.fixture(autouse=True)
def _reset_launched_root() -> None:
    clear_launched_project_root()
    yield
    clear_launched_project_root()


def test_empty_collision_layer_registered_for_editor_paint(tmp_path: Path) -> None:
    scene = _scene_with_painted_wall(painted_index=-1)
    controller = _load_instance(tmp_path, scene)
    instance = controller.tilemap_instance
    assert instance is not None
    assert "blocked" in instance.layer_data
    assert "blocked" in instance.layer_lookup
    assert instance.collision_layer_names == frozenset({"blocked"})
    assert len(instance.collision_sprites) == 0
    assert len(instance.draw_layers) == 0


def test_collision_tilemap_loads_collision_sprites_from_painted_tiles(tmp_path: Path) -> None:
    painted_index = 1 * _GRID_W + 2
    controller = _load_instance(tmp_path, _scene_with_painted_wall(painted_index=painted_index))
    instance = controller.tilemap_instance
    assert instance is not None
    assert len(instance.collision_sprites) == 1
    assert len(controller.solid_sprites) == 1
    assert len(instance.draw_layers) == 0


def test_move_entity_with_collision_stops_at_painted_tile(tmp_path: Path) -> None:
    import engine.optional_arcade as optional_arcade

    painted_index = 1 * _GRID_W + 2
    controller = _load_instance(tmp_path, _scene_with_painted_wall(painted_index=painted_index))
    assert controller.tilemap_instance is not None
    solid_sprites = controller.tilemap_instance.collision_sprites
    blocked = solid_sprites[0]

    player = optional_arcade.arcade.SpriteSolidColor(_TILE_W - 4, _TILE_H - 4, color=(0, 255, 0, 255))
    player.center_x = blocked.left - (player.width / 2.0) + 4.0
    player.center_y = blocked.center_y

    bind = type("SC", (), {"solid_sprites": solid_sprites, "window": controller.window})()
    bind.move_entity_with_collision = move_entity_with_collision.__get__(bind, type(bind))

    bind.move_entity_with_collision(player, _TILE_W, 0.0)
    assert player.right <= blocked.left + 0.5

    player.center_x = blocked.right + (player.width / 2.0) + 2.0
    before = player.center_x
    bind.move_entity_with_collision(player, -_TILE_W, 0.0)
    assert player.center_x < before
    assert player.left >= blocked.right - 0.5


def test_set_tile_updates_collision_sprites_on_collision_layer(tmp_path: Path) -> None:
    scene = _scene_with_painted_wall(painted_index=-1)
    controller = _load_instance(tmp_path, scene)
    bind = type(
        "SC",
        (),
        {
            "tilemap_instance": controller.tilemap_instance,
            "solid_sprites": controller.solid_sprites,
            "window": controller.window,
            "_mark_tilemap_tile_dirty": lambda *_a, **_k: None,
        },
    )()
    bind.set_tile = set_tile.__get__(bind, type(bind))
    assert bind.set_tile("blocked", 2, 1, 1) == (0, 1)
    assert len(bind.tilemap_instance.collision_sprites) == 1
    assert len(bind.solid_sprites) == 1
    assert bind.set_tile("blocked", 2, 1, 0) == (1, 0)
    assert len(bind.tilemap_instance.collision_sprites) == 0
    assert len(bind.solid_sprites) == 0


def test_launch_editor_pins_project_without_using_last_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "standalone_game"
    create_project(project, "Standalone", template_id="blank")
    other = tmp_path / "other_game"
    create_project(other, "Other", template_id="blank")

    projects_path = tmp_path / "projects.json"
    projects_path.write_text(
        json.dumps(
            {
                "version": 1,
                "last_root": str(other.resolve()),
                "recent_roots": [str(other.resolve())],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MESH_PROJECTS_PATH", str(projects_path))
    reset_path_caches()

    run_called = {"value": False}

    def _fake_run(self: Any) -> None:
        run_called["value"] = True

    def _fake_load_scene(self: Any, scene_id: str) -> dict[str, Any]:
        return {"tilemap": {"collision_layer_id": "blocked", "tile_layers": [{"id": "blocked"}]}}

    with (
        patch("engine.game_launch.GameWindow.run", _fake_run),
        patch("engine.game_launch.GameWindow.load_scene", _fake_load_scene),
    ):
        rc = launch_editor(project_root=project, open_tile_paint=False)
    assert rc == 0
    assert run_called["value"] is True
    assert get_launched_project_root() == project.resolve()
    assert get_content_roots()[0].resolve() == project.resolve()


def test_resolve_project_root_accepts_directory_or_config_parent() -> None:
    assert resolve_project_root(None) == Path.cwd().resolve()
    cfg = _REPO / "config.json"
    if cfg.is_file():
        assert resolve_project_root(cfg) == _REPO.resolve()
