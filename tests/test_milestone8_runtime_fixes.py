"""Runtime defects the capability lab found in Milestone 8 (docs/reviews/milestone8_runtime_reliability.md).

Each was measured in the real window first; these pin the fixes without one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


def test_enemy_ai_chases_at_its_speed() -> None:
    """It moved only on the frames it re-steered (every 0.2 s): 9 px/s measured for a speed of 100."""
    from engine.behaviours.enemy_ai import EnemyAI

    target = SimpleNamespace(center_x=1000.0, center_y=0.0, mesh_tag="player")
    enemy = SimpleNamespace(center_x=0.0, center_y=0.0, angle=0.0, change_x=0.0, change_y=0.0, mesh_entity_data={},
                            mesh_behaviours_runtime=[])

    def move(sprite: Any, dx: float, dy: float, friction: float = 1.0) -> None:  # noqa: ARG001
        sprite.center_x += dx
        sprite.center_y += dy

    window = SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=[target], move_entity_with_collision=move))
    ai = EnemyAI(enemy, window, target_tag="player", detect_radius=2000, lose_radius=3000, speed=100,
                 use_patrol=False)
    for _ in range(60):
        ai.update(1 / 60)
    assert 90.0 <= enemy.center_x <= 110.0


def _scene_settings_controller(config: Any, day_night: Any, lighting: Any) -> Any:
    window = SimpleNamespace(day_night=day_night, engine_config=config, lighting=lighting,
                             set_next_spawn_point=lambda spawn: setattr(window, "spawn", spawn))
    return SimpleNamespace(window=window)


def test_a_room_with_a_named_background_colour_still_applies_day_night_and_initial_spawn(monkeypatch) -> None:
    """apply_scene_settings returned early on a named colour, so Studio rooms (which have one) never ran a clock."""
    from engine.scene_runtime import scene_load_apply

    monkeypatch.setattr(scene_load_apply.optional_arcade.arcade, "get_window", lambda: object())
    monkeypatch.setattr(scene_load_apply.optional_arcade.arcade, "set_background_color", lambda _c: None)
    hours: list[float] = []
    day_night = SimpleNamespace(enabled=False, set_hour=hours.append, set_cycle_length_seconds=lambda _s: None)
    controller = _scene_settings_controller(SimpleNamespace(day_night_enabled=False), day_night,
                                            SimpleNamespace(ambient_color=(9, 9, 9, 255), base_ambient_color=(255, 255, 255, 255)))
    scene_load_apply.apply_scene_settings(controller, {"background_color": "BLACK", "day_night_enabled": True,
                                                      "time_of_day_hour": 6, "initial_spawn": "gate"})
    assert day_night.enabled and hours == [6.0] and controller.window.spawn == "gate"
    # The next room says nothing: the clock stops (the project's setting) and the project's ambient comes back.
    scene_load_apply.apply_scene_settings(controller, {"background_color": "BLACK"})
    assert not day_night.enabled
    assert controller.window.lighting.ambient_color == (255, 255, 255, 255)


def test_a_room_can_switch_lighting_off_and_the_next_room_gets_the_projects_setting() -> None:
    from engine.scene_lifecycle_controller import configure_scene_lighting

    class Lighting:
        enabled, available = True, True

        def clear_dynamic_lights(self) -> None: ...
        def configure_scene_lights(self, _cfg) -> None: ...
        def configure_scene_occluders(self, _cfg) -> None: ...
        def set_ambient_tint(self, _tint) -> None: ...

    window = SimpleNamespace(lighting=Lighting(), engine_config=SimpleNamespace(lighting_enabled=True,
                                                                               ambient_light_rgba=(255, 255, 255, 255)))
    configure_scene_lighting(window, {"occluders": []}, {"lighting_enabled": False}, "dark.json")
    assert window.lighting.enabled is False
    configure_scene_lighting(window, {"occluders": []}, {}, "next.json")
    assert window.lighting.enabled is True


def test_an_npc_schedule_drives_its_patrol_once_the_behaviours_are_attached() -> None:
    """The scene attaches an object's behaviours after building all of them; the schedule looked once, too early."""
    from engine.behaviours.npc_schedule import NpcSchedule
    from engine.behaviours.patrol import PatrolBehaviour

    def move(sprite: Any, dx: float, dy: float, friction: float = 1.0) -> None:  # noqa: ARG001
        sprite.center_x += dx
        sprite.center_y += dy

    clock = SimpleNamespace(hour=6.0)
    window = SimpleNamespace(day_night=clock, move_entity_with_collision=move)
    npc = SimpleNamespace(center_x=0.0, center_y=0.0, mesh_entity_data={}, mesh_behaviours_runtime=[], mesh_name="npc")
    blocks = [{"start_hour": 6, "end_hour": 8, "mode": "stand", "x": 0, "y": 0},
              {"start_hour": 8, "end_hour": 20, "mode": "patrol", "patrol_points": [{"x": 0, "y": 0}, {"x": 500, "y": 0}]}]
    built = [PatrolBehaviour(npc, window, patrol_points=[], patrol_speed=60), NpcSchedule(npc, window, schedules=blocks)]
    npc.mesh_behaviours_runtime = built  # as entity_factory does, after the loop
    for _ in range(30):
        for behaviour in built:
            behaviour.update(1 / 60)
    assert npc.center_x == 0.0  # standing until 08:00
    clock.hour = 9.0
    for _ in range(60):
        for behaviour in built:
            behaviour.update(1 / 60)
    assert npc.center_x > 30.0  # walking its route


def test_hard_shadows_are_drawn_through_the_world_camera(monkeypatch) -> None:
    """Subtracting the camera's corner ignored zoom: at 1.8x the lab saw a pillar's shadow drawn far from it."""
    import engine.optional_arcade
    from engine.lighting import shadow_pipeline

    drawn: list[list[tuple[float, float]]] = []
    events: list[str] = []
    monkeypatch.setattr(engine.optional_arcade.arcade, "draw_polygon_filled",
                        lambda points, _colour: drawn.append(list(points)), raising=False)
    window = SimpleNamespace(
        width=1280, height=720,
        camera=SimpleNamespace(bottom_left=(500.0, 300.0), use=lambda: events.append("world")),
        camera_controller=SimpleNamespace(use_gui_camera=lambda: events.append("gui")))
    manager = SimpleNamespace(
        _layer=object(), window=window, shadows_mode="hard", _draw_layer_safe=lambda: True,
        _select_shadow_light=lambda: ("static", (240.0, 240.0), 220.0, None),
        _static_occluders=[{"id": "pillar", "type": "rect", "x": 320, "y": 176, "width": 32, "height": 128}])
    assert shadow_pipeline.end_hard_shadows_overlay(manager)
    assert drawn and events == ["world", "gui"]
    xs = [x for poly in drawn for x, _ in poly]
    assert min(xs) >= 320.0 - 1e-6  # world coordinates: the shadow starts at the pillar, not offset by the camera


def test_quest_hook_counts_events_on_the_live_event_path(monkeypatch) -> None:
    """It subscribed only to the gameplay bus, which the game never creates: in play it heard nothing."""
    from engine.behaviours import quest_hook
    from engine.events import MeshEvent

    emitted: list[str] = []
    monkeypatch.setattr(quest_hook, "emit_gameplay_event", lambda _w, kind, _p, **_k: emitted.append(kind))
    entity = SimpleNamespace(mesh_id="board", mesh_name="Board", mesh_entity_data={})
    hook = quest_hook.QuestHookBehaviour(entity, SimpleNamespace(), quest_id="q", step_id="s",
                                         listen_events=["herald_done"], target_count=1)
    assert hook.subscribed_event_types() == frozenset({"herald_done"})
    hook.on_event(MeshEvent(type="something_else", payload={}))
    hook.on_event(MeshEvent(type="herald_done", payload={}))
    assert hook.is_completed and emitted == ["quest_progress", "quest_step_completed"]
    # Where the gameplay bus exists (the episode harness), events go there instead: nothing counted twice.
    bus_hook = quest_hook.QuestHookBehaviour(entity, SimpleNamespace(gameplay_event_bus=None), listen_events=["x"])
    bus_hook.window = SimpleNamespace(gameplay_event_bus=object())
    bus_hook.on_event(MeshEvent(type="x", payload={}))
    assert bus_hook.current_count == 0


def test_f6_in_play_loads_the_quick_save_f5_writes() -> None:
    """F6 loaded save_1.json, which F5 no longer writes when there is a SaveManager: a stale or missing save."""
    from engine.input_runtime.capture_key_router_handlers_global import _handle_savegame_load_or_play

    loaded: list[str] = []
    window = SimpleNamespace(editor_controller=None, save_manager=SimpleNamespace(load_game=loaded.append))
    assert _handle_savegame_load_or_play(window)
    assert loaded == ["quicksave"]
