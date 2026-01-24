from __future__ import annotations

from dataclasses import dataclass

from engine.behaviours.auto_animation_by_movement import AutoAnimationByMovement


@dataclass
class DummyAnimator:
    states: set[str]
    current_state: str
    calls: list[str]

    def available_states(self):
        return sorted(self.states)

    def set_state(self, name: str):
        self.calls.append(str(name))
        self.current_state = str(name)
        return True


class DummyWindow:
    pass


class DummySprite:
    def __init__(self):
        self.center_x = 0.0
        self.center_y = 0.0
        self.change_x = 0.0
        self.change_y = 0.0
        self.mesh_entity_data = {"animations": {"idle": {"frames": [0]}, "walk": {"frames": [1]}}}
        self.mesh_animator = DummyAnimator(states={"idle", "walk"}, current_state="walk", calls=[])


def test_auto_animation_by_movement_switches_idle_walk_without_thrashing():
    sprite = DummySprite()
    behaviour = AutoAnimationByMovement(sprite, DummyWindow())

    sprite.change_x = 0.0
    sprite.change_y = 0.0
    behaviour.late_update(0.1)
    assert sprite.mesh_animator.current_state == "idle"
    assert sprite.mesh_animator.calls == ["idle"]

    behaviour.late_update(0.1)
    assert sprite.mesh_animator.calls == ["idle"]

    sprite.change_x = 1.0
    sprite.change_y = 0.0
    behaviour.late_update(0.1)
    assert sprite.mesh_animator.current_state == "walk"
    assert sprite.mesh_animator.calls == ["idle", "walk"]

    behaviour.late_update(0.1)
    assert sprite.mesh_animator.calls == ["idle", "walk"]

    sprite.change_x = 0.0
    sprite.change_y = 0.0
    behaviour.late_update(0.1)
    assert sprite.mesh_animator.current_state == "idle"
    assert sprite.mesh_animator.calls == ["idle", "walk", "idle"]

