from __future__ import annotations

from unittest.mock import MagicMock

import engine.optional_arcade as optional_arcade

from engine.cutscene_controller import CutsceneController


class DialogueRunnerBehaviour:
    def __init__(self, dialogue_id: str) -> None:
        self.dialogue_id = dialogue_id
        self.started_with: str | None = None

    def start(self, node_id: str | None = None) -> bool:
        self.started_with = node_id
        return True


class _SceneController:
    def __init__(self, sprite) -> None:
        self._sprite = sprite
        self.all_sprites = [sprite]

    def find_sprite(self, identifier):
        name = str(identifier)
        if getattr(self._sprite, "mesh_name", None) == name:
            return self._sprite
        return None


def test_cutscene_start_dialogue_targets_dialogue_runner() -> None:
    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "mentor"
    runner = DialogueRunnerBehaviour("intro_dialogue")
    sprite.behaviours = [runner]

    window = MagicMock()
    window.scene_controller = _SceneController(sprite)
    window.ui_controller = None

    controller = CutsceneController(window)
    controller.register_cutscenes(
        [
            {
                "id": "intro",
                "steps": [
                    {
                        "type": "start_dialogue",
                        "dialogue_id": "intro_dialogue",
                        "target": "mentor",
                        "node_id": "start",
                    }
                ],
            }
        ]
    )

    assert controller.play_cutscene("intro") is True

    controller.update(0.01)

    assert runner.started_with == "start"