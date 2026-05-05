from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from engine.constants import EVENT_ANIMATION_EVENT


pytestmark = [pytest.mark.fast]


def test_animation_event_sink_methods_are_bound_from_part_module() -> None:
    from engine.scene_controller import SceneController

    for name in (
        "_handle_animation_event",
        "_apply_animation_root_motion",
        "_resolve_root_motion_config",
        "_normalize_root_motion_config",
        "_extract_root_motion_vector",
        "_coerce_float",
        "_coerce_motion_vector",
    ):
        method = getattr(SceneController, name, None)
        assert callable(method), f"SceneController.{name} missing or not callable"
        assert getattr(method, "__module__", None) == "engine.scene_controller_parts.animation_event_sink"


def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    sc = object.__new__(SceneController)
    sc.layers = {}
    sc.solid_sprites = []

    emitted: list[tuple[str, dict[str, Any]]] = []

    def _emit_signal(name: str, **payload: Any) -> None:
        emitted.append((name, payload))

    sc.window = SimpleNamespace(
        strict_mode=False,
        show_debug=False,
        emit_signal=_emit_signal,
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

    sc.entities = _Entities()
    return sc, emitted


def _make_sprite(
    *,
    x: float = 10.0,
    y: float = 20.0,
    angle: float = 0.0,
    tag: str | None = "tag",
    entity_data: dict[str, Any] | None = None,
) -> Any:
    return SimpleNamespace(
        mesh_name="entity",
        mesh_tag=tag,
        center_x=float(x),
        center_y=float(y),
        angle=float(angle),
        frozen=False,
        mesh_entity_data=dict(entity_data or {}),
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"move": [1.0, 2.0], "displacement": [3.0, 4.0], "dx": 5.0, "dy": 6.0}, (1.0, 2.0)),
        ({"displacement": [3.0, 4.0], "dx": 5.0, "dy": 6.0}, (3.0, 4.0)),
        ({"dx": 5.0, "dy": 6.0}, (5.0, 6.0)),
    ],
)
def test_root_motion_payload_parsing_precedence(payload: dict[str, Any], expected: tuple[float, float]) -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}})

    motion = sc._apply_animation_root_motion(sprite, payload)

    assert motion == expected
    assert (sprite.center_x, sprite.center_y) == pytest.approx((10.0 + expected[0], 20.0 + expected[1]))


def test_root_motion_uses_collision_helper_when_collision_enabled() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": True}})
    calls: list[tuple[Any, float, float, float]] = []

    def _move_entity_with_collision(target: Any, dx: float, dy: float, friction: float) -> None:
        calls.append((target, dx, dy, friction))
        target.center_x += dx
        target.center_y += dy

    sc.move_entity_with_collision = _move_entity_with_collision

    motion = sc._apply_animation_root_motion(sprite, {"dx": 2.5, "dy": -1.5})

    assert motion == (2.5, -1.5)
    assert calls == [(sprite, 2.5, -1.5, 1.0)]
    assert sprite.mesh_entity_data["x"] == pytest.approx(12.5)
    assert sprite.mesh_entity_data["y"] == pytest.approx(18.5)


def test_root_motion_uses_direct_position_mutation_when_collision_disabled() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}})

    def _unexpected_move_entity_with_collision(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("move_entity_with_collision should not be used")

    sc.move_entity_with_collision = _unexpected_move_entity_with_collision

    motion = sc._apply_animation_root_motion(sprite, {"dx": -3.0, "dy": 4.0})

    assert motion == (-3.0, 4.0)
    assert (sprite.center_x, sprite.center_y) == pytest.approx((7.0, 24.0))


def test_root_motion_local_space_rotates_by_sprite_angle() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(angle=90.0, entity_data={"animation_root_motion": {"collision": False, "space": "local"}})

    motion = sc._apply_animation_root_motion(sprite, {"move": [1.0, 0.0]})

    assert motion is not None
    dx, dy = motion
    assert dx == pytest.approx(0.0, abs=1e-6)
    assert dy == pytest.approx(1.0, abs=1e-6)
    assert sprite.center_x == pytest.approx(10.0, abs=1e-6)
    assert sprite.center_y == pytest.approx(21.0, abs=1e-6)


def test_root_motion_world_space_applies_directly() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(angle=90.0, entity_data={"animation_root_motion": {"collision": False, "space": "world"}})

    motion = sc._apply_animation_root_motion(sprite, {"move": [1.0, 0.0]})

    assert motion == (1.0, 0.0)
    assert (sprite.center_x, sprite.center_y) == pytest.approx((11.0, 20.0))


def test_root_motion_labels_gate_ignores_non_matching_events() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False, "labels": ["step"]}})

    motion = sc._apply_animation_root_motion(sprite, {"event": "land", "dx": 2.0, "dy": 3.0})

    assert motion is None
    assert (sprite.center_x, sprite.center_y) == (10.0, 20.0)
    assert "x" not in sprite.mesh_entity_data
    assert "y" not in sprite.mesh_entity_data


def test_root_motion_labels_gate_applies_matching_events() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False, "labels": ["step"]}})

    motion = sc._apply_animation_root_motion(sprite, {"event": "step", "dx": 2.0, "dy": 3.0})

    assert motion == (2.0, 3.0)
    assert (sprite.center_x, sprite.center_y) == pytest.approx((12.0, 23.0))


def test_handle_animation_event_emits_expected_payload_keys_and_root_motion_when_applied() -> None:
    sc, emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}})

    sc._handle_animation_event(sprite, {"state": "walk", "event": "step", "frame": 3, "loop": 1, "dx": 2.0, "dy": 0.5})

    assert len(emitted) == 1
    name, payload = emitted[0]
    assert name == EVENT_ANIMATION_EVENT
    assert payload["entity"] == "entity"
    assert payload["state"] == "walk"
    assert payload["event"] == "step"
    assert payload["frame"] == 3
    assert payload["loop"] == 1
    assert payload["tag"] == "tag"
    assert payload["position"] == pytest.approx((12.0, 20.5))
    assert payload["root_motion"] == pytest.approx({"dx": 2.0, "dy": 0.5})


def test_handle_animation_event_omits_root_motion_when_no_motion_applies() -> None:
    sc, emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False, "labels": ["step"]}})

    sc._handle_animation_event(sprite, {"state": "idle", "event": "land", "frame": 1})

    assert len(emitted) == 1
    name, payload = emitted[0]
    assert name == EVENT_ANIMATION_EVENT
    assert payload["entity"] == "entity"
    assert payload["state"] == "idle"
    assert payload["event"] == "land"
    assert payload["frame"] == 1
    assert payload["loop"] == 0
    assert payload["tag"] == "tag"
    assert payload["position"] == pytest.approx((10.0, 20.0))
    assert "root_motion" not in payload


def test_resolve_root_motion_config_normalizes_and_caches_current_behavior() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(
        entity_data={
            "animation_root_motion": {
                "labels": [" step ", "impact", 7],
                "space": "world",
                "collision": False,
                "scale": 2,
            }
        }
    )

    config = sc._resolve_root_motion_config(sprite)

    assert config == {
        "scale": 2.0,
        "space": "world",
        "collision": False,
        "labels": {"step", "impact", "7"},
    }
    assert getattr(sprite, "_mesh_root_motion_config") is config

    sprite.mesh_entity_data["animation_root_motion"] = False

    assert sc._resolve_root_motion_config(sprite) is config


def test_attach_animator_passes_event_sink_that_routes_to_handle_animation_event() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite()
    entity_data: dict[str, Any] = {}
    routed: list[tuple[Any, dict[str, Any]]] = []

    def _handle_animation_event(target: Any, payload: dict[str, Any]) -> None:
        routed.append((target, payload))

    sc._handle_animation_event = _handle_animation_event

    class FakeFactory:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def build_for_entity(self, sprite_arg: Any, entity_data_arg: dict[str, Any], *, debug: bool, event_sink: Any) -> Any:
            self.calls.append(
                {
                    "sprite": sprite_arg,
                    "entity_data": entity_data_arg,
                    "debug": debug,
                    "event_sink": event_sink,
                }
            )
            return SimpleNamespace(current_state="idle")

    factory = FakeFactory()
    sc.window.animation_factory = factory

    sc._attach_animator(sprite, entity_data)

    assert len(factory.calls) == 1
    call = factory.calls[0]
    assert call["sprite"] is sprite
    assert call["entity_data"] is entity_data
    assert call["debug"] is False
    assert callable(call["event_sink"])
    call["event_sink"]({"event": "step"})
    assert routed == [(sprite, {"event": "step"})]
    assert entity_data["default_animation"] == "idle"


def test_attach_animator_defaults_debug_false_when_window_not_fully_initialized() -> None:
    sc, _emitted = _make_controller()
    delattr(sc.window, "show_debug")
    sprite = _make_sprite()
    entity_data: dict[str, Any] = {}

    class FakeFactory:
        def __init__(self) -> None:
            self.debug_values: list[bool] = []

        def build_for_entity(self, _sprite: Any, _entity_data: dict[str, Any], *, debug: bool, event_sink: Any) -> Any:  # noqa: ARG002
            self.debug_values.append(debug)
            return SimpleNamespace(current_state="idle")

    factory = FakeFactory()
    sc.window.animation_factory = factory

    sc._attach_animator(sprite, entity_data)

    assert factory.debug_values == [False]
    assert entity_data["default_animation"] == "idle"


def test_update_animation_stage_applies_event_sink_motion_during_stage() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}, "animation_state": "walk"})
    order: list[tuple[str, float, float]] = []

    class FakeAnimator:
        def __init__(self) -> None:
            self.state_calls: list[str] = []

        def set_state(self, state: str) -> None:
            self.state_calls.append(state)

        def update(self, delta_time: float) -> None:
            order.append(("update-start", sprite.center_x, sprite.center_y))
            sc._handle_animation_event(
                sprite,
                {"state": "walk", "event": "step", "frame": 2, "loop": 0, "dx": 1.5, "dy": -0.5},
            )
            order.append(("update-end", sprite.center_x, sprite.center_y))

    sprite.mesh_animator = FakeAnimator()
    sc.layers = {"entities": [sprite]}

    sc._update_animation_stage(0.25)

    assert sprite.mesh_animator.state_calls == ["walk"]
    assert order == [
        ("update-start", 10.0, 20.0),
        ("update-end", 11.5, 19.5),
    ]
    assert (sprite.center_x, sprite.center_y) == pytest.approx((11.5, 19.5))

    def _emit_signal(name: str, **payload: Any) -> None:
        emitted.append((name, payload))

    sc.window = SimpleNamespace(
        strict_mode=False,
        show_debug=False,
        emit_signal=_emit_signal,
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

    sc.entities = _Entities()
    return sc, emitted


def _make_sprite(
    *,
    x: float = 10.0,
    y: float = 20.0,
    angle: float = 0.0,
    tag: str | None = "tag",
    entity_data: dict[str, Any] | None = None,
) -> Any:
    return SimpleNamespace(
        mesh_name="entity",
        mesh_tag=tag,
        center_x=float(x),
        center_y=float(y),
        angle=float(angle),
        frozen=False,
        mesh_entity_data=dict(entity_data or {}),
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"move": [1.0, 2.0], "displacement": [3.0, 4.0], "dx": 5.0, "dy": 6.0}, (1.0, 2.0)),
        ({"displacement": [3.0, 4.0], "dx": 5.0, "dy": 6.0}, (3.0, 4.0)),
        ({"dx": 5.0, "dy": 6.0}, (5.0, 6.0)),
    ],
)
def test_root_motion_payload_parsing_precedence(payload: dict[str, Any], expected: tuple[float, float]) -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}})

    motion = sc._apply_animation_root_motion(sprite, payload)

    assert motion == expected
    assert (sprite.center_x, sprite.center_y) == pytest.approx((10.0 + expected[0], 20.0 + expected[1]))


def test_root_motion_uses_collision_helper_when_collision_enabled() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": True}})
    calls: list[tuple[Any, float, float, float]] = []

    def _move_entity_with_collision(target: Any, dx: float, dy: float, friction: float) -> None:
        calls.append((target, dx, dy, friction))
        target.center_x += dx
        target.center_y += dy

    sc.move_entity_with_collision = _move_entity_with_collision

    motion = sc._apply_animation_root_motion(sprite, {"dx": 2.5, "dy": -1.5})

    assert motion == (2.5, -1.5)
    assert calls == [(sprite, 2.5, -1.5, 1.0)]
    assert sprite.mesh_entity_data["x"] == pytest.approx(12.5)
    assert sprite.mesh_entity_data["y"] == pytest.approx(18.5)


def test_root_motion_uses_direct_position_mutation_when_collision_disabled() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}})

    def _unexpected_move_entity_with_collision(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("move_entity_with_collision should not be used")

    sc.move_entity_with_collision = _unexpected_move_entity_with_collision

    motion = sc._apply_animation_root_motion(sprite, {"dx": -3.0, "dy": 4.0})

    assert motion == (-3.0, 4.0)
    assert (sprite.center_x, sprite.center_y) == pytest.approx((7.0, 24.0))


def test_root_motion_local_space_rotates_by_sprite_angle() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(angle=90.0, entity_data={"animation_root_motion": {"collision": False, "space": "local"}})

    motion = sc._apply_animation_root_motion(sprite, {"move": [1.0, 0.0]})

    assert motion is not None
    dx, dy = motion
    assert dx == pytest.approx(0.0, abs=1e-6)
    assert dy == pytest.approx(1.0, abs=1e-6)
    assert sprite.center_x == pytest.approx(10.0, abs=1e-6)
    assert sprite.center_y == pytest.approx(21.0, abs=1e-6)


def test_root_motion_world_space_applies_directly() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(angle=90.0, entity_data={"animation_root_motion": {"collision": False, "space": "world"}})

    motion = sc._apply_animation_root_motion(sprite, {"move": [1.0, 0.0]})

    assert motion == (1.0, 0.0)
    assert (sprite.center_x, sprite.center_y) == pytest.approx((11.0, 20.0))


def test_root_motion_labels_gate_ignores_non_matching_events() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False, "labels": ["step"]}})

    motion = sc._apply_animation_root_motion(sprite, {"event": "land", "dx": 2.0, "dy": 3.0})

    assert motion is None
    assert (sprite.center_x, sprite.center_y) == (10.0, 20.0)
    assert "x" not in sprite.mesh_entity_data
    assert "y" not in sprite.mesh_entity_data


def test_root_motion_labels_gate_applies_matching_events() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False, "labels": ["step"]}})

    motion = sc._apply_animation_root_motion(sprite, {"event": "step", "dx": 2.0, "dy": 3.0})

    assert motion == (2.0, 3.0)
    assert (sprite.center_x, sprite.center_y) == pytest.approx((12.0, 23.0))


def test_handle_animation_event_emits_expected_payload_keys_and_root_motion_when_applied() -> None:
    sc, emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}})

    sc._handle_animation_event(sprite, {"state": "walk", "event": "step", "frame": 3, "loop": 1, "dx": 2.0, "dy": 0.5})

    assert len(emitted) == 1
    name, payload = emitted[0]
    assert name == EVENT_ANIMATION_EVENT
    assert payload["entity"] == "entity"
    assert payload["state"] == "walk"
    assert payload["event"] == "step"
    assert payload["frame"] == 3
    assert payload["loop"] == 1
    assert payload["tag"] == "tag"
    assert payload["position"] == pytest.approx((12.0, 20.5))
    assert payload["root_motion"] == pytest.approx({"dx": 2.0, "dy": 0.5})


def test_handle_animation_event_omits_root_motion_when_no_motion_applies() -> None:
    sc, emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False, "labels": ["step"]}})

    sc._handle_animation_event(sprite, {"state": "idle", "event": "land", "frame": 1})

    assert len(emitted) == 1
    name, payload = emitted[0]
    assert name == EVENT_ANIMATION_EVENT
    assert payload["entity"] == "entity"
    assert payload["state"] == "idle"
    assert payload["event"] == "land"
    assert payload["frame"] == 1
    assert payload["loop"] == 0
    assert payload["tag"] == "tag"
    assert payload["position"] == pytest.approx((10.0, 20.0))
    assert "root_motion" not in payload


def test_resolve_root_motion_config_normalizes_and_caches_current_behavior() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(
        entity_data={
            "animation_root_motion": {
                "labels": [" step ", "impact", 7],
                "space": "world",
                "collision": False,
                "scale": 2,
            }
        }
    )

    config = sc._resolve_root_motion_config(sprite)

    assert config == {
        "scale": 2.0,
        "space": "world",
        "collision": False,
        "labels": {"step", "impact", "7"},
    }
    assert getattr(sprite, "_mesh_root_motion_config") is config

    sprite.mesh_entity_data["animation_root_motion"] = False

    assert sc._resolve_root_motion_config(sprite) is config


def test_attach_animator_passes_event_sink_that_routes_to_handle_animation_event() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite()
    entity_data: dict[str, Any] = {}
    routed: list[tuple[Any, dict[str, Any]]] = []

    def _handle_animation_event(target: Any, payload: dict[str, Any]) -> None:
        routed.append((target, payload))

    sc._handle_animation_event = _handle_animation_event

    class FakeFactory:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def build_for_entity(self, sprite_arg: Any, entity_data_arg: dict[str, Any], *, debug: bool, event_sink: Any) -> Any:
            self.calls.append(
                {
                    "sprite": sprite_arg,
                    "entity_data": entity_data_arg,
                    "debug": debug,
                    "event_sink": event_sink,
                }
            )
            return SimpleNamespace(current_state="idle")

    factory = FakeFactory()
    sc.window.animation_factory = factory

    sc._attach_animator(sprite, entity_data)

    assert len(factory.calls) == 1
    call = factory.calls[0]
    assert call["sprite"] is sprite
    assert call["entity_data"] is entity_data
    assert call["debug"] is False
    assert callable(call["event_sink"])
    call["event_sink"]({"event": "step"})
    assert routed == [(sprite, {"event": "step"})]
    assert entity_data["default_animation"] == "idle"


def test_update_animation_stage_applies_event_sink_motion_during_stage() -> None:
    sc, _emitted = _make_controller()
    sprite = _make_sprite(entity_data={"animation_root_motion": {"collision": False}, "animation_state": "walk"})
    order: list[tuple[str, float, float]] = []

    class FakeAnimator:
        def __init__(self) -> None:
            self.state_calls: list[str] = []

        def set_state(self, state: str) -> None:
            self.state_calls.append(state)

        def update(self, delta_time: float) -> None:
            order.append(("update-start", sprite.center_x, sprite.center_y))
            sc._handle_animation_event(
                sprite,
                {"state": "walk", "event": "step", "frame": 2, "loop": 0, "dx": 1.5, "dy": -0.5},
            )
            order.append(("update-end", sprite.center_x, sprite.center_y))

    sprite.mesh_animator = FakeAnimator()
    sc.layers = {"entities": [sprite]}

    sc._update_animation_stage(0.25)

    assert sprite.mesh_animator.state_calls == ["walk"]
    assert order == [
        ("update-start", 10.0, 20.0),
        ("update-end", 11.5, 19.5),
    ]
    assert (sprite.center_x, sprite.center_y) == pytest.approx((11.5, 19.5))
