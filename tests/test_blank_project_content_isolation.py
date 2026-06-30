"""Blank-project content isolation: no engine showcase bleed-through."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.behaviours import load_builtin_behaviours
from engine.config import load_config
from engine.paths import (
    get_content_roots,
    pin_config,
    reset_path_caches,
    resolve_path,
)
from engine.project_scaffold import create_project
from engine.scene_loader import SceneLoader


def _mesh_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.mark.fast
def test_blank_project_content_roots_follow_config_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "isolated_game"
    create_project(root, "Isolated Game", template_id="blank")

    mesh_repo = _mesh_repo_root()
    monkeypatch.chdir(mesh_repo)
    reset_path_caches()

    cfg = load_config(str(root / "config.json"))
    pin_config(cfg)

    roots = get_content_roots()
    assert len(roots) == 1
    assert roots[0].resolve() == root.resolve()

    start_path = resolve_path(cfg.start_scene)
    assert start_path.exists()
    assert root.resolve() in start_path.resolve().parents

    scene = json.loads(start_path.read_text(encoding="utf-8"))
    names = [entity.get("name") for entity in scene.get("entities", [])]
    assert names == ["Player"]
    assert "Showcase Guide" not in names


@pytest.mark.fast
def test_missing_project_scene_does_not_resolve_engine_showcase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "isolated_game"
    create_project(root, "Isolated Game", template_id="blank")

    mesh_repo = _mesh_repo_root()
    engine_showcase = mesh_repo / "scenes" / "showcase_hub.json"
    assert engine_showcase.is_file()

    monkeypatch.chdir(mesh_repo)
    reset_path_caches()

    cfg = load_config(str(root / "config.json"))
    pin_config(cfg)

    leaked = resolve_path("scenes/showcase_hub.json")
    assert leaked.resolve() != engine_showcase.resolve()
    assert not leaked.exists()

    with pytest.raises(FileNotFoundError, match="showcase_hub"):
        SceneLoader().load_scene("scenes/showcase_hub.json")


@pytest.mark.fast
def test_blank_project_boots_player_only_when_cwd_is_engine_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "isolated_game"
    create_project(root, "Isolated Game", template_id="blank")

    mesh_repo = _mesh_repo_root()
    monkeypatch.chdir(mesh_repo)
    reset_path_caches()

    cfg = load_config(str(root / "config.json"))
    pin_config(cfg)
    load_builtin_behaviours(force=True)

    scene = SceneLoader().load_scene(cfg.start_scene)
    names = [entity.get("name") for entity in scene.get("entities", [])]
    assert names == ["Player"]
