from __future__ import annotations

from typing import Any


def move_entity_with_collision(self, sprite, dx: float, dy: float, friction: float = 1.0) -> None:
    import math

    import engine.scene_controller_core as scene_controller_module
    from engine.physics_model import Aabb, axis_stop, fast_move_steps, keep_inside
    from engine.physics_runtime import room_bounds

    if not (math.isfinite(dx) and math.isfinite(dy)):  # a NaN/inf move would park the sprite at NaN for good
        return
    check = scene_controller_module.optional_arcade.arcade.check_for_collision_with_list

    def box(s: Any) -> Aabb:
        return Aabb((s.left + s.right) / 2, (s.bottom + s.top) / 2, s.right - s.left, s.top - s.bottom)

    # Cut a fast move into pieces no longer than half the sprite, so a thin wall can't be skipped. A wall the
    # sprite is already in blocks only going deeper (engine.physics_model.axis_stop), as for the player.
    nx, ny = fast_move_steps(dx, sprite.width), fast_move_steps(dy, sprite.height)
    for _ in range(nx):
        before = box(sprite)
        sprite.center_x += dx / nx
        hit_list = check(sprite, self.solid_sprites)
        stop = axis_stop(before, dx, [box(w) for w in hit_list], 0) if hit_list else None
        if stop is not None:
            sprite.center_x += stop - box(sprite).x
            break

    for _ in range(ny):
        before = box(sprite)
        sprite.center_y += dy / ny
        hit_list = check(sprite, self.solid_sprites)
        stop = axis_stop(before, dy, [box(w) for w in hit_list], 1) if hit_list else None
        if stop is not None:
            sprite.center_y += stop - box(sprite).y
            break

    # A 2D room's edges stop it as walls do (the player's too: engine.physics_runtime.room_bounds).
    after = box(sprite)
    kept = keep_inside(after, (dx, dy), room_bounds(getattr(self, "window", None)))
    if kept != (after.x, after.y):
        sprite.center_x += kept[0] - after.x
        sprite.center_y += kept[1] - after.y


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
