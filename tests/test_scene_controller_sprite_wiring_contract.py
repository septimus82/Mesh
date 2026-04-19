from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


pytestmark = [pytest.mark.fast]


class _FakeSprite:
    def __init__(self) -> None:
        self.texture = None
        self.center_x = 0.0
        self.center_y = 0.0
        self.scale = 1.0
        self.angle = 0.0
        self.hit_box_calls: list[tuple[Any, ...]] = []

    def set_hit_box(self, *args: Any) -> None:
        self.hit_box_calls.append(args)


class _RaisingHitBoxSprite(_FakeSprite):
    def __init__(self) -> None:
        super().__init__()
        self.raised = 0

    def set_hit_box(self, *args: Any) -> None:
        self.raised += 1
        raise RuntimeError("bad hit box")


def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    controller = object.__new__(SceneController)
    controller.layers = {}
    controller.solid_sprites = []
    controller.current_scene_path = "scenes/test.json"
    controller._suppress_spawn_toasts = True
    controller.window = SimpleNamespace(
        strict_mode=False,
        show_debug=False,
        assets=SimpleNamespace(get_texture=lambda path: f"tex:{path}"),
        scene_loader=SimpleNamespace(validate_entity=lambda entity: True),
        animation_factory=None,
    )

    class _Entities:
        @staticmethod
        def ensure_entity_data_dict(sprite: Any) -> dict[str, Any]:
            data = getattr(sprite, "mesh_entity_data", None)
            if not isinstance(data, dict):
                data = {}
                setattr(sprite, "mesh_entity_data", data)
            return data

    controller.entities = _Entities()
    return controller


def test_create_sprite_populates_runtime_metadata_and_normalized_entity_data(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core

    controller = _make_controller()
    monkeypatch.setattr(core.optional_arcade.arcade, "Sprite", _FakeSprite)
    monkeypatch.setattr(core, "maybe_enqueue_boss_spawn_toast", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core, "maybe_enqueue_miniboss_spawn_toast", lambda *_args, **_kwargs: None)

    entity = {
        "name": "Hero",
        "sprite": "assets/hero.png",
        "x": 12,
        "y": 34,
        "scale": 1.5,
        "rotation": 45,
        "tag": "player",
        "behaviours": ["wander", {"type": "talk", "params": {"speed": 2}, "radius": 4}],
        "collision_poly": [(0, 0), (1, 0), (1, 1)],
    }

    monkeypatch.setattr(core, "create_behaviour", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.geometry_tools.sanitize_poly", lambda poly: list(poly))

    sprite = controller._create_sprite(entity)

    assert sprite is not None
    assert sprite.texture == "tex:assets/hero.png"
    assert (sprite.center_x, sprite.center_y, sprite.scale, sprite.angle) == (12.0, 34.0, 1.5, 45.0)
    assert sprite.mesh_name == "Hero"
    assert sprite.mesh_tag == "player"
    assert sprite.mesh_behaviours == ["wander", "talk"]
    assert sprite.mesh_behaviour_configs == [
        {"type": "wander", "params": {}},
        {"type": "talk", "params": {"speed": 2, "radius": 4}},
    ]
    assert sprite.mesh_behaviours_runtime == []
    assert sprite.mesh_entity_data is not entity
    assert sprite.mesh_entity_data["name"] == "Hero"
    assert sprite.mesh_entity_data["behaviours"] == sprite.mesh_behaviour_configs
    assert sprite.mesh_entity_data["behaviour_config"] == {
        "talk": {"speed": 2, "radius": 4},
    }
    assert entity["behaviours"] == ["wander", {"type": "talk", "params": {"speed": 2}, "radius": 4}]
    assert sprite.hit_box_calls == [([(0, 0), (1, 0), (1, 1)],)]
    assert not hasattr(sprite, "mesh_animator")


def test_create_sprite_observes_animator_factory_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core

    controller = _make_controller()
    monkeypatch.setattr(core.optional_arcade.arcade, "Sprite", _FakeSprite)
    monkeypatch.setattr(core, "create_behaviour", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core, "maybe_enqueue_boss_spawn_toast", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core, "maybe_enqueue_miniboss_spawn_toast", lambda *_args, **_kwargs: None)

    animator = SimpleNamespace(current_state="idle")
    calls: list[dict[str, Any]] = []

    class _Factory:
        def build_for_entity(self, sprite: Any, entity_data: dict[str, Any], *, debug: bool, event_sink: Any) -> Any:
            sprite.mesh_animator = animator
            calls.append({
                "sprite": sprite,
                "entity_data": entity_data,
                "debug": debug,
                "event_sink": event_sink,
            })
            return animator

    controller.window.animation_factory = _Factory()

    sprite = controller._create_sprite({"name": "Mage", "sprite": "assets/mage.png", "behaviours": []})

    assert sprite is not None
    assert sprite.mesh_animator is animator
    assert sprite.mesh_entity_data["default_animation"] == "idle"
    assert len(calls) == 1
    assert calls[0]["sprite"] is sprite
    assert calls[0]["entity_data"] is sprite.mesh_entity_data
    assert calls[0]["debug"] is False
    assert callable(calls[0]["event_sink"])


def test_get_behaviour_configs_for_sprite_normalizes_strings_dicts_and_discards_invalid_entries() -> None:
    controller = _make_controller()
    sprite = SimpleNamespace(
        mesh_behaviour_configs=[
            "wander",
            {"type": "talk", "params": {"speed": 3}, "radius": 9},
            "  ",
            {"params": {"ignored": True}},
        ]
    )

    result = controller._get_behaviour_configs_for_sprite(sprite)

    assert result == [
        {"type": "wander", "params": {}},
        {"type": "talk", "params": {"speed": 3, "radius": 9}},
    ]
    assert sprite.mesh_behaviour_configs == result


def test_rebuild_behaviours_refreshes_runtime_container_and_picks_current_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core

    controller = _make_controller()
    sprite = SimpleNamespace(
        mesh_name="npc",
        mesh_behaviours=["wander", "talk"],
        mesh_behaviours_runtime=["stale"],
        mesh_entity_data={
            "behaviour_config": {
                "wander": {"speed": 1},
                "talk": {"radius": 2},
            }
        },
    )
    created: list[tuple[str, dict[str, Any]]] = []

    def _create_behaviour(name: str, _sprite: Any, _window: Any, *, config: dict[str, Any]) -> Any:
        created.append((name, dict(config)))
        return SimpleNamespace(config=dict(config))

    monkeypatch.setattr(core, "create_behaviour", _create_behaviour)

    controller._rebuild_behaviours_for_sprite(sprite)

    first_runtime = sprite.mesh_behaviours_runtime
    assert created == [("wander", {"speed": 1}), ("talk", {"radius": 2})]
    assert [b.mesh_behaviour_type for b in first_runtime] == ["wander", "talk"]
    assert [b.mesh_behaviour_index for b in first_runtime] == [0, 1]
    assert [b.config for b in first_runtime] == [{"speed": 1}, {"radius": 2}]

    created.clear()
    sprite.mesh_entity_data["behaviour_config"]["talk"]["radius"] = 7
    controller._rebuild_behaviours_for_sprite(sprite)

    second_runtime = sprite.mesh_behaviours_runtime
    assert second_runtime is not first_runtime
    assert created == [("wander", {"speed": 1}), ("talk", {"radius": 7})]
    assert [b.config for b in second_runtime] == [{"speed": 1}, {"radius": 7}]


def test_rebuild_behaviours_no_behaviour_case_is_safe_and_clears_runtime_container(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core

    controller = _make_controller()
    sprite = SimpleNamespace(
        mesh_behaviours=[],
        mesh_behaviours_runtime=[SimpleNamespace()],
        mesh_entity_data={},
    )

    monkeypatch.setattr(core, "create_behaviour", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected")))

    controller._rebuild_behaviours_for_sprite(sprite)

    assert sprite.mesh_behaviours_runtime == []


def test_apply_collision_poly_sets_hit_box_for_valid_points(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    sprite = _FakeSprite()

    monkeypatch.setattr("engine.geometry_tools.sanitize_poly", lambda poly: [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])

    controller._apply_collision_poly(sprite, [(0, 0), (1, 0), (1, 1)])

    assert sprite.hit_box_calls == [([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],)]


def test_apply_collision_poly_swallows_set_hit_box_failures_and_leaves_existing_state(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    sprite = _RaisingHitBoxSprite()
    sprite.mesh_name = "crate"
    sprite.mesh_entity_data = {"name": "crate"}

    monkeypatch.setattr("engine.geometry_tools.sanitize_poly", lambda poly: list(poly))

    controller._apply_collision_poly(sprite, [(0, 0), (1, 0), (1, 1)])

    assert sprite.raised == 1
    assert sprite.mesh_entity_data == {"name": "crate"}
