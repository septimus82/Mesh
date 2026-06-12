"""
Headless Render Plan Model - GPU-independent render regression testing.

This module provides dataclasses that capture the logical render plan
without any GPU or Arcade dependencies. These can be used for:
- Golden tests verifying stable draw ordering
- Determinism verification across runs
- Render queue regression testing

Design Principles:
1. Headless: No GPU/Arcade dependencies
2. Deterministic: Identical inputs produce identical plans
3. Comparable: Easy to diff and serialize
4. Testable: All fields are simple types (no object references)
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class BlendMode(str, Enum):
    """Standard blend modes for rendering."""
    NORMAL = "normal"
    ADDITIVE = "additive"
    MULTIPLY = "multiply"


class DrawCallType(str, Enum):
    """Types of draw calls in a render plan."""
    BACKGROUND = "background"
    SHADOW = "shadow"
    SPRITE = "sprite"
    OUTLINE = "outline"
    TILEMAP = "tilemap"
    LIGHT = "light"
    OCCLUDER = "occluder"


@dataclass(frozen=True, slots=True)
class Transform:
    """2D transform for a draw call.
    
    All transforms are in world-space coordinates.
    """
    x: float
    y: float
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0  # Degrees

    def is_valid(self) -> bool:
        """Check if all values are finite (no NaN/Inf)."""
        return (
            math.isfinite(self.x)
            and math.isfinite(self.y)
            and math.isfinite(self.scale_x)
            and math.isfinite(self.scale_y)
            and math.isfinite(self.rotation)
        )

    def to_tuple(self) -> tuple[float, float, float, float, float]:
        """Convert to tuple for hashing/comparison."""
        return (self.x, self.y, self.scale_x, self.scale_y, self.rotation)


@dataclass(frozen=True, slots=True)
class Color:
    """RGBA color with 0-255 components."""
    r: int = 255
    g: int = 255
    b: int = 255
    a: int = 255

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.r, self.g, self.b, self.a)

    @classmethod
    def from_tuple(cls, t: tuple[int, ...] | None) -> "Color":
        if t is None:
            return cls()
        if len(t) >= 4:
            return cls(r=int(t[0]), g=int(t[1]), b=int(t[2]), a=int(t[3]))
        if len(t) >= 3:
            return cls(r=int(t[0]), g=int(t[1]), b=int(t[2]))
        return cls()


@dataclass(frozen=True, slots=True)
class DrawCall:
    """A single headless draw call in the render plan.
    
    This captures all information needed to verify render ordering
    without actually performing any GPU operations.
    
    Fields:
        call_type: Type of draw call (sprite, shadow, background, etc.)
        layer: Render layer index (lower = drawn first)
        depth_z: Z-depth within layer (for sorting)
        texture_id: Texture identifier (path or "missing" if unresolved)
        shader_id: Shader identifier (or None for default)
        transform: Position, scale, rotation
        color: RGBA tint/color
        blend_mode: Blending mode
        entity_id: Optional entity identifier for debugging
        order_hint: Tie-breaker for stable sorting
    """
    call_type: DrawCallType
    layer: int
    depth_z: float
    texture_id: str
    transform: Transform
    color: Color = field(default_factory=Color)
    blend_mode: BlendMode = BlendMode.NORMAL
    shader_id: str | None = None
    entity_id: str | None = None
    order_hint: str = ""

    def sort_key(self) -> tuple[int, float, str, str]:
        """Key for stable sorting within a render plan."""
        return (self.layer, self.depth_z, self.call_type.value, self.order_hint)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dict."""
        return {
            "call_type": self.call_type.value,
            "layer": self.layer,
            "depth_z": round(self.depth_z, 6),
            "texture_id": self.texture_id,
            "shader_id": self.shader_id,
            "transform": {
                "x": round(self.transform.x, 6),
                "y": round(self.transform.y, 6),
                "scale_x": round(self.transform.scale_x, 6),
                "scale_y": round(self.transform.scale_y, 6),
                "rotation": round(self.transform.rotation, 6),
            },
            "color": list(self.color.to_tuple()),
            "blend_mode": self.blend_mode.value,
            "entity_id": self.entity_id,
            "order_hint": self.order_hint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DrawCall":
        """Deserialize from dict."""
        transform_data = data.get("transform", {})
        color_data = data.get("color", [255, 255, 255, 255])

        return cls(
            call_type=DrawCallType(data.get("call_type", "sprite")),
            layer=int(data.get("layer", 0)),
            depth_z=float(data.get("depth_z", 0.0)),
            texture_id=str(data.get("texture_id", "missing")),
            shader_id=data.get("shader_id"),
            transform=Transform(
                x=float(transform_data.get("x", 0.0)),
                y=float(transform_data.get("y", 0.0)),
                scale_x=float(transform_data.get("scale_x", 1.0)),
                scale_y=float(transform_data.get("scale_y", 1.0)),
                rotation=float(transform_data.get("rotation", 0.0)),
            ),
            color=Color.from_tuple(tuple(color_data) if color_data else None),
            blend_mode=BlendMode(data.get("blend_mode", "normal")),
            entity_id=data.get("entity_id"),
            order_hint=str(data.get("order_hint", "")),
        )


@dataclass
class RenderPlan:
    """An ordered sequence of draw calls representing a frame's render plan.
    
    The plan is computed from scene state and can be:
    - Compared against golden fixtures for regression testing
    - Validated for invariants (no NaNs, monotonic depth, etc.)
    - Serialized for debugging/inspection
    """
    calls: tuple[DrawCall, ...]
    frame: int = 0
    scene_id: str = ""

    def __len__(self) -> int:
        return len(self.calls)

    def __iter__(self):
        return iter(self.calls)

    def __getitem__(self, index: int) -> DrawCall:
        return self.calls[index]

    def digest(self) -> str:
        """Compute SHA-256 digest of the plan for quick comparison."""
        data = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dict."""
        return {
            "frame": self.frame,
            "scene_id": self.scene_id,
            "call_count": len(self.calls),
            "calls": [c.to_dict() for c in self.calls],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderPlan":
        """Deserialize from dict."""
        calls_data = data.get("calls", [])
        return cls(
            calls=tuple(DrawCall.from_dict(c) for c in calls_data),
            frame=int(data.get("frame", 0)),
            scene_id=str(data.get("scene_id", "")),
        )

    def by_layer(self) -> dict[int, list[DrawCall]]:
        """Group calls by layer."""
        result: dict[int, list[DrawCall]] = {}
        for call in self.calls:
            if call.layer not in result:
                result[call.layer] = []
            result[call.layer].append(call)
        return result

    def by_type(self) -> dict[DrawCallType, list[DrawCall]]:
        """Group calls by type."""
        result: dict[DrawCallType, list[DrawCall]] = {}
        for call in self.calls:
            if call.call_type not in result:
                result[call.call_type] = []
            result[call.call_type].append(call)
        return result

    def filter_type(self, call_type: DrawCallType) -> "RenderPlan":
        """Return new plan with only calls of given type."""
        return RenderPlan(
            calls=tuple(c for c in self.calls if c.call_type == call_type),
            frame=self.frame,
            scene_id=self.scene_id,
        )

    def filter_layer(self, layer: int) -> "RenderPlan":
        """Return new plan with only calls in given layer."""
        return RenderPlan(
            calls=tuple(c for c in self.calls if c.layer == layer),
            frame=self.frame,
            scene_id=self.scene_id,
        )


# =============================================================================
# Invariant Validation
# =============================================================================

@dataclass
class RenderPlanValidationResult:
    """Result of validating a render plan."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_render_plan(plan: RenderPlan) -> RenderPlanValidationResult:
    """Validate render plan invariants.
    
    Checks:
    1. No NaN/Inf values in transforms
    2. Depth order is monotonic within each layer
    3. Texture IDs are resolved (not "missing" unless explicitly marked)
    4. Layer indices are reasonable
    
    Returns:
        RenderPlanValidationResult with errors and warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check for NaN/Inf in transforms
    for i, call in enumerate(plan.calls):
        if not call.transform.is_valid():
            errors.append(
                f"Call {i} ({call.entity_id or 'unknown'}): "
                f"Invalid transform values (NaN/Inf)"
            )

    # Check monotonic depth within layers
    by_layer = plan.by_layer()
    for layer_idx, layer_calls in sorted(by_layer.items()):
        depths = [c.depth_z for c in layer_calls]
        for i in range(1, len(depths)):
            if depths[i] < depths[i - 1]:
                warnings.append(
                    f"Layer {layer_idx}: Non-monotonic depth at index {i} "
                    f"({depths[i - 1]} -> {depths[i]})"
                )

    # Check texture resolution
    for i, call in enumerate(plan.calls):
        if call.texture_id == "missing":
            warnings.append(
                f"Call {i} ({call.entity_id or 'unknown'}): "
                f"Unresolved texture (marked as 'missing')"
            )
        elif call.texture_id == "":
            errors.append(
                f"Call {i} ({call.entity_id or 'unknown'}): "
                f"Empty texture ID"
            )

    # Check layer indices
    for i, call in enumerate(plan.calls):
        if call.layer < -1000 or call.layer > 1000:
            warnings.append(
                f"Call {i} ({call.entity_id or 'unknown'}): "
                f"Unusual layer index {call.layer}"
            )

    return RenderPlanValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def assert_render_plan_valid(plan: RenderPlan) -> None:
    """Assert that a render plan passes validation.
    
    Raises:
        AssertionError: If validation fails with errors
    """
    result = validate_render_plan(plan)
    if not result.valid:
        error_msg = "Render plan validation failed:\n"
        error_msg += "\n".join(f"  - {e}" for e in result.errors)
        raise AssertionError(error_msg)


# =============================================================================
# Plan Building from Scene State
# =============================================================================

def build_render_plan_from_draw_plan(
    draw_plan: Any,
    scene_id: str = "",
    frame: int = 0,
) -> RenderPlan:
    """Build a headless RenderPlan from scene_render_pipeline.DrawPlan.
    
    This extracts the key ordering/transform information without
    any GPU dependencies.
    
    Args:
        draw_plan: A DrawPlan from scene_render_pipeline
        scene_id: Identifier for the scene
        frame: Frame number
        
    Returns:
        RenderPlan suitable for golden testing
    """
    calls: list[DrawCall] = []

    # Background operations
    bg_ops = getattr(draw_plan, "background_ops", []) or []
    for i, bg_op in enumerate(bg_ops):
        plane = getattr(bg_op, "plane", None)
        asset_path = getattr(plane, "asset_path", "unknown") if plane else "unknown"
        # Use render_layer for layer ordering, not z (BackgroundPlane has render_layer)
        plane_render_layer = getattr(plane, "render_layer", 0) if plane else 0
        parallax = getattr(plane, "parallax", 1.0) if plane else 1.0

        calls.append(DrawCall(
            call_type=DrawCallType.BACKGROUND,
            layer=-1000 + plane_render_layer,  # Backgrounds are always behind everything
            depth_z=float(plane_render_layer),  # Use render_layer as depth
            texture_id=str(asset_path) if asset_path else "missing",
            transform=Transform(
                x=float(getattr(bg_op, "base_x", 0.0)),
                y=float(getattr(bg_op, "base_y", 0.0)),
            ),
            color=Color(a=int(getattr(bg_op, "alpha", 255))),
            entity_id=f"bg_{i}",
            order_hint=f"parallax_{parallax:.2f}",
        ))

    # Shadow operations
    shadow_ops = getattr(draw_plan, "shadow_ops", []) or []
    for i, sh_op in enumerate(shadow_ops):
        color_tuple = getattr(sh_op, "color", (0, 0, 0, 128))
        calls.append(DrawCall(
            call_type=DrawCallType.SHADOW,
            layer=-1,  # Shadows are typically below sprites
            depth_z=float(getattr(sh_op, "cy", 0.0)),
            texture_id="shadow_ellipse",
            transform=Transform(
                x=float(getattr(sh_op, "cx", 0.0)),
                y=float(getattr(sh_op, "cy", 0.0)),
                scale_x=float(getattr(sh_op, "width", 1.0)),
                scale_y=float(getattr(sh_op, "height", 1.0)),
            ),
            color=Color.from_tuple(color_tuple),
            entity_id=f"shadow_{i}",
            order_hint=str(i),
        ))

    # Sprite operations
    sprite_ops = getattr(draw_plan, "sprite_ops", []) or []
    for i, sp_op in enumerate(sprite_ops):
        sprite = getattr(sp_op, "sprite", None)
        if sprite is None:
            continue

        # Extract sprite properties
        entity_data = getattr(sprite, "mesh_entity_data", {}) or {}
        entity_id = entity_data.get("id") or getattr(sprite, "mesh_name", None) or f"sprite_{i}"

        render_layer = 0
        try:
            render_layer = int(entity_data.get("render_layer", 0))
        except (TypeError, ValueError):
            pass

        depth_z = 0.0
        try:
            depth_z = float(entity_data.get("depth_z", 0.0))
        except (TypeError, ValueError):
            pass

        # Texture ID
        texture_key = getattr(sprite, "mesh_texture_key", None)
        texture = getattr(sprite, "texture", None)
        if texture_key:
            texture_id = str(texture_key)
        elif texture:
            texture_id = getattr(texture, "name", None) or str(id(texture))
        else:
            texture_id = "missing"

        # Transform
        scale = getattr(sprite, "scale", 1.0)
        if isinstance(scale, tuple):
            scale_x = float(scale[0]) if scale else 1.0
            scale_y = float(scale[1]) if len(scale) > 1 else scale_x
        else:
            scale_x = scale_y = float(scale) if scale else 1.0

        transform = Transform(
            x=float(getattr(sprite, "center_x", 0.0)),
            y=float(getattr(sprite, "center_y", 0.0)),
            scale_x=scale_x,
            scale_y=scale_y,
            rotation=float(getattr(sprite, "angle", 0.0)),
        )

        # Color
        sprite_color = getattr(sprite, "color", (255, 255, 255, 255))
        tint = getattr(sp_op, "tint", None)
        if tint:
            color = Color.from_tuple(tint)
        elif sprite_color:
            color = Color.from_tuple(sprite_color)
        else:
            color = Color()

        # Add outline calls first (they go behind the sprite)
        outline_calls = getattr(sp_op, "outline_draw_calls", []) or []
        for j, outline in enumerate(outline_calls):
            calls.append(DrawCall(
                call_type=DrawCallType.OUTLINE,
                layer=render_layer,
                depth_z=depth_z - 0.001,  # Slightly behind sprite
                texture_id=texture_id,
                transform=Transform(
                    x=float(getattr(outline, "x", transform.x)),
                    y=float(getattr(outline, "y", transform.y)),
                    scale_x=scale_x,
                    scale_y=scale_y,
                    rotation=transform.rotation,
                ),
                color=Color.from_tuple(getattr(outline, "color", (0, 0, 0, 255))),
                entity_id=f"{entity_id}_outline_{j}",
                order_hint=f"{i:06d}_{j:03d}",
            ))

        # Main sprite call
        calls.append(DrawCall(
            call_type=DrawCallType.SPRITE,
            layer=render_layer,
            depth_z=depth_z,
            texture_id=texture_id,
            transform=transform,
            color=color,
            entity_id=str(entity_id),
            order_hint=f"{i:06d}",
        ))

    # Sort calls by layer, then depth, then type, then order_hint
    sorted_calls = sorted(calls, key=lambda c: c.sort_key())

    return RenderPlan(
        calls=tuple(sorted_calls),
        frame=frame,
        scene_id=scene_id,
    )


def build_render_plan_from_sprites(
    sprites: Sequence[Any],
    scene_id: str = "",
    frame: int = 0,
    sort_mode: str = "y_sort",
) -> RenderPlan:
    """Build a RenderPlan directly from a list of sprites.
    
    This is a simpler alternative when you don't have a full DrawPlan.
    
    Args:
        sprites: List of sprite objects
        scene_id: Scene identifier
        frame: Frame number
        sort_mode: Sorting mode ("y_sort", "explicit_z", etc.)
        
    Returns:
        RenderPlan
    """
    from engine.render_sort_model import compute_sprite_render_sort_key

    # Sort sprites
    sorted_sprites = sorted(
        sprites,
        key=lambda s: compute_sprite_render_sort_key(s, sort_mode=sort_mode),
    )

    calls: list[DrawCall] = []

    for i, sprite in enumerate(sorted_sprites):
        entity_data = getattr(sprite, "mesh_entity_data", {}) or {}
        entity_id = entity_data.get("id") or getattr(sprite, "mesh_name", None) or f"sprite_{i}"

        render_layer = 0
        try:
            render_layer = int(entity_data.get("render_layer", 0))
        except (TypeError, ValueError):
            pass

        depth_z = 0.0
        try:
            depth_z = float(entity_data.get("depth_z", 0.0))
        except (TypeError, ValueError):
            # For y_sort, use y position as depth
            if sort_mode == "y_sort":
                depth_z = float(getattr(sprite, "center_y", 0.0))

        texture_key = getattr(sprite, "mesh_texture_key", None)
        texture = getattr(sprite, "texture", None)
        if texture_key:
            texture_id = str(texture_key)
        elif texture:
            texture_id = getattr(texture, "name", None) or str(id(texture))
        else:
            texture_id = "missing"

        scale = getattr(sprite, "scale", 1.0)
        if isinstance(scale, tuple):
            scale_x = float(scale[0]) if scale else 1.0
            scale_y = float(scale[1]) if len(scale) > 1 else scale_x
        else:
            scale_x = scale_y = float(scale) if scale else 1.0

        transform = Transform(
            x=float(getattr(sprite, "center_x", 0.0)),
            y=float(getattr(sprite, "center_y", 0.0)),
            scale_x=scale_x,
            scale_y=scale_y,
            rotation=float(getattr(sprite, "angle", 0.0)),
        )

        sprite_color = getattr(sprite, "color", (255, 255, 255, 255))
        color = Color.from_tuple(sprite_color) if sprite_color else Color()

        calls.append(DrawCall(
            call_type=DrawCallType.SPRITE,
            layer=render_layer,
            depth_z=depth_z,
            texture_id=texture_id,
            transform=transform,
            color=color,
            entity_id=str(entity_id),
            order_hint=f"{i:06d}",
        ))

    return RenderPlan(
        calls=tuple(calls),
        frame=frame,
        scene_id=scene_id,
    )
