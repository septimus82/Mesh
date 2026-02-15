"""Entity-related console command handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.animation_state import get_animation_state_snapshot, request_animation_state
from engine.console_runtime.utils import (
    entity_health_summary,
    format_scalar,
    normalize_tag_value,
    parse_float,
)

if TYPE_CHECKING:
    import arcade

    SpriteType = arcade.Sprite
else:
    SpriteType = Any


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def resolve_entity_reference(
    controller: Any,
    ref: str,
    sprites: list[SpriteType] | None = None,
) -> tuple[SpriteType | None, int | None, list[SpriteType]]:
    """Resolve an entity reference (index or name) to a sprite."""
    if sprites is None:
        sprites = list(controller.window.scene_controller.all_sprites)
    if not sprites:
        return None, None, sprites

    sprite: SpriteType | None = None
    index: int | None = None

    try:
        idx = int(ref)
    except ValueError:
        idx = None

    if idx is not None and 0 <= idx < len(sprites):
        sprite = sprites[idx]
        index = idx
        return sprite, index, sprites

    lowered = ref.strip().lower()
    for idx, candidate in enumerate(sprites):
        name = getattr(candidate, "mesh_name", None)
        if isinstance(name, str) and name.strip().lower() == lowered:
            sprite = candidate
            index = idx
            break

    return sprite, index, sprites


def find_layer_name(controller: Any, target: SpriteType) -> str:
    """Return the layer name containing *target*, or ``'<unknown>'``."""
    for layer_name, sprite_list in controller.window.scene_controller.layers.items():
        if target in sprite_list:
            return str(layer_name)
    return "<unknown>"


# ---------------------------------------------------------------------------
# Dispatch-compatible handlers  (controller, args) -> bool
# ---------------------------------------------------------------------------

def handle_entity(controller: Any, args: list[str]) -> bool:
    """Top-level ``entity`` command."""
    if args and args[0].lower() == "set":
        _entity_set(controller, args[1:])
        return True

    if args and args[0].lower() == "beh":
        # delegate to behaviour handlers (imported lazily to avoid circular deps)
        from engine.console_runtime.handlers_behaviour import entity_beh_command
        entity_beh_command(controller, args[1:])
        return True

    if args and args[0].lower() == "anim":
        _entity_anim_command(controller, args[1:])
        return True

    sprites = list(controller.window.scene_controller.all_sprites)
    if not sprites:
        controller.log("No entities loaded")
        return True

    if not args:
        controller.log("Entities:")
        for idx, sprite in enumerate(sprites):
            name = getattr(sprite, "mesh_name", None) or "<unnamed>"
            tag = getattr(sprite, "mesh_tag", None) or "<none>"
            layer = find_layer_name(controller, sprite)
            controller.log(f"  [{idx}] {name} (layer={layer}, tag={tag})")
        return True

    target = args[0]
    sprite, index, _ = resolve_entity_reference(controller, target, sprites)

    if sprite is None or index is None:
        controller.log(f"No entity found for '{target}'")
        return True

    name = getattr(sprite, "mesh_name", None) or "<unnamed>"
    tag = getattr(sprite, "mesh_tag", None) or "<none>"
    layer = find_layer_name(controller, sprite)
    solid = bool(getattr(sprite, "mesh_is_solid", False))
    asset = getattr(sprite, "mesh_entity_data", {}).get("sprite", "<unknown>")
    declared_behaviours = list(getattr(sprite, "mesh_behaviours", []))
    runtime_behaviours = list(getattr(sprite, "mesh_behaviours_runtime", []))

    controller.log(f"Entity [{index}] {name}")
    controller.log(f"  tag: {tag}")
    controller.log(f"  position: ({sprite.center_x:.1f}, {sprite.center_y:.1f})")
    rotation_text = format_scalar(getattr(sprite, "angle", 0.0))
    scale_text = format_scalar(getattr(sprite, "scale", 1.0))
    controller.log(f"  rotation: {rotation_text}°, scale: {scale_text}")
    controller.log(f"  layer: {layer}, solid: {'yes' if solid else 'no'}")
    controller.log(f"  texture: {asset}")

    if declared_behaviours:
        controller.log(f"  behaviours (declared): {', '.join(declared_behaviours)}")
    else:
        controller.log("  behaviours (declared): <none>")

    if runtime_behaviours:
        runtime_names = ", ".join(
            behaviour.__class__.__name__ for behaviour in runtime_behaviours
        )
        controller.log(f"  behaviours (runtime): {runtime_names}")
    else:
        controller.log("  behaviours (runtime): <none>")

    health_line = entity_health_summary(runtime_behaviours)
    if health_line:
        controller.log(f"  health: {health_line}")

    return True


def handle_spawn(controller: Any, args: list[str]) -> bool:
    """``spawn <sprite_path> <x> <y>``"""
    if len(args) < 3:
        controller.log("Usage: spawn <sprite_path> <x> <y>")
        return True
    sprite_path = args[0]
    x = parse_float(controller, args[1], "x")
    y = parse_float(controller, args[2], "y")
    if x is None or y is None:
        return True

    entity = {
        "sprite": sprite_path,
        "x": x,
        "y": y,
        "name": f"spawned_{len(list(controller.window.all_sprites))}",
        "layer": "entities",
    }
    sprite = controller.window.scene_controller._create_sprite(entity)
    if sprite:
        controller.window.scene_controller.layers["entities"].append(sprite)
        controller.log(f"Spawned {entity['name']} at ({x}, {y})")
    return True


def handle_spawn_like(controller: Any, args: list[str]) -> bool:
    """``spawn_like <ref> <x> <y>``"""
    if len(args) < 3:
        controller.log("Usage: spawn_like <ref> <x> <y>")
        return True
    ref = args[0]
    x = parse_float(controller, args[1], "x")
    y = parse_float(controller, args[2], "y")
    if x is None or y is None:
        return True

    sprite, _, _ = resolve_entity_reference(controller, ref)
    if not sprite:
        controller.log(f"Entity '{ref}' not found")
        return True

    entity_data = getattr(sprite, "mesh_entity_data", {})
    new_entity = dict(entity_data)
    new_entity["x"] = x
    new_entity["y"] = y
    new_entity["name"] = f"{new_entity.get('name', 'entity')}_clone"

    new_sprite = controller.window.scene_controller._create_sprite(new_entity)
    if new_sprite:
        layer_name = find_layer_name(controller, sprite)
        if layer_name in controller.window.scene_controller.layers:
            controller.window.scene_controller.layers[layer_name].append(new_sprite)
        else:
            controller.window.scene_controller.layers["entities"].append(new_sprite)
        controller.log(f"Spawned clone at ({x}, {y})")
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _entity_set(controller: Any, args: list[str]) -> None:
    if len(args) < 3:
        controller.log("Usage: entity set <index|name> <field> <value>")
        return

    target = args[0]
    field = args[1].lower()
    values = args[2:]

    sprite, index, _ = resolve_entity_reference(controller, target)
    if sprite is None or index is None:
        controller.log(f"No entity found for '{target}'")
        return

    if field == "x":
        x_value = parse_float(controller, values[0], "x")
        if x_value is None:
            return
        controller.window.scene_controller._apply_entity_mutation(sprite, x=x_value)
        controller.log(f"Entity [{index}] x set to {x_value:.1f}")
        return

    if field == "y":
        y_value = parse_float(controller, values[0], "y")
        if y_value is None:
            return
        controller.window.scene_controller._apply_entity_mutation(sprite, y=y_value)
        controller.log(f"Entity [{index}] y set to {y_value:.1f}")
        return

    if field == "pos":
        if len(values) < 2:
            controller.log("Usage: entity set <ref> pos <x> <y>")
            return
        x_value = parse_float(controller, values[0], "x")
        y_value = parse_float(controller, values[1], "y")
        if x_value is None or y_value is None:
            return
        controller.window.scene_controller._apply_entity_mutation(sprite, x=x_value, y=y_value)
        controller.log(f"Entity [{index}] position set to ({x_value:.1f}, {y_value:.1f})")
        return

    if field == "tag":
        tag_value = normalize_tag_value(values[0])
        controller.window.scene_controller._apply_entity_mutation(sprite, tag=tag_value)
        display = tag_value if tag_value is not None else "<none>"
        controller.log(f"Entity [{index}] tag set to {display}")
        return

    if field == "scale":
        scale_value = parse_float(controller, values[0], "scale")
        if scale_value is None:
            return
        controller.window.scene_controller._apply_entity_mutation(sprite, scale=scale_value)
        controller.log(f"Entity [{index}] scale set to {scale_value:.3f}")
        return

    controller.log("Unknown entity field. Supported fields: x, y, pos, tag, scale")


def _entity_anim_command(controller: Any, args: list[str]) -> None:
    usage = (
        "Usage: entity anim list <ref> | entity anim set <ref> <state> | "
        "entity anim state <ref> | entity anim pulse <ref> <state> [priority] [ttl]"
    )
    if not args:
        controller.log(usage)
        return

    action = args[0].lower()
    if action == "list":
        if len(args) < 2:
            controller.log("Usage: entity anim list <ref>")
            return
        sprite, index, _ = resolve_entity_reference(controller, args[1])
        if sprite is None or index is None:
            controller.log(f"No entity found for '{args[1]}'")
            return
        animator = getattr(sprite, "mesh_animator", None)
        if animator is None:
            controller.log(f"Entity [{index}] has no animator")
            return
        name = getattr(sprite, "mesh_name", "<unnamed>")
        controller.log(f"Animator states for entity [{index}] {name}:")
        enumerator = getattr(animator, "available_states", None)
        states = enumerator() if callable(enumerator) else []
        current = getattr(animator, "current_state", "<unknown>")
        if not states:
            controller.log("  <no states>")
        else:
            for state in states:
                marker = "*" if state == current else "-"
                controller.log(f"  {marker} {state}")
        return

    if action == "state":
        if len(args) < 2:
            controller.log("Usage: entity anim state <ref>")
            return
        sprite, index, _ = resolve_entity_reference(controller, args[1])
        if sprite is None or index is None:
            controller.log(f"No entity found for '{args[1]}'")
            return
        snapshot = get_animation_state_snapshot(sprite)
        animator = getattr(sprite, "mesh_animator", None)
        clip_state = getattr(animator, "current_state", None) if animator else None
        clip_info = "<none>"
        clip_obj = None
        if animator and clip_state:
            clip = getattr(animator, "clips", {}).get(clip_state)
            clip_obj = clip
            if clip is not None:
                clip_info = (
                    f"{clip_state} ({len(clip.frames)}f @ {clip.fps:.1f}fps, "
                    f"loop={'yes' if clip.loop else 'no'}"
                )
            else:
                clip_info = clip_state
        controller.log(f"Entity [{index}] animation debug:")
        movement = snapshot.get("movement_state") or "<unset>"
        requested = snapshot.get("animation_state") or "<unset>"
        default = snapshot.get("default_animation") or "<unset>"
        priority = float(snapshot.get("priority", 0.0))
        timer = float(snapshot.get("timer", 0.0))
        override_active = "active" if snapshot.get("override_active") else "inactive"
        controller.log(f"  movement_state: {movement}")
        controller.log(f"  animation_state: {requested} (default: {default})")
        controller.log(f"  animator clip: {clip_info}")
        controller.log(
            f"  override: priority={priority:.2f} timer={timer:.2f}s [{override_active}]"
        )
        if animator is not None:
            blend_duration = float(getattr(animator, "_blend_duration", 0.0))
            blend_elapsed = float(getattr(animator, "_blend_elapsed", 0.0))
            blend_active = bool(getattr(animator, "_blend_from_texture", None))
            default_blend = float(getattr(animator, "default_blend", 0.0))
            if blend_active or default_blend > 0.0:
                if blend_active and blend_duration > 0.0:
                    controller.log(
                        f"  blend: {blend_elapsed:.2f}/{blend_duration:.2f}s (default {default_blend:.2f}s)"
                    )
                else:
                    controller.log(f"  blend: default {default_blend:.2f}s (inactive)")
            if clip_obj is not None and getattr(clip_obj, "events", None):
                events = getattr(clip_obj, "events", ())
                labels = ", ".join(marker.label for marker in events)
                controller.log(f"  events: {labels}")
        return

    if action == "pulse":
        if len(args) < 3:
            controller.log("Usage: entity anim pulse <ref> <state> [priority] [ttl]")
            return
        sprite, index, _ = resolve_entity_reference(controller, args[1])
        if sprite is None or index is None:
            controller.log(f"No entity found for '{args[1]}'")
            return
        state = args[2]
        priority = 0.0
        ttl = 0.0
        if len(args) >= 4:
            parsed = parse_float(controller, args[3], "priority")
            if parsed is None:
                return
            priority = float(parsed)
        if len(args) >= 5:
            parsed_ttl = parse_float(controller, args[4], "ttl")
            if parsed_ttl is None:
                return
            ttl = float(parsed_ttl)
        accepted = request_animation_state(sprite, state, priority=priority, ttl=ttl)
        if accepted:
            controller.log(
                f"Requested animation '{state}' on entity [{index}] (priority={priority:.2f}, ttl={ttl:.2f})"
            )
        else:
            controller.log(
                "Animation request ignored: another state holds a higher priority override"
            )
        return

    if action == "set":
        if len(args) < 3:
            controller.log("Usage: entity anim set <ref> <state>")
            return
        sprite, index, _ = resolve_entity_reference(controller, args[1])
        if sprite is None or index is None:
            controller.log(f"No entity found for '{args[1]}'")
            return
        animator = getattr(sprite, "mesh_animator", None)
        if animator is None:
            controller.log(f"Entity [{index}] has no animator")
            return
        setter = getattr(animator, "set_state", None)
        if callable(setter) and setter(args[2], force=True):
            current = getattr(animator, "current_state", args[2])
            controller.log(f"Entity [{index}] animation set to '{current}'")
        else:
            controller.log(f"Animator has no state '{args[2]}'")
        return

    controller.log("Unknown entity anim command. Use 'list' or 'set'.")
