
from engine.behaviours.animator import SpriteAnimatorBehaviour


class StubAssets:
    def get_texture(self, path):
        return f"tex:{path}"


class StubWindow:
    def __init__(self):
        self.assets = StubAssets()


class StubEntity:
    def __init__(self):
        self.mesh_entity_data = {}
        self.change_x = 0.0
        self.change_y = 0.0
        self.texture = None
        self.mesh_behaviours_runtime = []


def test_directional_animator_auto_switch():
    window = StubWindow()
    entity = StubEntity()
    anim = SpriteAnimatorBehaviour(
        entity,
        window,
        animations={
            "idle_down": ["a"],
            "idle_up": ["b"],
            "walk_up": ["c"],
            "walk_down": ["d"],
        },
        animation_frame_rate=8.0,
        enable_auto_state=True,
        directional_mode="4-way",
        facing_default="down",
        idle_clip="idle_down",
        walk_clip="walk_down",
    )
    entity.mesh_behaviours_runtime = [anim]
    anim.set_facing("up")
    entity.change_y = 5.0
    anim.update(0.016)
    assert anim.current_state == "walk_up"
    entity.change_y = 0.0
    anim.update(0.016)
    assert anim.current_state == "idle_up"
