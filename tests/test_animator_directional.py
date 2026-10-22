
import pytest

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


@pytest.mark.fast
def test_a_flipped_clip_mirrors_its_frames_so_right_facing_art_also_walks_left():
    class _Frame:
        def __init__(self, name):
            self.name = name

        def flip_left_right(self):
            return _Frame(f"mirrored {self.name}")

    class SheetAssets(StubAssets):
        def load_sprite_sheet(self, path, fw, fh, count, start):
            return [_Frame(f"{path}#{start + i}") for i in range(count)]

    window = StubWindow()
    window.assets = SheetAssets()
    walk_right = {"sheet": "hero.png", "frame_width": 32, "frame_height": 32, "start": 6, "frames": 3}
    anim = SpriteAnimatorBehaviour(StubEntity(), window, animations={
        "walk_right": walk_right, "walk_left": {**walk_right, "flip_x": True}})
    assert [f.name for f in anim.animations["walk_right"]] == ["hero.png#6", "hero.png#7", "hero.png#8"]
    assert [f.name for f in anim.animations["walk_left"]] == ["mirrored hero.png#6", "mirrored hero.png#7", "mirrored hero.png#8"]
