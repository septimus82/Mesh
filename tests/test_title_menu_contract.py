from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from tests._typing import as_any


def _patch_arcade(monkeypatch):
    import engine.optional_arcade as optional_arcade
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)


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
        self.engine_config = SimpleNamespace(start_scene="scenes/should_not_use.json")
        self.game_state_controller = SimpleNamespace(state=SimpleNamespace(flags={"demo.flag": True}))
        self.input_controller = None

    def request_scene_change(self, scene_path: str) -> None:
        self.scene_changes.append(str(scene_path))


def test_title_menu_continue_visibility(tmp_path: Path, monkeypatch) -> None:
    _patch_arcade(monkeypatch)
    from engine.savegame import SaveGameV1, save_savegame
    from engine.ui import MainMenuOverlay

    save_path = tmp_path / "save_1.json"
    monkeypatch.setenv("MESH_SAVEGAME_PATH", str(save_path))
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))

    window = _Window()
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    if getattr(menu, "state", "") == "project_browser":
        menu._activate_project_selection()
    assert menu.get_lines()[0] == "TITLE SCREEN"
    assert menu.get_lines()[-1] == "Enter Select  Esc Back  Up/Down Navigate"
    assert all("Continue" not in line for line in menu.get_lines())

    save = SaveGameV1(scene_path="scenes/door_field.json", player_x=1.0, player_y=2.0, flags={})
    save_savegame(save_path, save)

    menu2 = MainMenuOverlay(as_any(window))
    menu2.open()
    if getattr(menu2, "state", "") == "project_browser":
        menu2._activate_project_selection()
    assert menu2.get_lines()[0] == "TITLE SCREEN"
    assert any(line.strip().endswith("Continue") for line in menu2.get_lines())


def test_title_menu_selection_clamps_and_start_game(tmp_path: Path, monkeypatch) -> None:
    _patch_arcade(monkeypatch)
    from engine.ui import MainMenuOverlay
    import engine.optional_arcade as optional_arcade

    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))
    window = _Window()
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    # Skip project browser to avoid _reload_project_config overwriting world_controller
    menu.state = "main"
    menu._selection_index = 0
    window.input_controller = SimpleNamespace(manager=SimpleNamespace(input_source="gamepad"))
    assert menu.get_lines()[-1] == "A Select  B Back  D-pad Navigate"

    menu.on_key_press(optional_arcade.arcade.key.UP, 0)
    assert menu._selection_index == 0

    last_index = len(menu._items()) - 1
    menu._selection_index = last_index
    menu.on_key_press(optional_arcade.arcade.key.DOWN, 0)
    assert menu._selection_index == last_index

    menu._selection_index = 0
    menu.on_key_press(optional_arcade.arcade.key.ENTER, 0)
    assert window.scene_changes == ["scenes/door_field.json"]
    assert window.game_state_controller.state.flags == {}
    assert menu.visible is False
