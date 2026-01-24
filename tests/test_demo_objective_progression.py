from __future__ import annotations

import json
import types
from pathlib import Path

from engine.behaviours.set_game_state_on_event import SetGameStateOnEvent
from engine.event_runtime.emit import emit_event
from engine.events import MeshEventBus
from engine.ui import (
    DEMO_COMPLETE_ENDCAP_SECONDS,
    DEMO_INTERIOR_HINT_SECONDS,
    maybe_enqueue_demo_interior_hint,
    maybe_trigger_demo_complete_endcap,
)


class _Window:
    def __init__(self) -> None:
        self.event_bus = MeshEventBus()
        self._flags: dict[str, bool] = {}
        self.flag_calls: list[tuple[str, bool]] = []
        self.player_hud = types.SimpleNamespace(toasts=[])
        self.player_hud.enqueue_toast = lambda message, *, seconds=4.0: self.player_hud.toasts.append(str(message))  # type: ignore[assignment]  # noqa: ARG005
        self.demo_complete_calls: list[float] = []
        self.demo_complete_overlay = types.SimpleNamespace(
            show=lambda *, seconds=DEMO_COMPLETE_ENDCAP_SECONDS: self.demo_complete_calls.append(float(seconds))
        )

    def emit_event(self, event) -> None:  # noqa: ANN001
        self.event_bus.emit_event(event)

    def emit_signal(self, event_type: str, **payload) -> None:  # noqa: ANN003
        emit_event(self, event_type, dict(payload))

    def set_flag(self, name: str, value: bool = True) -> None:
        key = str(name)
        val = bool(value)
        previous = bool(self._flags.get(key, False))
        self._flags[key] = val
        self.flag_calls.append((key, val))
        if key == "demo.reached_cellar":
            maybe_trigger_demo_complete_endcap(self, previous=previous, current=val)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return bool(self._flags.get(str(name), default))

    def tick(self, dt: float) -> None:
        maybe_enqueue_demo_interior_hint(self, dt=float(dt))


def _load_scene(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find_entity(scene: dict, predicate) -> dict:  # noqa: ANN001
    for entity in scene.get("entities", []):
        if predicate(entity):
            return entity
    raise AssertionError("matching entity not found")


def test_demo_objective_progression_sets_flags_and_is_idempotent() -> None:
    window = _Window()

    door_field = _load_scene("scenes/door_field.json")
    warden = _find_entity(
        door_field,
        lambda e: e.get("id") == "door_field_fieldwarden_150_150_0_0",
    )
    nodes = warden["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]
    assert "demo_objective" in nodes
    assert any(
        choice.get("id") == "demo_objective_start"
        for choice in nodes["intro"]["choices"]
        if isinstance(choice, dict)
    )

    hook = _find_entity(
        door_field,
        lambda e: (
            isinstance(e.get("behaviour_config"), dict)
            and isinstance(e["behaviour_config"].get("SetGameStateOnEvent"), dict)
            and e["behaviour_config"]["SetGameStateOnEvent"].get("event_type") == "dialogue_choice"
            and e["behaviour_config"]["SetGameStateOnEvent"].get("payload_value") == "demo_objective_start"
        ),
    )

    hook_cfg = hook["behaviour_config"]["SetGameStateOnEvent"]
    hook_entity = types.SimpleNamespace(mesh_entity_data=hook, mesh_name=hook.get("name", "Hook"))
    SetGameStateOnEvent(hook_entity, window, **hook_cfg)

    assert window.get_flag("demo.objective_started") is False
    window.emit_signal("dialogue_choice", entity="FieldWarden", choice_id="demo_objective_start")
    assert window.get_flag("demo.objective_started") is True
    assert [k for k, _ in window.flag_calls].count("demo.objective_started") == 1
    assert window.player_hud.toasts == ["Objective: Enter the cellar"]

    window.emit_signal("dialogue_choice", entity="FieldWarden", choice_id="demo_objective_start")
    assert [k for k, _ in window.flag_calls].count("demo.objective_started") == 1
    assert window.player_hud.toasts == ["Objective: Enter the cellar"]

    window2 = _Window()
    door_interior = _load_scene("scenes/door_interior.json")
    interior_zone_entity = _find_entity(door_interior, lambda e: e.get("name") == "DemoObjectiveInteriorZone")
    interior_zone_cfg = interior_zone_entity["behaviour_config"]["SetGameStateOnEvent"]
    interior_zone_sprite = types.SimpleNamespace(
        mesh_entity_data=interior_zone_entity, mesh_name=interior_zone_entity.get("name", "Zone")
    )
    SetGameStateOnEvent(interior_zone_sprite, window2, **interior_zone_cfg)

    window2.emit_signal("entered_zone", zone="DemoObjectiveInteriorZone", actor="Player", position=(0.0, 0.0))
    assert window2.get_flag("demo.reached_interior") is False
    assert window2.player_hud.toasts == []

    window2.set_flag("demo.objective_started", True)
    window2.emit_signal("entered_zone", zone="DemoObjectiveInteriorZone", actor="Player", position=(0.0, 0.0))
    assert window2.get_flag("demo.reached_interior") is True
    assert [k for k, _ in window2.flag_calls].count("demo.reached_interior") == 1
    assert window2.player_hud.toasts == ["Objective: Find the cellar"]

    window2.emit_signal("entered_zone", zone="DemoObjectiveInteriorZone", actor="Player", position=(0.0, 0.0))
    assert [k for k, _ in window2.flag_calls].count("demo.reached_interior") == 1
    assert window2.player_hud.toasts == ["Objective: Find the cellar"]

    cellar = _load_scene("scenes/cellar.json")
    zone_entity = _find_entity(cellar, lambda e: e.get("name") == "DemoObjectiveCellarZone")
    zone_cfg = zone_entity["behaviour_config"]["SetGameStateOnEvent"]
    zone_sprite = types.SimpleNamespace(mesh_entity_data=zone_entity, mesh_name=zone_entity.get("name", "Zone"))
    SetGameStateOnEvent(zone_sprite, window2, **zone_cfg)

    window2.emit_signal("entered_zone", zone="DemoObjectiveCellarZone", actor="Player", position=(0.0, 0.0))
    assert window2.get_flag("demo.reached_cellar") is True
    assert [k for k, _ in window2.flag_calls].count("demo.reached_cellar") == 1
    assert window2.player_hud.toasts == ["Objective: Find the cellar", "Objective complete!"]
    assert window2.demo_complete_calls == [DEMO_COMPLETE_ENDCAP_SECONDS]

    window2.emit_signal("entered_zone", zone="DemoObjectiveCellarZone", actor="Player", position=(0.0, 0.0))
    assert [k for k, _ in window2.flag_calls].count("demo.reached_cellar") == 1
    assert window2.player_hud.toasts == ["Objective: Find the cellar", "Objective complete!"]
    assert window2.demo_complete_calls == [DEMO_COMPLETE_ENDCAP_SECONDS]


def test_demo_objective_interior_hint_toast_is_one_shot_and_gated_by_reached_interior() -> None:
    window = _Window()
    window.set_flag("demo.objective_started", True)
    window.tick(DEMO_INTERIOR_HINT_SECONDS - 0.1)
    assert window.player_hud.toasts == []

    window.tick(1.0)
    assert window.player_hud.toasts == ["Hint: Head inside the building."]
    assert window.get_flag("demo.interior_hint_shown") is True

    window.tick(999.0)
    assert window.player_hud.toasts == ["Hint: Head inside the building."]

    window2 = _Window()
    window2.set_flag("demo.objective_started", True)
    window2.set_flag("demo.reached_interior", True)
    window2.tick(DEMO_INTERIOR_HINT_SECONDS + 10.0)
    assert window2.player_hud.toasts == []
