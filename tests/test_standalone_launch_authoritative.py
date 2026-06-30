"""Standalone launch must not be hijacked by projects.json last_root."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.config import load_config
from engine.game_runtime.scene_flow import resolve_game_start_scene
from engine.paths import get_content_roots, pin_config, reset_path_caches
from engine.project_scaffold import create_project
from engine.repo_root import (
    clear_launched_project_root,
    get_launched_project_root,
    pin_launched_project_root,
)
from engine.ui_overlays.main_menu_overlay import MainMenuOverlay
from engine.world_controller import WorldController
from tests._typing import as_any


@pytest.fixture(autouse=True)
def _reset_launched_project_root() -> None:
    clear_launched_project_root()
    yield
    clear_launched_project_root()


def _mesh_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.mark.fast
def test_standalone_pin_uses_launched_root_not_last_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_p = tmp_path / "project_p"
    project_q = tmp_path / "project_q"
    create_project(project_p, "Project P", template_id="blank")
    create_project(project_q, "Project Q", template_id="blank")

    mesh_repo = _mesh_repo_root()
    projects_path = mesh_repo / "projects.json"
    projects_path.write_text(
        json.dumps(
            {
                "version": 1,
                "last_root": str(project_q.resolve()),
                "recent_roots": [str(project_q.resolve())],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(project_p)
    monkeypatch.setenv("MESH_PROJECTS_PATH", str(projects_path))
    clear_launched_project_root()
    reset_path_caches()

    cfg = load_config(str(project_p / "config.json"))
    pin_launched_project_root(project_p, config=cfg)
    pin_config(cfg)

    assert get_launched_project_root() == project_p.resolve()
    assert os.environ.get("MESH_REPO_ROOT") == str(project_p.resolve())
    assert get_content_roots()[0].resolve() == project_p.resolve()

    resolved = resolve_game_start_scene(engine_config=cfg, world_controller=None)
    assert resolved == "packs/core_regions/scenes/start.json"
    assert "showcase_hub" not in (resolved or "")


@pytest.mark.fast
def test_apply_project_root_blocked_when_standalone_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_p = tmp_path / "project_p"
    project_q = tmp_path / "project_q"
    create_project(project_p, "Project P", template_id="blank")
    create_project(project_q, "Project Q", template_id="blank")

    monkeypatch.chdir(project_p)
    clear_launched_project_root()
    reset_path_caches()

    cfg = load_config(str(project_p / "config.json"))
    pin_launched_project_root(project_p, config=cfg)

    window = SimpleNamespace(
        engine_config=cfg,
        editor_controller=SimpleNamespace(active=False),
        world_controller=None,
        paused=False,
    )
    overlay = MainMenuOverlay(as_any(window))

    with patch.object(overlay, "_reload_project_config") as reload_mock:
        overlay._apply_project_root(str(project_q))

    reload_mock.assert_not_called()
    assert get_launched_project_root() == project_p.resolve()
    assert os.environ.get("MESH_REPO_ROOT") == str(project_p.resolve())


@pytest.mark.fast
def test_standalone_open_skips_project_browser_when_editor_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_p = tmp_path / "project_p"
    create_project(project_p, "Project P", template_id="blank")

    monkeypatch.chdir(project_p)
    clear_launched_project_root()
    reset_path_caches()

    cfg = load_config(str(project_p / "config.json"))
    pin_launched_project_root(project_p, config=cfg)

    window = SimpleNamespace(
        width=1280,
        height=720,
        paused=False,
        editor_controller=SimpleNamespace(active=False),
    )
    overlay = MainMenuOverlay(as_any(window))
    overlay.open()

    assert overlay.state == "main"
    assert overlay.visible is True


@pytest.mark.fast
def test_standalone_start_game_ignores_engine_world_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_p = tmp_path / "project_p"
    create_project(project_p, "Project P", template_id="blank")

    mesh_repo = _mesh_repo_root()
    engine_world = json.loads((mesh_repo / "worlds/main_world.json").read_text(encoding="utf-8"))
    stale_engine_world = WorldController(engine_world)

    monkeypatch.chdir(project_p)
    clear_launched_project_root()
    reset_path_caches()

    cfg = load_config(str(project_p / "config.json"))
    pin_launched_project_root(project_p, config=cfg)
    pin_config(cfg)

    window = SimpleNamespace(
        engine_config=cfg,
        world_controller=stale_engine_world,
        editor_controller=SimpleNamespace(active=False),
        paused=False,
        game_state_controller=SimpleNamespace(state=SimpleNamespace(flags={})),
    )
    requested: list[str] = []
    window.request_scene_change = lambda scene_path: requested.append(str(scene_path))

    overlay = MainMenuOverlay(as_any(window))
    MainMenuOverlay._handle_start_game_impl(overlay)

    assert requested == ["packs/core_regions/scenes/start.json"]
    assert "showcase_hub" not in requested[0]
