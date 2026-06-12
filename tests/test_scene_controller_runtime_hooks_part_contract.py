from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    sc = object.__new__(SceneController)
    sc.layers = {}
    sc.window = SimpleNamespace(strict_mode=False)
    return sc


def test_runtime_hook_methods_are_bound_from_part_module() -> None:
    from engine.scene_controller import SceneController

    for name in (
        "_layer_update_order",
        "_iter_layered_sprites",
        "_deliver_events_to_behaviours",
        "_pre_update_behaviour_stage",
        "_update_behaviour_stage",
        "_update_movement_stage",
        "_late_update_stage",
        "update",
    ):
        method = getattr(SceneController, name, None)
        assert callable(method), f"SceneController.{name} missing or not callable"
        assert getattr(method, "__module__", None) == "engine.scene_controller_parts.runtime_hooks"


def test_layer_update_order_prefers_standard_layers_then_preserves_rest() -> None:
    sc = _make_controller()
    sc.layers = {
        "effects": [],
        "foreground": [],
        "entities": [],
        "background": [],
        "ui": [],
    }

    assert sc._layer_update_order() == ["background", "entities", "foreground", "effects", "ui"]


def test_event_delivery_continues_in_non_strict_mode_after_handler_error(capsys: pytest.CaptureFixture[str]) -> None:
    sc = _make_controller()
    calls: list[tuple[str, str]] = []

    class FailingBehaviour:
        def on_event(self, event: Any) -> None:
            calls.append(("failing", event.type))
            raise RuntimeError("boom")

    class HealthyBehaviour:
        def on_event(self, event: Any) -> None:
            calls.append(("healthy", event.type))

    sprite_a = SimpleNamespace(mesh_name="a", mesh_behaviours_runtime=[FailingBehaviour()])
    sprite_b = SimpleNamespace(mesh_name="b", mesh_behaviours_runtime=[HealthyBehaviour()])
    sc.layers = {"entities": [sprite_a, sprite_b]}

    sc._deliver_events_to_behaviours([SimpleNamespace(type="ping")])

    assert calls == [("failing", "ping"), ("healthy", "ping")]
    assert "ERROR delivering 'ping'" in capsys.readouterr().out


def test_event_delivery_raises_in_strict_mode() -> None:
    sc = _make_controller()
    sc.window.strict_mode = True

    class FailingBehaviour:
        def on_event(self, event: Any) -> None:
            raise RuntimeError("boom")

    sprite = SimpleNamespace(mesh_name="a", mesh_behaviours_runtime=[FailingBehaviour()])
    sc.layers = {"entities": [sprite]}

    with pytest.raises(RuntimeError, match="boom"):
        sc._deliver_events_to_behaviours([SimpleNamespace(type="ping")])


def test_runtime_stages_skip_frozen_sprites_and_preserve_layer_order() -> None:
    sc = _make_controller()
    calls: list[str] = []

    class Behaviour:
        def __init__(self, name: str) -> None:
            self.name = name

        def pre_update(self, dt: float) -> None:
            calls.append(f"pre:{self.name}:{dt}")

        def update(self, dt: float) -> None:
            calls.append(f"update:{self.name}:{dt}")

        def late_update(self, dt: float) -> None:
            calls.append(f"late:{self.name}:{dt}")

    class Sprite(SimpleNamespace):
        def update(self) -> None:
            calls.append(f"move:{self.mesh_name}")

    sprite_background = Sprite(mesh_name="bg", frozen=False, mesh_behaviours_runtime=[Behaviour("bg")])
    sprite_entities = Sprite(mesh_name="entity", frozen=False, mesh_behaviours_runtime=[Behaviour("entity")])
    sprite_frozen = Sprite(mesh_name="frozen", frozen=True, mesh_behaviours_runtime=[Behaviour("frozen")])
    sc.layers = {
        "foreground": [sprite_frozen],
        "entities": [sprite_entities],
        "background": [sprite_background],
    }

    sc._pre_update_behaviour_stage(0.5)
    sc._update_behaviour_stage(0.5)
    sc._update_movement_stage(0.5)
    sc._late_update_stage(0.5)

    assert calls == [
        "pre:bg:0.5",
        "pre:entity:0.5",
        "update:bg:0.5",
        "update:entity:0.5",
        "move:bg",
        "move:entity",
        "late:bg:0.5",
        "late:entity:0.5",
    ]
