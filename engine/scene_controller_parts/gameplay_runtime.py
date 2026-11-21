from __future__ import annotations

from typing import Any


def move_entity_with_collision(self, sprite, dx: float, dy: float, friction: float = 1.0) -> None:
    import math

    import engine.scene_controller_core as scene_controller_module
    from engine.physics_model import fast_move_steps

    if not (math.isfinite(dx) and math.isfinite(dy)):  # a NaN/inf move would park the sprite at NaN for good
        return
    check = scene_controller_module.optional_arcade.arcade.check_for_collision_with_list
    # Cut a fast move into pieces no longer than half the sprite, so a thin wall can't be skipped.
    nx, ny = fast_move_steps(dx, sprite.width), fast_move_steps(dy, sprite.height)
    for _ in range(nx):
        sprite.center_x += dx / nx
        hit_list = check(sprite, self.solid_sprites)
        if hit_list:
            if dx > 0:
                sprite.right = min(wall.left for wall in hit_list)
            elif dx < 0:
                sprite.left = max(wall.right for wall in hit_list)
            break

    for _ in range(ny):
        sprite.center_y += dy / ny
        hit_list = check(sprite, self.solid_sprites)
        if hit_list:
            if dy > 0:
                sprite.top = min(wall.bottom for wall in hit_list)
            elif dy < 0:
                sprite.bottom = max(wall.top for wall in hit_list)
            break


def on_collectible_picked(self, collectible, collector) -> None:
    import engine.scene_controller_core as scene_controller_module

    payload = {
        "collectible_name": getattr(collectible, "mesh_name", "<unnamed>"),
        "collector": getattr(collector, "mesh_name", "<unnamed>"),
        "position": (float(collectible.center_x), float(collectible.center_y)),
    }
    self.window.emit_signal(scene_controller_module.EVENT_COLLECTIBLE_PICKED, **payload)
    self.window.console_log(
        f"Collected {payload['collectible_name']} by {payload['collector']}",
    )


def on_damage(self, source, target, amount: float, *, emit: bool = True) -> None:
    import engine.scene_controller_core as scene_controller_module

    payload = {
        "source": getattr(source, "mesh_name", "<unnamed>"),
        "target": getattr(target, "mesh_name", "<unnamed>"),
        "amount": float(amount),
    }
    scene_controller_module.request_animation_state(source, "attack", priority=20.0, ttl=0.25)
    scene_controller_module.request_animation_state(target, "hit", priority=40.0, ttl=0.45)
    if emit:  # (False when Health.apply_damage already published damage_applied)
        self.window.emit_signal(scene_controller_module.EVENT_DAMAGE_APPLIED, **payload)
    self.window.console_log(
        f"{payload['source']} dealt {payload['amount']:.1f} damage to {payload['target']}",
    )


def _coerce_optional_float(self, value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def bind_gameplay_runtime_methods(cls) -> None:
    cls.move_entity_with_collision = move_entity_with_collision
    cls.on_collectible_picked = on_collectible_picked
    cls.on_damage = on_damage
    cls._coerce_optional_float = _coerce_optional_float
