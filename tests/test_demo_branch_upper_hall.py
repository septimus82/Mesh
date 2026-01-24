from __future__ import annotations

import json
import types
from pathlib import Path

from engine.behaviours.set_game_state_on_event import SetGameStateOnEvent
from engine.event_runtime.emit import emit_event
from engine.events import MeshEventBus
from engine.savegame import SaveGameV1, load_savegame, save_savegame


class _Window:
    def __init__(self) -> None:
        self.event_bus = MeshEventBus()
        self._flags: dict[str, bool] = {}
        self.flag_calls: list[tuple[str, bool]] = []
        self.player_hud = types.SimpleNamespace(toasts=[])
        self.player_hud.enqueue_toast = lambda message, *, seconds=4.0: self.player_hud.toasts.append(str(message))  # type: ignore[assignment]  # noqa: ARG005

    def emit_event(self, event) -> None:  # noqa: ANN001
        self.event_bus.emit_event(event)

    def emit_signal(self, event_type: str, **payload) -> None:  # noqa: ANN003
        emit_event(self, event_type, dict(payload))

    def set_flag(self, name: str, value: bool = True) -> None:
        key = str(name)
        val = bool(value)
        self._flags[key] = val
        self.flag_calls.append((key, val))

    def get_flag(self, name: str, default: bool = False) -> bool:
        return bool(self._flags.get(str(name), default))


def _load_scene(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find_entity(scene: dict, predicate) -> dict:  # noqa: ANN001
    for entity in scene.get("entities", []):
        if predicate(entity):
            return entity
    raise AssertionError("matching entity not found")


def test_demo_branch_upper_hall_flags_are_idempotent_and_persistable(tmp_path: Path) -> None:
    window = _Window()

    door_field = _load_scene("scenes/door_field.json")
    warden = _find_entity(
        door_field,
        lambda e: e.get("id") == "door_field_fieldwarden_150_150_0_0",
    )
    nodes = warden["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]
    assert any(
        choice.get("id") == "demo_objective_upper_hall"
        for choice in nodes["intro"]["choices"]
        if isinstance(choice, dict)
    )

    hook = _find_entity(
        door_field,
        lambda e: (
            isinstance(e.get("behaviour_config"), dict)
            and isinstance(e["behaviour_config"].get("SetGameStateOnEvent"), dict)
            and e["behaviour_config"]["SetGameStateOnEvent"].get("event_type") == "dialogue_choice"
            and e["behaviour_config"]["SetGameStateOnEvent"].get("payload_value") == "demo_objective_upper_hall"
        ),
    )

    hook_cfg = hook["behaviour_config"]["SetGameStateOnEvent"]
    hook_entity = types.SimpleNamespace(mesh_entity_data=hook, mesh_name=hook.get("name", "Hook"))
    SetGameStateOnEvent(hook_entity, window, **hook_cfg)

    assert window.get_flag("demo.objective_upper_started") is False
    window.emit_signal("dialogue_choice", entity="FieldWarden", choice_id="demo_objective_upper_hall")
    assert window.get_flag("demo.objective_upper_started") is True
    assert [k for k, _ in window.flag_calls].count("demo.objective_upper_started") == 1
    assert window.player_hud.toasts == ["Optional: Visit the upper hall"]

    window.emit_signal("dialogue_choice", entity="FieldWarden", choice_id="demo_objective_upper_hall")
    assert [k for k, _ in window.flag_calls].count("demo.objective_upper_started") == 1
    assert window.player_hud.toasts == ["Optional: Visit the upper hall"]

    window2 = _Window()

    upper_hall = _load_scene("scenes/upper_hall.json")
    zone_entity = _find_entity(upper_hall, lambda e: e.get("name") == "DemoObjectiveUpperHallZone")
    zone_cfg = zone_entity["behaviour_config"]["SetGameStateOnEvent"]
    zone_sprite = types.SimpleNamespace(mesh_entity_data=zone_entity, mesh_name=zone_entity.get("name", "Zone"))
    SetGameStateOnEvent(zone_sprite, window2, **zone_cfg)

    window2.emit_signal("entered_zone", zone="DemoObjectiveUpperHallZone", actor="Player", position=(0.0, 0.0))
    assert window2.get_flag("demo.reached_upper_hall") is False

    window2.emit_signal("entered_zone", zone="DemoObjectiveUpperHallZone", actor="Player", position=(0.0, 0.0))
    assert window2.get_flag("demo.reached_upper_hall") is False

    # Now satisfy gating and assert idempotency + toast.
    window2.set_flag("demo.objective_upper_started", True)
    window2.emit_signal("entered_zone", zone="DemoObjectiveUpperHallZone", actor="Player", position=(0.0, 0.0))
    assert window2.get_flag("demo.reached_upper_hall") is True
    assert [k for k, _ in window2.flag_calls].count("demo.reached_upper_hall") == 1
    assert window2.player_hud.toasts == ["Optional complete: Reached the upper hall"]

    window2.emit_signal("entered_zone", zone="DemoObjectiveUpperHallZone", actor="Player", position=(0.0, 0.0))
    assert [k for k, _ in window2.flag_calls].count("demo.reached_upper_hall") == 1

    # Save/load preserves the new flags.
    save_path = tmp_path / "savegame.json"
    save = SaveGameV1(
        scene_path="scenes/door_field.json",
        player_x=1.0,
        player_y=2.0,
        flags={
            "demo.objective_upper_started": True,
            "demo.reached_upper_hall": True,
        },
    )
    save_savegame(save_path, save)
    loaded = load_savegame(save_path)
    assert loaded is not None
    assert loaded.flags["demo.objective_upper_started"] is True
    assert loaded.flags["demo.reached_upper_hall"] is True
