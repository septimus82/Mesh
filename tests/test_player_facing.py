from engine.behaviours.player_controller import PlayerController


class FakeAnimator:
    def __init__(self):
        self.facing = None

    def set_facing(self, facing: str):
        self.facing = facing


class FakeInput:
    def __init__(self, vx: float, vy: float):
        self.vx = vx
        self.vy = vy

    def get_axis(self, neg: str, pos: str) -> float:
        if "left" in pos or "right" in pos:
            return self.vx
        return self.vy

    def is_action_down(self, action: str) -> bool:
        return False


class FakeWindow:
    def __init__(self, vx: float, vy: float, animator):
        self.input = FakeInput(vx, vy)
        self._pressed = set()
        self._locked = False
        self.animator = animator

    def get_pressed_keys(self):
        return self._pressed

    def player_input_blocked(self):
        return False

    def is_input_locked(self):
        return False

    def move_entity_with_collision(self, entity, dx, dy, dt=0.0):
        entity.center_x += dx * dt
        entity.center_y += dy * dt


class FakeEntity:
    def __init__(self, animator):
        self.center_x = 0.0
        self.center_y = 0.0
        self.mesh_behaviours_runtime = [animator]
        self.mesh_entity_data = {}


def test_player_controller_sets_facing():
    animator = FakeAnimator()
    window = FakeWindow(0.0, 1.0, animator)  # moving up
    entity = FakeEntity(animator)
    ctrl = PlayerController(entity, window, speed=100.0)
    ctrl.update(0.1)
    assert animator.facing == "up"
    window.input.vx = -1.0
    window.input.vy = 0.0
    ctrl.update(0.1)
    assert animator.facing == "left"
