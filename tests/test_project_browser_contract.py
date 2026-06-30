from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.projects import add_recent_project, get_recent_projects
from engine.repo_root import clear_launched_project_root
from tests._typing import as_any


@pytest.fixture(autouse=True)
def _reset_launched_project_root() -> None:
    clear_launched_project_root()
    yield
    clear_launched_project_root()


def _patch_arcade(monkeypatch) -> None:
    import engine.optional_arcade as optional_arcade
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)


def test_recent_project_list_order_stable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("MESH_PROJECTS_PATH", str(tmp_path / "projects.json"))

    proj_a = tmp_path / "proj_a"
    proj_b = tmp_path / "proj_b"
    proj_a.mkdir()
    proj_b.mkdir()

    add_recent_project(str(proj_a))
    add_recent_project(str(proj_b))
    add_recent_project(str(proj_a))

    assert get_recent_projects() == [str(proj_a.resolve()), str(proj_b.resolve())]


def test_project_selection_sets_repo_root_for_scene_index(tmp_path: Path, monkeypatch) -> None:
    _patch_arcade(monkeypatch)
    from engine.scene_index import list_pack_scene_listings
    from engine.ui import MainMenuOverlay

    project_root = tmp_path / "project"
    scene_path = project_root / "packs" / "core" / "scenes" / "alpha.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text('{"name": "Alpha Scene"}', encoding="utf-8")
    (project_root / "config.json").write_text("{}", encoding="utf-8")

    other_root = tmp_path / "other"
    other_root.mkdir()

    monkeypatch.setenv("MESH_REPO_ROOT", str(other_root))
    monkeypatch.setenv("MESH_PROJECTS_PATH", str(tmp_path / "projects.json"))
    add_recent_project(str(project_root))

    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    assert menu.state == "project_browser"

    menu._project_index = 0
    menu._activate_project_selection()

    assert os.environ.get("MESH_REPO_ROOT") == str(project_root)
    listings = list_pack_scene_listings()
    assert any(entry.path.endswith("packs/core/scenes/alpha.json") for entry in listings)


def test_project_browser_skips_on_web(monkeypatch) -> None:
    _patch_arcade(monkeypatch)
    from engine.ui import MainMenuOverlay

    monkeypatch.setenv("PYGBAG", "1")
    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    assert menu.state == "main"
    assert menu.get_lines()[0] == "TITLE SCREEN"


def test_project_browser_create_flow(tmp_path: Path, monkeypatch) -> None:
    _patch_arcade(monkeypatch)
    # Ensure is_web_runtime is False
    monkeypatch.setenv("PYGBAG", "0")

    import engine.optional_arcade as optional_arcade
    from engine.ui import MainMenuOverlay

    window = SimpleNamespace(width=800, height=600, paused=False)

    menu = MainMenuOverlay(as_any(window))
    menu.open()
    assert menu.state == "project_browser"

    # Mock _project_items
    mock_items = [{"root": "", "label": "Create New Project...", "kind": "create"}]
    with patch.object(menu, "_project_items", return_value=mock_items):
        menu._project_index = 0
        # Press Enter on "Create..."
        menu.on_key_press(optional_arcade.arcade.key.ENTER)

        # Now must be in template state
        assert menu.state == "create_project_template"

        # Press Enter to select default "blank" template
        menu.on_key_press(optional_arcade.arcade.key.ENTER)
        assert menu._create_template_id == "blank"

        # Now in name state
        assert menu.state == "create_project_name"

        # Enter Name
        menu.on_text("MyGame")
        assert menu._create_name == "MyGame"

        # Press Enter
        with patch("pathlib.Path.cwd", return_value=tmp_path):
             menu.on_key_press(optional_arcade.arcade.key.ENTER)

        assert menu.state == "create_project_path"
        expected_path = str((tmp_path / "mygame").resolve())
        assert menu._create_path == expected_path

        # Press Enter to create
        with patch("engine.project_scaffold.create_project") as mock_create:
            with patch("engine.project_scaffold.validate_new_project_target", return_value=(True, "")) as mock_valid:
                with patch.object(menu, "_apply_project_root") as mock_apply:
                    with patch.object(menu, "_handle_start_game_impl") as mock_start:
                        menu.on_key_press(optional_arcade.arcade.key.ENTER)

                        mock_valid.assert_called_with(Path(expected_path))
                        mock_create.assert_called_once()
                        mock_apply.assert_called_with(expected_path)
                        mock_start.assert_called_once()
                        # State should still be create_project_path since close() isn't called
                        # when _handle_start_game_impl is mocked
                        assert menu.state in ("create_project_path", "main")

def test_project_browser_cancel_flow(monkeypatch) -> None:
    _patch_arcade(monkeypatch)
    import engine.optional_arcade as optional_arcade
    from engine.ui import MainMenuOverlay

    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    assert menu.state == "project_browser"

    mock_items = [{"root": "", "label": "Create New Project...", "kind": "create"}]
    with patch.object(menu, "_project_items", return_value=mock_items):
        menu._project_index = 0
        menu.on_key_press(optional_arcade.arcade.key.ENTER)
        assert menu.state == "create_project_template"

        # Escape from template -> browser
        menu.on_key_press(optional_arcade.arcade.key.ESCAPE)
        assert menu.state == "project_browser"

        # Enter again -> template
        menu.on_key_press(optional_arcade.arcade.key.ENTER)
        assert menu.state == "create_project_template"

        # Select template -> name
        menu.on_key_press(optional_arcade.arcade.key.ENTER)
        assert menu.state == "create_project_name"

        # Escape from name -> template
        menu.on_key_press(optional_arcade.arcade.key.ESCAPE)
        assert menu.state == "create_project_template"

        # Advance to name again
        menu.on_key_press(optional_arcade.arcade.key.ENTER)
        assert menu.state == "create_project_name"

        # Enter name and advance
        menu.on_text("A")
        menu.on_key_press(optional_arcade.arcade.key.ENTER)
        assert menu.state == "create_project_path"

        # Escape from path -> name
        menu.on_key_press(optional_arcade.arcade.key.ESCAPE)
        assert menu.state == "create_project_name"
        assert menu._create_name == "A"
