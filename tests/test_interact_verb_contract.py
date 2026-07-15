from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.behaviours.interactable import InteractableBehaviour
from engine.behaviours.player_controller import PlayerController
from engine.input import InputManager
from engine.interaction import format_interact_prompt_text, perform_interaction, resolve_interaction_candidate, select_interaction_candidate
from tests._typing import as_any

pytestmark = [pytest.mark.fast]

KEY_E = 101
KEY_K = 107


class _Behaviour:
    def __init__(
        self,
        label: str,
        calls: list[str],
        *,
        priority: int = 0,
        radius: float | None = None,
        enabled: bool = True,
        raises: bool = False,
    ) -> None:
        self.interact_label = label
        self.calls = calls
        self.interaction_priority = priority
        if radius is not None:
            self.interact_radius = radius
        self.enabled = enabled
        self.raises = raises

    def can_interact_with(self, _actor: Any) -> bool:
        return bool(self.enabled)

    def get_interact_label(self, _actor: Any) -> str:
        return self.interact_label

    def on_interact(self, _window: Any, _actor: Any) -> None:
        self.calls.append(self.interact_label)
        if self.raises:
            raise RuntimeError("boom")


def _sprite(
    entity_id: str,
    x: float,
    y: float,
    behaviours: list[Any] | None = None,
    *,
    facing: str | None = None,
    tag: str = "npc",
    width: float = 16.0,
    height: float = 16.0,
    **data: Any,
) -> SimpleNamespace:
    payload = {"id": entity_id, "name": entity_id, **data}
    if facing is not None:
        payload["facing"] = facing
    return SimpleNamespace(
        mesh_id=entity_id,
        mesh_name=entity_id,
        mesh_tag=tag,
        mesh_tags=[tag],
        mesh_entity_data=payload,
        mesh_behaviours_runtime=list(behaviours or []),
        center_x=float(x),
        center_y=float(y),
        width=float(width),
        height=float(height),
        visible=True,
    )


def _window(actor: Any, entities: list[Any]) -> SimpleNamespace:
    scene = SimpleNamespace(_find_player_sprite=lambda: actor, all_sprites=list(entities), solid_sprites=None)
    return SimpleNamespace(
        player=actor,
        scene_controller=scene,
        all_sprites=list(entities),
        get_flag=lambda _name, default=False: default,
        input=None,
        move_entity_with_collision=lambda entity, dx, dy, dt=0.0: None,
        player_input_blocked=lambda: False,
        is_input_locked=lambda: False,
        dialogue_blocks_input=lambda: False,
    )


def test_resolver_ranking_facing_radius_and_ties() -> None:
    calls: list[str] = []
    actor = _sprite("player", 0, 0, [], facing="right", tag="player", width=20, height=20)
    behind = _sprite("behind", -20, 0, [_Behaviour("behind", calls)])
    forward_far = _sprite("forward_far", 30, 0, [_Behaviour("far", calls)])
    forward_near = _sprite("forward_near", 10, 0, [_Behaviour("near", calls)])

    candidate = select_interaction_candidate([behind, forward_far, forward_near], actor=actor, max_dist=72)
    assert candidate is not None
    assert candidate.entity is forward_near

    high = _sprite("high", 40, 0, [_Behaviour("high", calls, priority=5)])
    candidate = select_interaction_candidate([forward_near, high], actor=actor, max_dist=72)
    assert candidate is not None and candidate.entity is high

    diagonal = _sprite("diagonal", 20, 20, [_Behaviour("diagonal", calls)])
    straight = _sprite("straight", 30, 0, [_Behaviour("straight", calls)])
    candidate = select_interaction_candidate([diagonal, straight], actor=actor, max_dist=72)
    assert candidate is not None and candidate.entity is straight

    tie_b = _sprite("b", 20, 0, [_Behaviour("b", calls)])
    tie_a = _sprite("a", 20, 0, [_Behaviour("a", calls)])
    candidate = select_interaction_candidate([tie_b, tie_a], actor=actor, max_dist=72)
    assert candidate is not None and candidate.entity is tie_a

    actor.mesh_entity_data["facing"] = "left"
    candidate = select_interaction_candidate([behind, forward_near], actor=actor, max_dist=72)
    assert candidate is not None and candidate.entity is behind

    overlap_behind = _sprite("overlap_behind", -2, 0, [_Behaviour("overlap", calls)], width=20, height=20)
    actor.mesh_entity_data["facing"] = "right"
    candidate = select_interaction_candidate([overlap_behind], actor=actor, max_dist=72)
    assert candidate is not None and candidate.entity is overlap_behind

    radius_entity = _sprite("radius_entity", 60, 0, [_Behaviour("r", calls)], interact_radius=64)
    assert select_interaction_candidate([radius_entity], actor=actor, max_dist=72) is not None
    assert select_interaction_candidate([radius_entity], actor=actor, max_dist=40) is None

    radius_behaviour = _sprite("radius_behaviour", 55, 0, [_Behaviour("r", calls, radius=60)])
    assert select_interaction_candidate([radius_behaviour], actor=actor, max_dist=72) is not None


def test_resolver_excludes_gated_malformed_and_ineligible_entities() -> None:
    calls: list[str] = []
    actor = _sprite("player", 0, 0, [], facing="right", tag="player")
    disabled = _sprite("disabled", 10, 0, [_Behaviour("disabled", calls, enabled=False)])
    no_behaviour = _sprite("none", 5, 0, [])
    malformed = SimpleNamespace(mesh_entity_data={"id": "bad"}, mesh_behaviours_runtime=[_Behaviour("bad", calls)])
    gated = _sprite("gated", 8, 0, [_Behaviour("gated", calls)], require_flags=["flag.on"])

    candidate = select_interaction_candidate(
        [disabled, no_behaviour, malformed, gated],
        actor=actor,
        get_flag=lambda _name, default=False: default,
    )
    assert candidate is None

    first = _Behaviour("first", calls)
    second = _Behaviour("second", calls)
    multi = _sprite("multi", 10, 0, [first, second])
    candidate = select_interaction_candidate([multi], actor=actor)
    assert candidate is not None
    assert candidate.entity is multi
    assert candidate.behaviours == (first, second)


def test_prompt_uses_authoritative_candidate_and_labels() -> None:
    calls: list[str] = []
    actor = _sprite("player", 0, 0, [], facing="right", tag="player")
    behaviour = _Behaviour("Talk", calls)
    entity = _sprite("npc", 30, 0, [behaviour], name="EntityName")
    window = _window(actor, [actor, entity])
    candidate = resolve_interaction_candidate(window)
    assert candidate is not None
    assert candidate.entity is entity
    assert format_interact_prompt_text(candidate, hint="K") == "K: Interact: Talk"

    behaviour.interact_label = "Interact"
    candidate = resolve_interaction_candidate(window)
    assert candidate is not None
    assert candidate.label == "EntityName"
    assert format_interact_prompt_text(candidate, hint="A") == "A: Interact: EntityName"

    actor.mesh_entity_data["facing"] = "left"
    assert resolve_interaction_candidate(window) is None


def test_perform_interaction_invokes_one_entity_behaviours_once_and_continues_after_failure() -> None:
    calls: list[str] = []
    actor = _sprite("player", 0, 0, [], facing="right", tag="player")
    first = _Behaviour("first", calls, raises=True)
    second = _Behaviour("second", calls)
    chosen = _sprite("chosen", 10, 0, [first, second])
    other = _sprite("other", 12, 0, [_Behaviour("other", calls)])
    window = _window(actor, [actor, chosen, other])

    assert perform_interaction(window, actor=actor) is True
    assert calls == ["first", "second"]


def test_player_controller_owns_keyboard_and_gamepad_interaction_edges() -> None:
    calls: list[str] = []
    actor = _sprite("player", 0, 0, [], facing="right", tag="player")
    target = _sprite("target", 10, 0, [_Behaviour("target", calls)])
    manager = InputManager()
    manager.bind("interact", KEY_E)
    window = _window(actor, [actor, target])
    window.input = manager
    controller = PlayerController(actor, as_any(window), speed=0.0)

    manager.press(KEY_E)
    manager.update(0.016)
    controller.update(0.016)
    manager.update(0.016)
    controller.update(0.016)
    assert calls == ["target"]

    manager.release(KEY_E)
    manager.update(0.016)
    controller.update(0.016)
    manager.press(KEY_E)
    manager.update(0.016)
    controller.update(0.016)
    assert calls == ["target", "target"]

    manager.release(KEY_E)
    manager.update(0.016)
    controller.update(0.016)
    manager.set_gamepad_state(
        actions_down={"interact"},
        axis_values={("move_left", "move_right"): 0.0, ("move_down", "move_up"): 0.0},
        supported_actions={"interact", "move_left", "move_right", "move_down", "move_up"},
        source_active=True,
    )
    manager.update(0.016)
    controller.update(0.016)
    assert calls == ["target", "target", "target"]
    assert not hasattr(window, "_mesh_interact_consumed")


def test_keyboard_router_records_interact_without_direct_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.interaction as interaction
    from engine.input_runtime import capture as input_capture

    def _direct_call(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("router must not perform world interaction")

    monkeypatch.setattr(interaction, "perform_interaction", _direct_call)

    manager = InputManager()
    manager.bind("interact", KEY_K)
    controller = SimpleNamespace(
        manager=manager,
        _keys=set(),
        is_input_locked=lambda: False,
        window=SimpleNamespace(
            show_debug=False,
            console_controller=SimpleNamespace(active=False, process_key=lambda *_args: False),
            ui_controller=SimpleNamespace(input_blocked=False, on_key_press=lambda *_args: False),
            editor_controller=SimpleNamespace(active=False),
            cutscene_controller=None,
        ),
    )

    assert input_capture.handle_key_press(controller, KEY_K, 0) is False
    assert KEY_K in manager.get_keys_down()
    assert KEY_K in controller._keys


def test_interactable_behaviour_event_cooldown_one_shot_tags_and_state() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    entity = _sprite("terminal", 0, 0, [])
    actor = _sprite("player", 5, 0, [], tag="player")
    window = SimpleNamespace(
        scene_controller=SimpleNamespace(all_sprites=[entity, actor]),
        gameplay_event_bus=None,
    )

    def _emit(event_type: str, **payload: Any) -> None:
        events.append((event_type, payload))

    window.gameplay_event_bus = SimpleNamespace(emit=_emit)
    behaviour = InteractableBehaviour(
        entity,
        window,
        interact_event="terminal.used",
        interact_radius=12,
        cooldown=0.5,
        one_shot=True,
        target_tags=["player"],
    )
    entity.mesh_behaviours_runtime = [behaviour]

    assert behaviour.subscribed_event_types() == frozenset()
    assert behaviour.can_interact_with(actor) is True
    behaviour.on_interact(window, actor)
    assert [event[0] for event in events] == ["terminal.used"]
    assert behaviour.can_interact_with(actor) is False
    behaviour.on_interact(window, actor)
    assert len(events) == 1

    state = behaviour.saveable_state()
    restored = InteractableBehaviour(entity, window, one_shot=True)
    restored.restore_state(state)
    assert restored.saveable_state()["consumed"] is True
