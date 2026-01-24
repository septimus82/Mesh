from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


class _StubQuestManager:
    def __init__(self) -> None:
        self.loaded: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": 1, "quests": {"q1": {"id": "q1", "state": "active"}}}

    def load_from_dict(self, data: dict[str, object]) -> None:
        self.loaded = dict(data)


class _StubPlayer:
    def __init__(self) -> None:
        self.center_x = 0.0
        self.center_y = 0.0
        self.mesh_entity_data = {"id": "player", "x": 0.0, "y": 0.0}


def _make_window(player: _StubPlayer, quest_manager: _StubQuestManager):
    scene_controller = SimpleNamespace(
        current_scene_path="scenes/test.json",
        _find_player_sprite=lambda: player,
    )

    def _request_scene_change(path: str) -> None:
        scene_controller.current_scene_path = path

    return SimpleNamespace(
        scene_controller=scene_controller,
        player_sprite=player,
        game_state_controller=SimpleNamespace(quests=quest_manager, state=SimpleNamespace(flags={})),
        request_scene_change=_request_scene_change,
    )


def test_savegame_roundtrip_and_apply(tmp_path: Path) -> None:
    from engine import savegame

    player = _StubPlayer()
    quest_manager = _StubQuestManager()
    window = _make_window(player, quest_manager)

    payload = savegame.build_savegame(window)
    assert isinstance(payload, dict)
    save_path = tmp_path / "save_1.json"
    savegame.save_savegame(save_path, savegame.SaveGameV1.from_payload(payload))

    loaded = savegame.load_savegame(save_path)
    assert loaded is not None
    assert loaded.scene_path == "scenes/test.json"
    assert loaded.quests == payload["quests"]

    updated = dict(payload)
    updated["player"] = {"x": 12.5, "y": 99.5}
    updated["quests"] = {"schema_version": 1, "quests": {"q2": {"id": "q2", "state": "completed"}}}

    assert savegame.apply_savegame(window, updated) is True
    assert player.center_x == 12.5
    assert player.center_y == 99.5
    assert player.mesh_entity_data["x"] == 12.5
    assert player.mesh_entity_data["y"] == 99.5
    assert quest_manager.loaded == updated["quests"]


def test_savegame_version_mismatch_is_noop() -> None:
    from engine import savegame

    player = _StubPlayer()
    quest_manager = _StubQuestManager()
    window = _make_window(player, quest_manager)

    payload = {
        "version": 99,
        "scene_id": "scenes/test.json",
        "player": {"x": 5.0, "y": 6.0},
        "quests": {},
    }
    assert savegame.apply_savegame(window, payload) is False
    assert player.center_x == 0.0
    assert player.center_y == 0.0
    assert quest_manager.loaded is None


def test_savegame_missing_file_returns_none(tmp_path: Path) -> None:
    from engine import savegame

    missing = tmp_path / "missing.json"
    assert savegame.load_savegame(missing) is None
