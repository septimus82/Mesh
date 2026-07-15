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
