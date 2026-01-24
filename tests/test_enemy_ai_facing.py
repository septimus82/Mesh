from engine.behaviours.enemy_ai import EnemyAI


class FakeAnimator:
    def __init__(self):
        self.facing = None

    def set_facing(self, facing: str):
        self.facing = facing


class FakeSceneController:
    def __init__(self, sprites):
        self.all_sprites = sprites

    def move_entity_with_collision(self, entity, dx, dy):
        entity.center_x += dx
        entity.center_y += dy


class FakeWindow:
    def __init__(self, target, enemy, animator):
        self.scene_controller = FakeSceneController([target])
        enemy.mesh_behaviours_runtime = [animator]


class FakeSprite:
    def __init__(self, x=0.0, y=0.0):
        self.center_x = x
        self.center_y = y
        self.mesh_tag = "player"
        self.mesh_behaviours_runtime = []


def test_enemy_ai_sets_facing_towards_target():
    target = FakeSprite(10.0, 0.0)
    enemy = FakeSprite(0.0, 0.0)
    animator = FakeAnimator()
    window = FakeWindow(target, enemy, animator)
    ai = EnemyAI(enemy, window, detect_radius=100.0, attack_radius=1.0, use_patrol=False)
    ai.update(0.1)
    assert animator.facing == "right"
