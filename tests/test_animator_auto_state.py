
from engine.behaviours.animator import SpriteAnimatorBehaviour


class DummyAssets:
    def get_texture(self, path):
        return object()

    def load_sprite_sheet(self, *args, **kwargs):
        return [object(), object()]


class DummyWindow:
    def __init__(self):
        self.assets = DummyAssets()


class DummySprite:
    def __init__(self):
        self.change_x = 0.0
        self.change_y = 0.0
        self.texture = None
        self.mesh_entity_data = {}


def make_animator(sprite, config):
    window = DummyWindow()
    return SpriteAnimatorBehaviour(sprite, window, **config)


def test_animator_auto_idle_walk_switching():
    sprite = DummySprite()
    config = {
        "animations": {
            "idle": ["a.png", "b.png"],
            "walk": ["c.png", "d.png"],
        },
        "enable_auto_state": True,
        "idle_clip": "idle",
        "walk_clip": "walk",
        "speed_threshold": 1.0,
    }
    animator = make_animator(sprite, config)
    animator.update(0.1)
    assert animator.current_state == "idle"
    sprite.change_x = 5.0
    animator.update(0.1)
    assert animator.current_state == "walk"


def test_animator_state_override_wins_temporarily():
    sprite = DummySprite()
    config = {
        "animations": {
            "idle": ["a.png", "b.png"],
            "walk": ["c.png", "d.png"],
            "attack": ["e.png", "f.png"],
        },
        "enable_auto_state": True,
        "idle_clip": "idle",
        "walk_clip": "walk",
        "speed_threshold": 1.0,
        "override_duration": 0.2,
    }
    animator = make_animator(sprite, config)
    sprite.change_x = 5.0
    animator.request_state_override("attack", "attack", 0.3)
    animator.update(0.1)
    assert animator.current_state == "attack"
    animator.update(0.1)
    assert animator.current_state == "attack"
    animator.update(0.2)
    assert animator.current_state == "walk"
