import engine.optional_arcade as optional_arcade
from engine.behaviours.hitbox import Hitbox
from engine.behaviours.projectile import Projectile
from engine.behaviours.scene_transition import SceneTransition


class StubSceneController:
    def __init__(self, sprites):
        self.all_sprites = sprites


class StubWindow:
    def __init__(self, sprites):
        self.scene_controller = StubSceneController(sprites)


class Sprite(optional_arcade.arcade.Sprite):
    def __init__(self, tag: str):
        super().__init__()
        self.mesh_tag = tag
        self.mesh_behaviours_runtime = []


def test_hitbox_passes_spritelist_to_arcade(monkeypatch):
    hitbox_sprite = Sprite("hitbox")
    target = Sprite("enemy")
    window = StubWindow([hitbox_sprite, target])
    behaviour = Hitbox(hitbox_sprite, window, target_tag="enemy")

    def _check(_a, sprite_list):
        assert isinstance(sprite_list, optional_arcade.arcade.SpriteList)
        return []

    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision_with_list", _check)
    behaviour.update(0.01)


def test_projectile_passes_spritelist_to_arcade(monkeypatch):
    proj_sprite = Sprite("projectile")
    proj_sprite.center_x = 0
    proj_sprite.center_y = 0
    target = Sprite("player")
    window = StubWindow([proj_sprite, target])
    behaviour = Projectile(proj_sprite, window, target_tag="player", lifetime=1.0, speed=0.0)

    def _check(_a, sprite_list):
        assert isinstance(sprite_list, optional_arcade.arcade.SpriteList)
        return []

    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision_with_list", _check)
    behaviour.update(0.01)


def test_scene_transition_passes_spritelist_to_arcade(monkeypatch):
    door = Sprite("door")
    player = Sprite("player")
    window = StubWindow([door, player])
    behaviour = SceneTransition(door, window, target_scene="scenes/any.json", trigger_on_touch=True)

    def _check(_a, sprite_list):
        assert isinstance(sprite_list, optional_arcade.arcade.SpriteList)
        return []

    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision_with_list", _check)
    behaviour.update(0.01)

