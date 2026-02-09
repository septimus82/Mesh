"""
Pipeline for rendering the scene in a deterministic, testable way.

Extracts sorting, culling, and draw order logic from SceneController.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

import engine.optional_arcade as optional_arcade
from engine.culling import Rect, is_sprite_visible, sprite_bounds
from engine.depth_tint_model import (
    DepthTintSettings,
    apply_tint_to_sprite_color,
    compute_sprite_tint,
)
from engine.editor.sprite_outline_model import (
    OutlineSettings,
    compute_sprite_outline_draw_calls,
    should_draw_outline,
)
from engine.parallax_model import (
    BackgroundPlane,
    compute_parallax_offset_with_zoom,
    sort_background_planes,
)
from engine.render_queue import DrawSpriteCmd
from engine.render_sort_model import compute_sprite_render_sort_key
from engine.sprite_shadow_model import compute_sprite_multi_shadow


@dataclass
class RenderContext:
    """Inputs required to compute a draw plan."""

    # Viewport / Camera
    camera_x: float
    camera_y: float
    viewport_w: float
    viewport_h: float
    zoom: float
    camera_rect: Optional[Rect] = None  # For culling
    use_culling: bool = False

    # Settings
    sort_mode: str = "y_sort"
    shadows_enabled: bool = False
    shadows_ao_enabled: bool = False
    shadows_contact_enabled: bool = False
    depth_tint_settings: DepthTintSettings = field(
        default_factory=lambda: DepthTintSettings(enabled=False)
    )
    outline_settings: OutlineSettings = field(
        default_factory=lambda: OutlineSettings(enabled=False)
    )

    # Content
    background_planes: List[BackgroundPlane] = field(default_factory=list)
    sprites: List[Any] = field(default_factory=list)  # Flat list of all sprites to consider


@dataclass
class ShadowDrawOp:
    """A parameterized shadow ellipse draw call."""
    cx: float
    cy: float
    width: float
    height: float
    color: tuple[int, int, int, int]


@dataclass
class BackgroundDrawOp:
    """A prioritized background plane draw call."""
    plane: BackgroundPlane
    base_x: float
    base_y: float
    alpha: int


@dataclass
class SpriteDrawOp:
    """A sprite draw operation, potentially including tint or outline."""
    sprite: Any
    tint: Optional[tuple[int, int, int, int]] = None
    outline_draw_calls: List[Any] = field(default_factory=list)


@dataclass
class DrawPlan:
    """Ordered lists of operations to execute."""
    background_ops: List[BackgroundDrawOp]
    shadow_ops: List[ShadowDrawOp]
    sprite_ops: List[SpriteDrawOp]


# -----------------------------------------------------------------------------
# Pipeline Steps
# -----------------------------------------------------------------------------

def build_render_context(
    *,
    sprites: List[Any],
    background_planes: List[BackgroundPlane],
    camera_pos: tuple[float, float],
    viewport_size: tuple[float, float],
    zoom: float,
    sort_mode: str,
    shadows_enabled: bool,
    shadows_ao_enabled: bool,
    shadows_contact_enabled: bool,
    depth_tint_settings: DepthTintSettings,
    outline_settings: OutlineSettings,
    use_culling: bool,
    camera_rect: Optional[Rect] = None,
) -> RenderContext:
    """Use this to construct the context from SceneController state."""
    return RenderContext(
        camera_x=camera_pos[0],
        camera_y=camera_pos[1],
        viewport_w=viewport_size[0],
        viewport_h=viewport_size[1],
        zoom=zoom,
        camera_rect=camera_rect,
        use_culling=use_culling,
        sort_mode=sort_mode,
        shadows_enabled=shadows_enabled,
        shadows_ao_enabled=shadows_ao_enabled,
        shadows_contact_enabled=shadows_contact_enabled,
        depth_tint_settings=depth_tint_settings,
        outline_settings=outline_settings,
        background_planes=background_planes,
        sprites=sprites,
    )


def compute_draw_plan(ctx: RenderContext) -> DrawPlan:
    """Pure transformation of RenderContext into a linear plan."""
    # 1. Background Planes
    bg_ops = _compute_background_ops(ctx)

    # 2. Sort Sprites
    sorted_sprites = sorted(
        ctx.sprites,
        key=lambda s: compute_sprite_render_sort_key(s, sort_mode=ctx.sort_mode),
    )

    # 3. Shadows
    shadow_ops = []
    if ctx.shadows_enabled:
        shadow_ops = _compute_shadow_ops(ctx, sorted_sprites)

    # 4. Sprite Ops (Outlines + Tints + Draw)
    sprite_ops = _compute_sprite_ops(ctx, sorted_sprites)

    return DrawPlan(
        background_ops=bg_ops,
        shadow_ops=shadow_ops,
        sprite_ops=sprite_ops,
    )


def _compute_background_ops(ctx: RenderContext) -> List[BackgroundDrawOp]:
    ops = []
    planes = sort_background_planes(ctx.background_planes)
    center_x = ctx.viewport_w / 2.0
    center_y = ctx.viewport_h / 2.0

    for plane in planes:
        offset_x, offset_y = compute_parallax_offset_with_zoom(
            ctx.camera_x, ctx.camera_y, plane.parallax, ctx.zoom
        )
        base_x = center_x + offset_x + plane.offset_x
        base_y = center_y + offset_y + plane.offset_y
        alpha = int(max(0, min(255, plane.alpha * 255)))
        
        ops.append(BackgroundDrawOp(
            plane=plane,
            base_x=base_x,
            base_y=base_y,
            alpha=alpha
        ))
    return ops


def _compute_shadow_ops(ctx: RenderContext, sorted_sprites: List[Any]) -> List[ShadowDrawOp]:
    ops = []
    shadow_base_color = (20, 20, 20)

    for sprite in sorted_sprites:
        multi_shadow = compute_sprite_multi_shadow(
            sprite,
            contact_enabled=ctx.shadows_contact_enabled,
            ao_enabled=ctx.shadows_ao_enabled,
        )
        if multi_shadow is None:
            continue

        # Culling check
        if ctx.use_culling and ctx.camera_rect is not None:
            shadow_rect = sprite_bounds(
                multi_shadow.base_ellipse.cx,
                multi_shadow.base_ellipse.cy,
                multi_shadow.base_ellipse.width,
                multi_shadow.base_ellipse.height,
            )
            if not is_sprite_visible(ctx.camera_rect, shadow_rect):
                continue

        # AO
        if multi_shadow.ao_ellipse is not None and multi_shadow.ao_alpha > 0:
            ao_alpha = int(multi_shadow.ao_alpha * 255)
            ops.append(ShadowDrawOp(
                cx=multi_shadow.ao_ellipse.cx,
                cy=multi_shadow.ao_ellipse.cy,
                width=multi_shadow.ao_ellipse.width,
                height=multi_shadow.ao_ellipse.height,
                color=(*shadow_base_color, ao_alpha),
            ))

        # Base
        base_alpha = int(multi_shadow.base_alpha * 255)
        ops.append(ShadowDrawOp(
            cx=multi_shadow.base_ellipse.cx,
            cy=multi_shadow.base_ellipse.cy,
            width=multi_shadow.base_ellipse.width,
            height=multi_shadow.base_ellipse.height,
            color=(*shadow_base_color, base_alpha),
        ))

        # Contact
        if multi_shadow.contact_ellipse is not None and multi_shadow.contact_alpha > 0:
            contact_alpha = int(multi_shadow.contact_alpha * 255)
            ops.append(ShadowDrawOp(
                cx=multi_shadow.contact_ellipse.cx,
                cy=multi_shadow.contact_ellipse.cy,
                width=multi_shadow.contact_ellipse.width,
                height=multi_shadow.contact_ellipse.height,
                color=(*shadow_base_color, contact_alpha),
            ))
            
    return ops


def _compute_sprite_ops(ctx: RenderContext, sorted_sprites: List[Any]) -> List[SpriteDrawOp]:
    ops = []
    
    for sprite in sorted_sprites:
        # Culling check
        if ctx.use_culling and ctx.camera_rect is not None:
            center_x = float(getattr(sprite, "center_x", 0.0))
            center_y = float(getattr(sprite, "center_y", 0.0))
            width = getattr(sprite, "width", None)
            height = getattr(sprite, "height", None)
            sprite_rect = None
            
            # Fast path
            if isinstance(width, (int, float)) and isinstance(height, (int, float)):
                 if float(width) > 0.0 and float(height) > 0.0:
                      sprite_rect = sprite_bounds(center_x, center_y, float(width), float(height))
            
            # Slow path (texture check)
            if sprite_rect is None:
                texture = getattr(sprite, "texture", None)
                tex_w = getattr(texture, "width", None)
                tex_h = getattr(texture, "height", None)
                scale = float(getattr(sprite, "scale", 1.0) or 1.0) 
                if isinstance(tex_w, (int, float)) and isinstance(tex_h, (int, float)):
                    if float(tex_w) > 0.0 and float(tex_h) > 0.0:
                         sprite_rect = sprite_bounds(center_x, center_y, float(tex_w), float(tex_h), scale=scale)

            if sprite_rect is None:
                 # Fallback
                 sprite_rect = sprite_bounds(center_x, center_y, 100, 100)
            
            if not is_sprite_visible(ctx.camera_rect, sprite_rect):
                continue

        # Outline
        outline_calls = []
        entity_data = getattr(sprite, "mesh_entity_data", None) or {}
        if should_draw_outline(entity_data, ctx.outline_settings.enabled):
             center_x = float(getattr(sprite, "center_x", 0.0))
             center_y = float(getattr(sprite, "center_y", 0.0))
             try:
                render_layer = int(entity_data.get("render_layer", 0))
             except (TypeError, ValueError):
                render_layer = 0
             try:
                 depth_z = float(entity_data.get("depth_z", 0.0))
             except (TypeError, ValueError):
                 depth_z = 0.0
             
             outline_calls = compute_sprite_outline_draw_calls(
                center_x,
                center_y,
                render_layer,
                depth_z,
                ctx.outline_settings,
                entity_data=entity_data,
             )

        # Tint
        tint: Optional[tuple[int, int, int, int]] = None
        if ctx.depth_tint_settings.enabled:
             tint = compute_sprite_tint(
                sprite,
                ctx.depth_tint_settings,
                sort_mode=ctx.sort_mode,
            )

        ops.append(SpriteDrawOp(
            sprite=sprite,
            tint=tint,
            outline_draw_calls=outline_calls
        ))

    return ops


def execute_draw_plan(
    plan: DrawPlan,
    texture_lookup: Callable[[str], Optional[Any]],
    render_queue: Optional[Any] = None,
    use_batching: bool = False,
    camera_rect: Optional[Rect] = None,
    use_culling: bool = False,
) -> None:
    """Execute the full plan. Consider using granular methods if camera switching is needed."""
    execute_background_plan(plan, texture_lookup)
    execute_scene_plan(plan, render_queue, use_batching, camera_rect, use_culling)


def execute_background_plan(
    plan: DrawPlan,
    texture_lookup: Callable[[str], Optional[Any]],
) -> None:
    """Execute only the background part of the plan (usually requires GUI camera)."""
    if optional_arcade.arcade is None:
        return

    draw_texture_rectangle = getattr(optional_arcade.arcade, "draw_texture_rectangle", None)
    if not draw_texture_rectangle:
        return

    for bg_op in plan.background_ops:
        texture = texture_lookup(bg_op.plane.asset_path)
        if texture is None:
            continue
        
        tex_w = max(1.0, float(texture.width))
        tex_h = max(1.0, float(texture.height))
        
        if not bg_op.plane.repeat_x and not bg_op.plane.repeat_y:
             draw_texture_rectangle(
                bg_op.base_x, bg_op.base_y, tex_w, tex_h, texture, alpha=bg_op.alpha
            )
             continue
        
        # Tiled drawing
        x_range = (0, 0)
        y_range = (0, 0)
        
        if bg_op.plane.repeat_x:
            start_x = -((bg_op.base_x // tex_w) + 2)
            end_x = (2000 // tex_w) + 2 # Limit
            x_range = (int(start_x), int(end_x))
        else:
            x_range = (0, 1)

        if bg_op.plane.repeat_y:
             start_y = -((bg_op.base_y // tex_h) + 2)
             end_y = (2000 // tex_h) + 2
             y_range = (int(start_y), int(end_y))
        else:
            y_range = (0, 1)

        for ix in range(x_range[0], x_range[1]):
            for iy in range(y_range[0], y_range[1]):
                draw_x = bg_op.base_x + (ix * tex_w)
                draw_y = bg_op.base_y + (iy * tex_h)
                draw_texture_rectangle(
                    draw_x, draw_y, tex_w, tex_h, texture, alpha=bg_op.alpha
                )


def execute_scene_plan(
    plan: DrawPlan,
    render_queue: Optional[Any] = None,
    use_batching: bool = False,
    camera_rect: Optional[Rect] = None,
    use_culling: bool = False,
) -> None:
    """Execute shadows and sprites (usually requires World camera)."""
    if optional_arcade.arcade is None:
        return

    draw_ellipse_filled = getattr(optional_arcade.arcade, "draw_ellipse_filled", None)
    
    # Shadows
    if draw_ellipse_filled:
        for sh_op in plan.shadow_ops:
             draw_ellipse_filled(
                sh_op.cx, sh_op.cy, sh_op.width, sh_op.height, sh_op.color
             )

    # Sprites
    for op in plan.sprite_ops:
        _execute_outline_ops(op, render_queue, use_batching, camera_rect, use_culling)
        _execute_sprite_op(op, render_queue, use_batching, camera_rect, use_culling)


def _execute_outline_ops(
    op: SpriteDrawOp,
    render_queue: Any,
    use_batching: bool,
    camera_rect: Optional[Rect],
    use_culling: bool,
) -> None:
    if not op.outline_draw_calls:
        return

    sprite = op.sprite
    original_color = getattr(sprite, "color", None)
    original_alpha = getattr(sprite, "alpha", None)
    original_x = getattr(sprite, "center_x", None)
    original_y = getattr(sprite, "center_y", None)

    try:
        for call in op.outline_draw_calls:
            sprite.center_x = call.x
            sprite.center_y = call.y
            try:
                sprite.color = call.color
            except Exception:
                pass
            try:
                sprite.alpha = int(call.alpha)
            except Exception:
                pass
            
            if use_batching and render_queue:
                _submit_to_queue(sprite, render_queue, camera_rect, use_culling)
            else:
                 sprite.draw()
    finally:
         _restore_sprite_state(sprite, original_x, original_y, original_color, original_alpha)


def _execute_sprite_op(
    op: SpriteDrawOp,
    render_queue: Any,
    use_batching: bool,
    camera_rect: Optional[Rect],
    use_culling: bool,
) -> None:
    sprite = op.sprite
    
    if op.tint is None:
        if use_batching and render_queue:
            _submit_to_queue(sprite, render_queue, camera_rect, use_culling)
        else:
            sprite.draw()
        return

    # Apply tint
    original_color = getattr(sprite, "color", None)
    try:
        tinted = apply_tint_to_sprite_color(original_color, op.tint)
        sprite.color = tinted
        if use_batching and render_queue:
            _submit_to_queue(sprite, render_queue, camera_rect, use_culling)
        else:
            sprite.draw()
    finally:
        try:
             if original_color is None:
                 sprite.color = (255, 255, 255, 255)
             else:
                 sprite.color = original_color
        except Exception:
            pass


def _submit_to_queue(sprite: Any, render_queue: Any, camera_rect: Optional[Rect], use_culling: bool) -> None:
    texture = getattr(sprite, "texture", None)
    texture_key = getattr(sprite, "mesh_texture_key", None)
    if texture_key is None:
        name = getattr(texture, "name", None)
        if name:
             texture_key = ("texture", str(name))
        else:
             texture_key = ("texture_id", id(texture) if texture is not None else id(sprite))

    scale = getattr(sprite, "scale", 1.0)
    if isinstance(scale, tuple) and scale:
        try:
            scale_value = float(scale[0])
        except (TypeError, ValueError):
             scale_value = 1.0
    else:
        scale_value = float(scale)  # type: ignore

    alpha = getattr(sprite, "alpha", 255)
    rotation = getattr(sprite, "angle", 0.0)
    center_x = float(getattr(sprite, "center_x", 0.0))
    center_y = float(getattr(sprite, "center_y", 0.0))

    if use_culling and camera_rect is not None:
         width = getattr(sprite, "width", None)
         height = getattr(sprite, "height", None)
         sprite_rect = None
         if isinstance(width, (int, float)) and isinstance(height, (int, float)):
             if float(width) > 0.0 and float(height) > 0.0:
                 sprite_rect = sprite_bounds(center_x, center_y, float(width), float(height))
         if sprite_rect is None:
              # Fallback
              sprite_rect = sprite_bounds(center_x, center_y, 100, 100)
         
         if not is_sprite_visible(camera_rect, sprite_rect):
             return

    # Entity data layer index
    entity_data = getattr(sprite, "mesh_entity_data", None) or {}
    render_layer = entity_data.get("render_layer", 0)
    try:
        layer_index = int(render_layer)
    except (TypeError, ValueError):
        layer_index = 0
    
    # Use current color (which might have been tinted by _execute_sprite_op)
    sprite_color = getattr(sprite, "color", None)

    if hasattr(render_queue, "submit"):
        render_queue.submit(
            DrawSpriteCmd(
                texture_key=texture_key,
                texture=texture,
                x=center_x,
                y=center_y,
                scale=scale_value,
                alpha=float(alpha),
                rotation=float(rotation),
                layer=layer_index,
                blend_mode="normal",
                color=sprite_color,
            )
        )

def _restore_sprite_state(sprite, x, y, color, alpha):
    try:
        if x is not None: sprite.center_x = x
        if y is not None: sprite.center_y = y
        if color is None:
            sprite.color = (255, 255, 255, 255)
        else:
            sprite.color = color
        if alpha is not None:
             sprite.alpha = alpha
    except Exception:
        pass
