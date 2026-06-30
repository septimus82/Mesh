"""Scaffolded project world format and Start Game isolation tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import json_io
from engine.game_runtime.scene_flow import resolve_game_start_scene
from engine.paths import reset_path_caches, set_content_roots
from engine.project_scaffold import create_project
from engine.ui_overlays.main_menu_overlay import MainMenuOverlay
from engine.world_controller import WorldController


def _mesh_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.mark.fast
def test_scaffolded_world_uses_dict_scenes_with_start_tag(tmp_path: Path) -> None:
    root = tmp_path / "fresh_game"
    create_project(root, "Fresh Game", template_id="blank")

    world = json.loads((root / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
    assert isinstance(world["scenes"], dict)
    assert world["start_scene"] == "start"
    assert world["scenes"]["start"]["path"] == "packs/core_regions/scenes/start.json"
    assert world["scenes"]["start"]["tags"] == ["start"]

    controller = WorldController(world)
    assert controller.get_start_scene_key() == "start"
    assert controller.get_scene_path("start") == "packs/core_regions/scenes/start.json"


@pytest.mark.fast
def test_broken_world_start_game_uses_config_not_engine_showcase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "fresh_game"
    create_project(root, "Fresh Game", template_id="blank")

    broken_world = {
        "id": "main",
        "start_scene": "start",
        "scenes": [],
    }
    json_io.write_json_atomic(root / "packs/core_regions/worlds/main.json", broken_world)

    mesh_repo = _mesh_repo_root()
    engine_world = json.loads((mesh_repo / "worlds/main_world.json").read_text(encoding="utf-8"))
    stale_engine_world = WorldController(engine_world)

    monkeypatch.chdir(root)
    reset_path_caches()
    set_content_roots([root.resolve()])

    project_config = SimpleNamespace(
        start_scene="packs/core_regions/scenes/start.json",
    )
    resolved = resolve_game_start_scene(
        engine_config=project_config,
        world_controller=stale_engine_world,
    )
    assert resolved == "packs/core_regions/scenes/start.json"
    assert resolved != "scenes/showcase_hub.json"


@pytest.mark.fast
def test_main_menu_start_game_stays_on_project_start_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "fresh_game"
    create_project(root, "Fresh Game", template_id="blank")

    mesh_repo = _mesh_repo_root()
    engine_world = json.loads((mesh_repo / "worlds/main_world.json").read_text(encoding="utf-8"))

    monkeypatch.chdir(root)
    reset_path_caches()
    set_content_roots([root.resolve()])

    window = SimpleNamespace()
    window.engine_config = SimpleNamespace(
        start_scene="packs/core_regions/scenes/start.json",
    )
    window.world_controller = WorldController(engine_world)
    requested: list[str] = []
    window.request_scene_change = lambda scene_path: requested.append(str(scene_path))
    window.game_state_controller = SimpleNamespace(state=SimpleNamespace(flags={}))

    overlay = MainMenuOverlay.__new__(MainMenuOverlay)
    overlay.window = window
    MainMenuOverlay._handle_start_game_impl(overlay)

    assert requested == ["packs/core_regions/scenes/start.json"]
    assert "scenes/showcase_hub.json" not in requested[0]
