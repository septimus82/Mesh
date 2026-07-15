from __future__ import annotations

import arcade


def test_interact_key_triggers_nearest_dialogue_entity() -> None:
    from engine.behaviours.player_controller import PlayerController
    from engine.input import InputManager
    from engine.input_runtime import capture as input_capture

    calls: list[str] = []

    class _DialogueBehaviour:
        def __init__(self, label: str) -> None:
            self.label = label

        def on_interact(self, _window, _actor) -> None:
            calls.append(self.label)

    class _Sprite:
        def __init__(self, *, entity_id: str, x: float, y: float, behaviours) -> None:
            self.center_x = float(x)
            self.center_y = float(y)
            self.mesh_entity_data = {"id": entity_id, "prefab_id": "npc"}
            self.mesh_behaviours_runtime = list(behaviours)
            self.mesh_tag = "npc"
            self.mesh_name = entity_id

    player = _Sprite(entity_id="player", x=0, y=0, behaviours=[])
    player.mesh_tag = "player"

    npc_near = _Sprite(entity_id="npc_a", x=10, y=0, behaviours=[_DialogueBehaviour("near")])
    npc_far = _Sprite(entity_id="npc_b", x=20, y=0, behaviours=[_DialogueBehaviour("far")])

    class _Scene:
        current_scene_path = "scenes/test.json"

        def _find_player_sprite(self):
            return player

    class _Console:
        active = False

    class _UI:
        input_blocked = False

        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    class _Editor:
        active = False

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        editor_controller = _Editor()
        show_debug = False
        scene_controller = _Scene()
        input = None

        @property
        def all_sprites(self):
            return iter([player, npc_near, npc_far])

        def is_input_locked(self) -> bool:
            return False

        def player_input_blocked(self) -> bool:
            return False

        def dialogue_blocks_input(self) -> bool:
            return False

    window = _Window()
    manager = InputManager()
    manager.bind("interact", arcade.key.E)
    window.input = manager
    window.move_entity_with_collision = lambda entity, dx, dy, dt=0.0: None
    controller = type(
        "C",
        (),
        {
            "window": window,
            "manager": manager,
            "_keys": set(),
            "is_input_locked": lambda self: False,
        },
    )()

    player_controller = PlayerController(player, window, speed=0.0)

    assert input_capture.handle_key_press(controller, arcade.key.E, 0) is False
    manager.update(0.016)
    player_controller.update(0.016)
    assert calls == ["near"]
