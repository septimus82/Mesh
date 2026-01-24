from __future__ import annotations

import json
from pathlib import Path


def _filtered_entity_ids(scene_payload: dict, *, get_flag) -> list[str]:
    from engine.scene_entity_gating import filter_entities_by_flags

    entities = scene_payload.get("entities") or []
    filtered = filter_entities_by_flags(entities, get_flag=get_flag)
    return [str(e.get("id") or "") for e in filtered if isinstance(e, dict)]


def test_micro_dungeon_key_disappears_after_taken_and_persists_on_load(monkeypatch) -> None:
    from engine.savegame import SaveGameV1, apply_savegame_to_window

    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    side_payload = json.loads((repo_root / "scenes" / "side_room_01.json").read_text(encoding="utf-8"))
    assert isinstance(side_payload, dict)

    class _State:
        flags: dict[str, bool] = {}

    class _GS:
        state = _State()

    class _Window:
        game_state_controller = _GS()

        def request_scene_change(self, _scene_path: str) -> None:
            return

        def get_flag(self, name: str, default: bool = False) -> bool:
            return bool(self.game_state_controller.state.flags.get(name, default))

    window = _Window()

    assert "side_room_01_sidekey_240_232_0_0" in _filtered_entity_ids(side_payload, get_flag=window.get_flag)

    save = SaveGameV1(
        scene_path="scenes/side_room_01.json",
        player_x=0.0,
        player_y=0.0,
        flags={"demo.side_key_taken": True},
    )
    apply_savegame_to_window(window, save)

    assert "side_room_01_sidekey_240_232_0_0" not in _filtered_entity_ids(side_payload, get_flag=window.get_flag)


def test_micro_dungeon_chest_hidden_until_key_and_reward_visible_after_claim(monkeypatch) -> None:
    from engine.savegame import SaveGameV1, apply_savegame_to_window

    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    reward_payload = json.loads((repo_root / "scenes" / "reward_nook_01.json").read_text(encoding="utf-8"))
    assert isinstance(reward_payload, dict)

    class _HUD:
        def __init__(self) -> None:
            self.toasts: list[str] = []

        def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
            self.toasts.append(str(message))

    class _State:
        flags: dict[str, bool] = {}

    class _GS:
        state = _State()

    class _Window:
        game_state_controller = _GS()
        player_hud = _HUD()

        def request_scene_change(self, _scene_path: str) -> None:
            return

        def get_flag(self, name: str, default: bool = False) -> bool:
            return bool(self.game_state_controller.state.flags.get(name, default))

    window = _Window()

    ids = _filtered_entity_ids(reward_payload, get_flag=window.get_flag)
    assert "reward_nook_01_rewardchest_240_232_0_0" not in ids
    assert "reward_nook_01_reward_272_232_0_0" not in ids

    apply_savegame_to_window(
        window,
        SaveGameV1(
            scene_path="scenes/reward_nook_01.json",
            player_x=0.0,
            player_y=0.0,
            flags={"demo.side_key_taken": True},
        ),
    )
    ids = _filtered_entity_ids(reward_payload, get_flag=window.get_flag)
    assert "reward_nook_01_rewardchest_240_232_0_0" in ids
    assert "reward_nook_01_reward_272_232_0_0" not in ids
    assert window.player_hud.toasts == []

    apply_savegame_to_window(
        window,
        SaveGameV1(
            scene_path="scenes/reward_nook_01.json",
            player_x=0.0,
            player_y=0.0,
            flags={"demo.side_key_taken": True, "demo.reward_claimed": True},
        ),
    )
    ids = _filtered_entity_ids(reward_payload, get_flag=window.get_flag)
    assert "reward_nook_01_rewardchest_240_232_0_0" in ids
    assert "reward_nook_01_reward_272_232_0_0" in ids
    assert window.player_hud.toasts == []

