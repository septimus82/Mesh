from __future__ import annotations

import json
from pathlib import Path


def _filtered_entity_ids(scene_payload: dict, *, get_flag) -> list[str]:
    from engine.scene_entity_gating import filter_entities_by_flags

    entities = scene_payload.get("entities") or []
    filtered = filter_entities_by_flags(entities, get_flag=get_flag)
    return [str(e.get("id") or "") for e in filtered if isinstance(e, dict)]


def test_micro_dungeon_barrier_gates_by_side_key_used_and_does_not_toast_on_load(monkeypatch) -> None:
    from engine.savegame import SaveGameV1, apply_savegame_to_window

    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    side_payload = json.loads((repo_root / "scenes" / "side_room_01.json").read_text(encoding="utf-8"))
    assert isinstance(side_payload, dict)

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

    assert "side_room_01_barrier_184_184_0_0" in _filtered_entity_ids(side_payload, get_flag=window.get_flag)

    apply_savegame_to_window(
        window,
        SaveGameV1(
            scene_path="scenes/side_room_01.json",
            player_x=0.0,
            player_y=0.0,
            flags={"demo.side_key_taken": True, "demo.side_key_used": True},
        ),
    )
    assert window.player_hud.toasts == []
    assert "side_room_01_barrier_184_184_0_0" not in _filtered_entity_ids(side_payload, get_flag=window.get_flag)


def test_micro_dungeon_barrier_intercepts_interact_until_used() -> None:
    from engine.interaction import pick_interactable

    class _Behaviour:
        def on_interact(self, *_a, **_k) -> None:
            return

    class _Entity:
        def __init__(self, entity_id: str, *, x: float, y: float, entity_data: dict) -> None:
            self.center_x = float(x)
            self.center_y = float(y)
            self.mesh_entity_data = dict(entity_data)
            self.mesh_entity_data["id"] = entity_id
            self.mesh_behaviours_runtime = [_Behaviour()]

    flags: dict[str, bool] = {}

    def _get_flag(name: str, default: bool = False) -> bool:
        return bool(flags.get(name, default))

    barrier_id = "side_room_01_barrier_184_184_0_0"
    transition_id = "side_room_01_transition_reward_nook_01_184_184_0_0"
    assert barrier_id < transition_id

    barrier = _Entity(barrier_id, x=184.0, y=184.0, entity_data={"forbid_flags": ["demo.side_key_used"]})
    transition = _Entity(transition_id, x=184.0, y=184.0, entity_data={})

    picked = pick_interactable(
        [transition, barrier],
        player_pos=(184.0, 184.0),
        max_dist=1.0,
        get_flag=_get_flag,
    )
    assert picked is barrier

    flags["demo.side_key_used"] = True
    picked = pick_interactable(
        [transition, barrier],
        player_pos=(184.0, 184.0),
        max_dist=1.0,
        get_flag=_get_flag,
    )
    assert picked is transition

