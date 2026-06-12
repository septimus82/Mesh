from __future__ import annotations

from typing import Any


def move_entity_with_collision(self, sprite, dx: float, dy: float, friction: float = 1.0) -> None:
    import engine.scene_controller_core as scene_controller_module

    sprite.center_x += dx
    hit_list = scene_controller_module.optional_arcade.arcade.check_for_collision_with_list(
        sprite,
        self.solid_sprites,
    )
    if hit_list:
        if dx > 0:
            min_left = min(wall.left for wall in hit_list)
            sprite.right = min_left
        elif dx < 0:
            max_right = max(wall.right for wall in hit_list)
            sprite.left = max_right

    sprite.center_y += dy
    hit_list = scene_controller_module.optional_arcade.arcade.check_for_collision_with_list(
        sprite,
        self.solid_sprites,
    )
    if hit_list:
        if dy > 0:
            min_bottom = min(wall.bottom for wall in hit_list)
            sprite.top = min_bottom
        elif dy < 0:
            max_top = max(wall.top for wall in hit_list)
            sprite.bottom = max_top


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


def on_damage(self, source, target, amount: float) -> None:
    import engine.scene_controller_core as scene_controller_module

    payload = {
        "source": getattr(source, "mesh_name", "<unnamed>"),
        "target": getattr(target, "mesh_name", "<unnamed>"),
        "amount": float(amount),
    }
    scene_controller_module.request_animation_state(source, "attack", priority=20.0, ttl=0.25)
    scene_controller_module.request_animation_state(target, "hit", priority=40.0, ttl=0.45)
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
