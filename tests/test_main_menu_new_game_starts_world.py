from __future__ import annotations

import types
from pathlib import Path

import arcade

from engine.ui import MainMenuOverlay


class _World:
    def get_start_scene_key(self) -> str:
        return "door_field"

    def get_scene_path(self, key: str) -> str | None:
        if key == "door_field":
            return "scenes/door_field.json"
        return None


class _Window:
    def __init__(self) -> None:
        self.width = 800
        self.height = 600
        self.paused = False
        self.scene_changes: list[str] = []
        self.world_controller = _World()
        self.engine_config = types.SimpleNamespace(start_scene="scenes/should_not_use.json")
        self.game_state_controller = types.SimpleNamespace(state=types.SimpleNamespace(flags={"demo.reached_cellar": True}))

    def request_scene_change(self, scene_path: str) -> None:
        self.scene_changes.append(str(scene_path))


def test_main_menu_new_game_starts_world_and_clears_flags(tmp_path: Path, monkeypatch) -> None:
    save_path = tmp_path / "missing_savegame.json"
    monkeypatch.setenv("MESH_SAVEGAME_PATH", str(save_path))
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))

    window = _Window()
    menu = MainMenuOverlay(window)  # type: ignore[arg-type]
    menu.open()
    # Skip project browser and go directly to main menu state
    # to avoid _reload_project_config overwriting our mocked world_controller
    menu.state = "main"
    menu._selection_index = 0

    # New Game is first when Continue is unavailable.
    menu.on_key_press(arcade.key.ENTER, 0)

    assert window.scene_changes == ["scenes/door_field.json"]
    assert window.game_state_controller.state.flags == {}
    assert menu.visible is False
    assert window.paused is False
