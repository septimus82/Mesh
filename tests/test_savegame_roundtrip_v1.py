from __future__ import annotations

import json
from pathlib import Path


def test_savegame_v1_roundtrip_and_apply(tmp_path: Path) -> None:
    from engine.savegame import SaveGameV1, apply_savegame_to_window, load_savegame, save_savegame

    save_path = tmp_path / "savegame.json"

    save = SaveGameV1(
        scene_path="scenes/door_field.json",
        player_x=12.5,
        player_y=99.25,
        flags={"demo.objective_started": True, "demo.reached_cellar": False},
    )

    save_savegame(save_path, save)
    loaded = load_savegame(save_path)
    assert loaded == save

    class _State:
        flags: dict[str, bool] = {}

    class _GS:
        state = _State()

    class _Player:
        def __init__(self) -> None:
            self.center_x = 0.0
            self.center_y = 0.0
            self.mesh_entity_data = {"id": "player", "x": 0.0, "y": 0.0}

    player = _Player()

    class _Scene:
        current_scene_path = "scenes/door_field.json"

        def _find_player_sprite(self):
            return player

    requested: list[str] = []

    class _Window:
        game_state_controller = _GS()
        scene_controller = _Scene()

        def request_scene_change(self, scene_path: str) -> None:
            requested.append(str(scene_path))

    window = _Window()
    apply_savegame_to_window(window, loaded)

    assert window.game_state_controller.state.flags == save.flags
    assert requested == ["scenes/door_field.json"]
    assert player.center_x == 12.5
    assert player.center_y == 99.25
    assert player.mesh_entity_data["x"] == 12.5
    assert player.mesh_entity_data["y"] == 99.25


def test_savegame_v1_payload_schema_is_stable(tmp_path: Path) -> None:
    from engine.savegame import SaveGameV1, save_savegame

    save_path = tmp_path / "savegame.json"
    save = SaveGameV1(scene_path="scenes/x.json", player_x=1.0, player_y=2.0, flags={"b": False, "a": True})
    save_savegame(save_path, save)

    data = json.loads(save_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["scene_path"] == "scenes/x.json"
    assert data["player_x"] == 1.0
    assert data["player_y"] == 2.0
    assert list(data["flags"].keys()) == ["a", "b"]

