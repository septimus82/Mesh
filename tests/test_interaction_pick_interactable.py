from __future__ import annotations


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

