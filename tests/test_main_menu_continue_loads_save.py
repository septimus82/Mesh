from __future__ import annotations

import types
from pathlib import Path

import arcade

from engine.savegame import SaveGameV1, save_savegame
from engine.ui import MainMenuOverlay


class _Window:
    def __init__(self) -> None:
        self.width = 800
        self.height = 600
        self.paused = False
        self.scene_changes: list[str] = []
        self.game_state_controller = types.SimpleNamespace(state=types.SimpleNamespace(flags={"x": True}))

    def request_scene_change(self, scene_path: str) -> None:
        self.scene_changes.append(str(scene_path))


def test_main_menu_continue_loads_save(tmp_path: Path, monkeypatch) -> None:
    save_path = tmp_path / "savegame.json"
    monkeypatch.setenv("MESH_SAVEGAME_PATH", str(save_path))
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))

    save = SaveGameV1(
        scene_path="scenes/door_field.json",
        player_x=10.0,
        player_y=20.0,
        flags={"demo.objective_started": True},
    )
    save_savegame(save_path, save)

    window = _Window()
    menu = MainMenuOverlay(window)  # type: ignore[arg-type]
    menu.open()
    if getattr(menu, "state", "") == "project_browser":
        menu._activate_project_selection()
    assert menu.visible is True

    # Continue is first when present.
    menu.on_key_press(arcade.key.ENTER, 0)

    assert window.scene_changes == ["scenes/door_field.json"]
    assert window.paused is False
    assert menu.visible is False
    assert window.game_state_controller.state.flags.get("demo.objective_started") is True
