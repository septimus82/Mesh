from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


def test_pick_interactable_nearest_and_tiebreak() -> None:
    from engine.interaction import pick_interactable

    class _Behaviour:
        def on_interact(self, _window, _actor) -> None:
            return

    def _sprite(*, entity_id: str, x: float, y: float, interactable: bool):
        sprite = type("S", (), {})()
        sprite.center_x = x
        sprite.center_y = y
        sprite.mesh_entity_data = {"id": entity_id}
        sprite.mesh_behaviours_runtime = [_Behaviour()] if interactable else []
        return sprite

    player = _sprite(entity_id="player", x=0.0, y=0.0, interactable=False)
    a = _sprite(entity_id="b_id", x=10.0, y=0.0, interactable=True)
    b = _sprite(entity_id="a_id", x=10.0, y=0.0, interactable=True)
    far = _sprite(entity_id="z", x=100.0, y=0.0, interactable=True)
    non = _sprite(entity_id="c", x=1.0, y=0.0, interactable=False)

    # Tie-break by entity id (a_id < b_id)
    picked = pick_interactable([a, b, far, non, player], player_pos=(0.0, 0.0), max_dist=20.0, exclude_entity=player)
    assert picked is b

    # Nearest wins
    near = _sprite(entity_id="zzz", x=2.0, y=0.0, interactable=True)
    picked2 = pick_interactable([a, near], player_pos=(0.0, 0.0), max_dist=20.0)
    assert picked2 is near


def test_pick_interactable_respects_max_dist() -> None:
    from engine.interaction import pick_interactable

    class _Behaviour:
        def on_interact(self, _window, _actor) -> None:
            return

    sprite = type("S", (), {})()
    sprite.center_x = 100.0
    sprite.center_y = 0.0
    sprite.mesh_entity_data = {"id": "x"}
    sprite.mesh_behaviours_runtime = [_Behaviour()]

    assert pick_interactable([sprite], player_pos=(0.0, 0.0), max_dist=10.0) is None


def test_pick_interactable_player_pos_legacy_does_not_require_actor_eligibility() -> None:
    from engine.interaction import pick_interactable, select_interaction_candidate

    class _PlayerOnlyBehaviour:
        def can_interact_with(self, actor) -> bool:
            return getattr(actor, "mesh_tag", None) == "player"

        def on_interact(self, _window, _actor) -> None:
            return

    def _sprite(entity_id: str, x: float, *, gated: bool = False):
        sprite = type("S", (), {})()
        sprite.center_x = x
        sprite.center_y = 0.0
        sprite.width = 16.0
        sprite.height = 16.0
        sprite.mesh_tag = "npc"
        sprite.mesh_entity_data = {"id": entity_id}
        if gated:
            sprite.mesh_entity_data["require_flags"] = ["flag.enabled"]
        sprite.mesh_behaviours_runtime = [_PlayerOnlyBehaviour()]
        return sprite

    target_b = _sprite("b", 10.0)
    target_a = _sprite("a", 10.0)
    gated = _sprite("gated", 1.0, gated=True)

    def get_flag(_name: str, default: bool = False) -> bool:
        return default

    assert (
        pick_interactable(
            [target_b, target_a, gated],
            player_pos=(0.0, 0.0),
            max_dist=20.0,
            get_flag=get_flag,
        )
        is target_a
    )

    player = type("P", (), {})()
    player.center_x = 0.0
    player.center_y = 0.0
    player.width = 16.0
    player.height = 16.0
    player.mesh_tag = "player"
    player.mesh_entity_data = {"id": "player", "facing": "right"}
    player.mesh_behaviours_runtime = []
    assert select_interaction_candidate([target_b], actor=player) is not None

    npc = type("P", (), {})()
    npc.center_x = 0.0
    npc.center_y = 0.0
    npc.width = 16.0
    npc.height = 16.0
    npc.mesh_tag = "npc"
    npc.mesh_entity_data = {"id": "npc", "facing": "right"}
    npc.mesh_behaviours_runtime = []
    assert select_interaction_candidate([target_b], actor=npc) is None


def test_hidden_entities_cannot_be_interacted_with() -> None:
    from engine.interaction import pick_interactable

    class _Behaviour:
        def on_interact(self, _window, _actor) -> None:
            return

    def _sprite(entity_id: str, x: float):
        sprite = type("S", (), {})()
        sprite.center_x, sprite.center_y, sprite.width, sprite.height = x, 0.0, 16.0, 16.0
        sprite.mesh_entity_data = {"id": entity_id}
        sprite.mesh_behaviours_runtime = [_Behaviour()]
        return sprite

    player = _sprite("player", 0.0)
    player.mesh_behaviours_runtime = []
    taken_shovel = _sprite("shovel", 2.0)
    taken_shovel.visible = False  # what ConditionalActivator does once it's picked up
    grave = _sprite("grave", 10.0)
    assert pick_interactable([taken_shovel, grave], player_pos=(0.0, 0.0), max_dist=20.0, actor=player) is grave


def _picture_less(entity_id: str, x: float, window: object, *extra: object):
    """An object with no picture, as the scene loader makes one: never ``visible`` (Watchfire R2)."""

    class _Talk:  # (a conversation: Dialogue's on_interact)
        def __init__(self) -> None:
            self.window = window

        def on_interact(self, _window, _actor) -> None:
            return

    sprite = type("S", (), {})()
    sprite.center_x, sprite.center_y, sprite.width, sprite.height = x, 0.0, 16.0, 16.0
    sprite.visible = False
    sprite.mesh_entity_data = {"id": entity_id}
    sprite.mesh_behaviours_runtime = [_Talk(), *extra]
    return sprite


def test_a_campfire_without_a_picture_can_be_talked_to_but_logic_only_objects_cannot() -> None:
    from types import SimpleNamespace

    from engine import fire
    from engine.interaction import pick_interactable

    window = SimpleNamespace(campfires=[])
    player = _picture_less("player", 0.0, window)
    player.mesh_behaviours_runtime = []
    arrival_spot = _picture_less("arrival", 2.0, window)  # nearer, picture-less, but nothing the world draws
    watchfire = _picture_less("watchfire", 10.0, window)
    fire.register(window, watchfire, fire.parse_fire({}))

    assert pick_interactable([arrival_spot, watchfire], player_pos=(0.0, 0.0), max_dist=20.0, actor=player) is watchfire
    assert pick_interactable([arrival_spot], player_pos=(0.0, 0.0), max_dist=20.0, actor=player) is None


def test_a_campfire_its_show_when_flags_hide_cannot_be_talked_to() -> None:
    from types import SimpleNamespace

    from engine import fire
    from engine.interaction import pick_interactable

    class ConditionalActivator:  # (its "Show when" flags: water.active asks it, as the renderer does)
        def __init__(self, shown: bool) -> None:
            self.shown = shown

        def _requirements_met(self) -> bool:
            return self.shown

    window = SimpleNamespace(campfires=[])
    player = _picture_less("player", 0.0, window)
    player.mesh_behaviours_runtime = []
    cold_fire = _picture_less("cold", 10.0, window, ConditionalActivator(False))  # once lit: not there
    lit_fire = _picture_less("lit", 12.0, window, ConditionalActivator(True))
    unregistered = _picture_less("elsewhere", 5.0, window)  # (a campfire of another room: not this room's)
    for hearth in (cold_fire, lit_fire):
        fire.register(window, hearth, fire.parse_fire({}))

    assert pick_interactable([cold_fire, lit_fire, unregistered], player_pos=(0.0, 0.0), max_dist=20.0,
                             actor=player) is lit_fire
    assert pick_interactable([cold_fire], player_pos=(0.0, 0.0), max_dist=20.0, actor=player) is None
