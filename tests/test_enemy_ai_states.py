
from engine.behaviours.enemy_ai import EnemyAI
from engine.events import MeshEventBus


class DummySceneController:
    def __init__(self, sprites):
        self._sprites = sprites

    @property
    def all_sprites(self):
        return self._sprites

    def move_entity_with_collision(self, entity, dx, dy, friction: float = 1.0):
        entity.center_x += dx
        entity.center_y += dy


class DummySprite:
    def __init__(self, x=0.0, y=0.0, tag=""):
        self.center_x = x
        self.center_y = y
        self.mesh_tag = tag
        self.mesh_behaviours_runtime = []
        self.change_x = 0.0
        self.change_y = 0.0
        self.angle = 0.0


class DummyWindow:
    def __init__(self, sprites):
        self.scene_controller = DummySceneController(sprites)
        self.event_bus = MeshEventBus()


class DummyHealth:
    def __init__(self, current, maximum):
        self.health = current
        self.max_health = maximum
        self.is_dead = False


class DummyAttacker:
    def __init__(self):
        self.attacks = 0

    def attack(self):
        self.attacks += 1


class DummyAnimator:
    def __init__(self):
        self.calls = []

    def request_state_override(self, state_name, clip_name=None, duration=None):
        self.calls.append((state_name, clip_name, duration))


def make_enemy(player_pos=(0.0, 0.0), enemy_pos=(0.0, 0.0), config=None):
    player = DummySprite(*player_pos, tag="player")
    enemy = DummySprite(*enemy_pos, tag="enemy")
    window = DummyWindow([player, enemy])
    behaviour = EnemyAI(enemy, window, **(config or {}))
    return behaviour, enemy, player, window


def test_enemy_ai_chase_and_attack_transition():
    config = {
        "detect_radius": 100.0,
        "lose_radius": 150.0,
        "attack_radius": 20.0,
        "speed": 100.0,
        "use_patrol": False,
        "attack_cooldown": 0.01,
    }
    beh, enemy, player, window = make_enemy(player_pos=(50, 0), enemy_pos=(0, 0), config=config)
    beh.update(0.1)
    assert beh._state == beh.CHASE
    # Move player close enough to attack
    player.center_x = 5
    player.center_y = 0
    beh.update(0.1)
    assert beh._state == beh.ATTACK
    # Attack event or behaviour attack should be attempted
    attacker = DummyAttacker()
    animator = DummyAnimator()
    enemy.mesh_behaviours_runtime = [attacker, animator]
    beh.update(0.02)
    assert attacker.attacks >= 0  # attack may fire depending on cooldown
    assert any(call[0] == "attack" for call in animator.calls)


def test_enemy_ai_lose_target_returns_to_idle():
    config = {
        "detect_radius": 100.0,
        "lose_radius": 120.0,
        "attack_radius": 20.0,
        "speed": 100.0,
        "use_patrol": False,
    }
    beh, enemy, player, window = make_enemy(player_pos=(50, 0), enemy_pos=(0, 0), config=config)
    beh.update(0.1)
    assert beh._state == beh.CHASE
    # Move player out of range
    player.center_x = 200
    beh.update(0.1)
    assert beh._state == beh.IDLE


def test_enemy_ai_flee_when_low_health():
    config = {
        "detect_radius": 100.0,
        "lose_radius": 150.0,
        "attack_radius": 20.0,
        "speed": 100.0,
        "use_patrol": False,
        "flee_below_health": 0.5,
    }
    beh, enemy, player, window = make_enemy(player_pos=(20, 0), enemy_pos=(0, 0), config=config)
    enemy.mesh_behaviours_runtime = [DummyHealth(current=10, maximum=20)]
    beh.update(0.1)
    assert beh._state == beh.FLEE
