from __future__ import annotations

import types
from pathlib import Path

from engine.savegame import SaveGameV1, save_savegame
from engine.ui import MainMenuOverlay
from tests._typing import as_any


def test_main_menu_continue_visibility(tmp_path: Path, monkeypatch) -> None:
    save_path = tmp_path / "savegame.json"
    monkeypatch.setenv("MESH_SAVEGAME_PATH", str(save_path))
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))

    window = types.SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    if getattr(menu, "state", "") == "project_browser":
        menu._activate_project_selection()
    assert all("Continue" not in line for line in menu.get_lines())

    save = SaveGameV1(scene_path="scenes/door_field.json", player_x=1.0, player_y=2.0, flags={})
    save_savegame(save_path, save)

    menu2 = MainMenuOverlay(as_any(window))
    menu2.open()
    if getattr(menu2, "state", "") == "project_browser":
        menu2._activate_project_selection()
    assert any(line.strip() == "> Continue" or line.strip() == "Continue" for line in menu2.get_lines())
