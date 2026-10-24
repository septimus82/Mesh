"""Lighting with shadows that belong to their light (Milestone 12).

    final = diffuse * (ambient + sum over lights of light_i * (1 - occlusion_i))

Arcade's LightLayer adds every light in one pass, so a shadow could only be painted over the finished
picture: black over the room light and over every other lamp. Here each light that casts shadows is
added on its own: its shadow polygons go into an occlusion mask, then the light is added scaled by
(1 - mask). Lights that cast no shadow (or have no wall in reach) are added together in one instanced
draw. The light falloff and the final combine are Arcade's own shader maths, so a room with shadows
off, or a light with nothing to block it, looks exactly as before.

This module owns the GPU side (programs, textures, draws); ``render_shadowed_lighting`` gathers the
manager's lights and occluders, keeps to a per-frame budget of shadowed lights, and reports what it did.
If anything here can't run (no GL context, a framebuffer or program failure), the caller draws the room
lit without shadows and says why; it never falls back to painting black over the scene.
"""

from __future__ import annotations

import math
from array import array
from typing import Any

from engine.swallowed_exceptions import _log_swallow


def _gl_failures() -> tuple[type[BaseException], ...]:
    """What building or drawing with the GL layer raises when the driver or context can't do it."""
    found: list[type[BaseException]] = [RuntimeError, OSError, ValueError, TypeError, AttributeError]
    try:
        from arcade.gl.exceptions import ShaderException  # noqa: PLC0415
        from pyglet.gl.lib import GLException, MissingFunctionException  # noqa: PLC0415

        found += [ShaderException, GLException, MissingFunctionException]
    except ImportError:
        pass
    return tuple(found)


# How many lights may cast shadows in one frame; the rest are drawn lit, without shadows, and the stats
# say how many. Each costs one mask clear, its shadow triangles and one light draw.
DEFAULT_SHADOW_LIGHT_BUDGET = 16

_LIGHT_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec2 in_vert;
in vec2 in_uv;
in vec2 in_instance_position;
in float in_instance_radius;
in float in_instance_attenuation;
in vec3 in_instance_color;
out float attenuation;
out vec3 color;
out vec2 uv;
void main() {
    vec2 position = (in_vert * in_instance_radius) + in_instance_position;
    gl_Position = window.projection * window.view * vec4(position, 0.0, 1.0);
    uv = in_uv;
    attenuation = in_instance_attenuation;
    color = in_instance_color / 255.0;
}
"""

# Arcade's point-light falloff (resources/system/shaders/lights/point_lights_fs.glsl), optionally
# scaled by what the light's own occlusion mask leaves of it.
_LIGHT_FS = """
#version 330
uniform sampler2D occlusion;
uniform vec2 target_size;
uniform int shadowed;
in vec2 uv;
in float attenuation;
in vec3 color;
out vec4 f_color;
void main() {
    float dist = length(uv * 2.0 - vec2(1.0));
    if (dist > 1.0) discard;
    float att = (1.0 - dist + attenuation);
    float visible = 1.0;
    if (shadowed == 1) visible = 1.0 - clamp(texture(occlusion, gl_FragCoord.xy / target_size).r, 0.0, 1.0);
    f_color = vec4(color * clamp(att, 0.0, 1.0) * visible, 0.0);
}
"""

_OCCLUDER_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec2 in_pos;
void main() { gl_Position = window.projection * window.view * vec4(in_pos, 0.0, 1.0); }
"""

_OCCLUDER_FS = """
#version 330
uniform float amount;
out vec4 f_color;
void main() { f_color = vec4(amount, 0.0, 0.0, 1.0); }
"""

# Arcade's combine (combine_fs.glsl): the scene lit by the room light plus the summed lamps.
_COMBINE_VS = """
#version 330
in vec2 in_vert;
in vec2 in_uv;
out vec2 vs_uv;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); vs_uv = in_uv; }
"""

_COMBINE_FS = """
#version 330
uniform sampler2D diffuse_buffer;
uniform sampler2D light_buffer;
uniform vec3 ambient;
in vec2 vs_uv;
out vec4 f_color;
void main() {
    vec3 diffuse = texture(diffuse_buffer, vs_uv).rgb;
    vec3 light = texture(light_buffer, vs_uv).rgb;
    f_color = vec4(diffuse * ambient / 255.0 + diffuse * light, 1.0);
}
"""

_STRIDE = 28  # 2f position, 1f radius, 1f attenuation, 3f colour


class LightCompositor:
    """GPU resources for one window: built once, resized with the light layer."""

    def __init__(self, ctx: Any) -> None:
        from arcade import gl  # noqa: PLC0415  # the GL layer is only needed once lighting draws

        self.ctx = ctx
        self.size: tuple[int, int] = (0, 0)
        self.light_program = ctx.program(vertex_shader=_LIGHT_VS, fragment_shader=_LIGHT_FS)
        self.occluder_program = ctx.program(vertex_shader=_OCCLUDER_VS, fragment_shader=_OCCLUDER_FS)
        self.combine_program = ctx.program(vertex_shader=_COMBINE_VS, fragment_shader=_COMBINE_FS)
        quad = array("f", [-1.0, 1.0, 0.0, 1.0, -1.0, -1.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, 1.0, 0.0])
        self.instances = ctx.buffer(reserve=_STRIDE * 64)
        self.light_vao = ctx.geometry([
            gl.BufferDescription(ctx.buffer(data=quad), "2f 2f", ["in_vert", "in_uv"]),
            gl.BufferDescription(self.instances, "2f 1f 1f 3f", ["in_instance_position", "in_instance_radius",
                                                                  "in_instance_attenuation", "in_instance_color"],
                                 instanced=True),
        ])
        self.triangles = ctx.buffer(reserve=4096)
        self.occluder_vao = ctx.geometry([gl.BufferDescription(self.triangles, "2f", ["in_pos"])])
        self.fullscreen = gl.geometry.quad_2d_fs()
        self.accum: Any = None
        self.occlusion: Any = None

    def ensure(self, size: tuple[int, int]) -> None:
        if size == self.size and self.accum is not None:
            return
        # 8-bit RGB like Arcade's own light buffer: the same saturation, so unshadowed rooms look the same.
        self.accum = self.ctx.framebuffer(color_attachments=[self.ctx.texture(size, components=3)])
        self.occlusion = self.ctx.framebuffer(color_attachments=[self.ctx.texture(size, components=1, dtype="f2")])
        self.size = size

    def _write(self, buffer: Any, data: array) -> None:
        nbytes = len(data) * 4
        while buffer.size < nbytes:
            buffer.orphan(size=buffer.size * 2)
        buffer.write(data)

    def _draw_lights(self, lights: list[tuple[float, float, float, float, tuple[float, float, float]]], *,
                     shadowed: bool) -> None:
        data = array("f")
        for x, y, radius, attenuation, colour in lights:
            data.extend((x, y, radius, attenuation, *colour))
        self._write(self.instances, data)
        self.light_program["shadowed"] = 1 if shadowed else 0
        self.light_vao.render(self.light_program, mode=self.ctx.TRIANGLE_STRIP, instances=len(lights))

    def render(self, *, diffuse: Any, plain: list[Any], shadowed: list[tuple[Any, list[tuple[float, array]]]],
               ambient: tuple[int, int, int], camera: Any, target: Any) -> None:
        """Add ``plain`` lights, then each shadowed light through its own mask, and combine onto ``target``.

        A light is ``(x, y, radius, attenuation, (r, g, b))`` in world units and 0-255 colour. A shadowed
        light comes with its occlusion: ``(amount, triangles)`` pairs, the triangles a flat float array of
        world points, each pass adding ``amount`` to the mask (1.0 for a hard shadow).
        """
        ctx = self.ctx
        self.ensure(tuple(diffuse.size))
        self.light_program["occlusion"] = 0
        self.light_program["target_size"] = self.size
        self.accum.use()
        self.accum.clear()
        camera.use()  # world projection (scroll and zoom) for the lights and the shadow triangles
        ctx.enable(ctx.BLEND)
        try:
            ctx.blend_func = ctx.BLEND_ADDITIVE
            if plain:
                self._draw_lights(plain, shadowed=False)
            for spec, passes in shadowed:
                self.occlusion.use()
                self.occlusion.clear()
                for amount, triangles in passes:
                    if not triangles:
                        continue
                    self._write(self.triangles, triangles)
                    self.occluder_program["amount"] = float(amount)
                    self.occluder_vao.render(self.occluder_program, mode=ctx.TRIANGLES, vertices=len(triangles) // 2)
                self.accum.use()
                self.occlusion.color_attachments[0].use(0)
                self._draw_lights([spec], shadowed=True)
        finally:
            ctx.blend_func = ctx.BLEND_DEFAULT
        target.use()
        self.combine_program["diffuse_buffer"] = 0
        self.combine_program["light_buffer"] = 1
        self.combine_program["ambient"] = tuple(float(c) for c in ambient[:3])
        diffuse.use(0)
        self.accum.color_attachments[0].use(1)
        self.fullscreen.render(self.combine_program)


# ------------------------------------------------------------------------------------- gathering
def _fan(poly: list[tuple[float, float]], out: array) -> None:
    """A convex polygon as triangles (every shadow polygon here is convex: rays from the light)."""
    x0, y0 = poly[0]
    for (x1, y1), (x2, y2) in zip(poly[1:], poly[2:]):
        out.extend((x0, y0, x1, y1, x2, y2))


def _view_rect(window: Any, camera: Any) -> tuple[float, float, float, float] | None:
    """The world rectangle the camera shows: left, bottom, right, top."""
    try:
        cx, cy = camera.position
        zoom = float(getattr(camera, "zoom", 1.0) or 1.0)
        half_w, half_h = float(window.width) / 2 / zoom, float(window.height) / 2 / zoom
        return float(cx) - half_w, float(cy) - half_h, float(cx) + half_w, float(cy) + half_h
    except (AttributeError, TypeError, ValueError):
        return None


def _light_spec(light: Any) -> tuple[float, float, float, float, tuple[float, float, float]] | None:
    try:
        x, y = light.position
        radius = float(light.radius)
        colour = tuple(float(c) for c in (getattr(light, "_color", None) or getattr(light, "color", None) or (255, 255, 255))[:3])
        attenuation = float(getattr(light, "_attenuation", 0.0))
    except (AttributeError, TypeError, ValueError):
        return None
    if radius <= 0:
        return None
    return float(x), float(y), radius, attenuation, colour  # type: ignore[return-value]


def shadow_triangles(manager: Any, x: float, y: float, radius: float) -> tuple[array, int]:
    """The light's shadow polygons as triangles, cached per light position and size (walls don't move)."""
    from .shadows import cull_occluders_for_light, cull_polygons_for_light, light_shadow_polygons  # noqa: PLC0415

    reach = math.ceil(radius / 32.0) * 32.0  # flicker changes the radius: build for the next size up and reuse it
    key = (round(x, 1), round(y, 1), reach)
    cache: dict[Any, tuple[array, int]] = manager._shadow_cache
    hit = cache.get(key)
    if hit is not None:
        return hit
    rects, polys = manager._shadow_occluders
    near_rects = cull_occluders_for_light(x, y, reach, rects)
    near_polys = cull_polygons_for_light(x, y, reach, polys)
    shapes = light_shadow_polygons((x, y), reach, near_rects, near_polys)
    triangles = array("f")
    for shape in shapes:
        if len(shape) >= 3:
            _fan(shape, triangles)
    if len(cache) > 512:  # a light moving every frame: keep the cache small
        cache.clear()
    cache[key] = (triangles, len(shapes))
    return triangles, len(shapes)


def render_shadowed_lighting(manager: Any) -> bool:
    """Draw the room's lights with per-light shadows. False (and the reason in the stats) if it can't run."""
    from . import occluder_utils  # noqa: PLC0415

    layer, window = manager._layer, manager.window
    camera = getattr(window, "camera", None)
    ctx = getattr(window, "ctx", None)
    diffuse = getattr(layer, "diffuse_texture", None)
    if ctx is None or camera is None or diffuse is None or not callable(getattr(camera, "use", None)):
        manager._last_lighting_stats = {"shadows_mode": manager.shadows_mode, "renderer": "unshadowed",
                                        "shadows_unavailable": "no GL context or camera"}
        return False
    compositor: LightCompositor | bool | None = getattr(manager, "_compositor", None)
    if compositor is None:
        try:
            compositor = manager._compositor = LightCompositor(ctx)
        except _gl_failures() as exc:  # a driver that can't build the programs or targets: the room is lit, without shadows
            _log_swallow("LCMP-001", f"engine/lighting/light_compositor.py create: {exc}", once=True)
            manager._compositor = False
            compositor = False
    if not isinstance(compositor, LightCompositor):
        manager._last_lighting_stats = {"shadows_mode": manager.shadows_mode, "renderer": "unshadowed",
                                        "shadows_unavailable": "the GPU couldn't build the shadow renderer"}
        return False

    if manager._shadow_occluders is None:
        manager._shadow_occluders = occluder_utils.build_rect_and_poly_occluders(manager._static_occluders or [])
        manager._shadow_cache = {}
    rects, polys = manager._shadow_occluders
    view = _view_rect(window, camera)
    budget = int(getattr(manager, "shadow_light_budget", DEFAULT_SHADOW_LIGHT_BUDGET))
    casts = getattr(manager, "_light_casts_shadows", {})
    plain: list[Any] = []
    wanted: list[tuple[float, Any, list[tuple[float, array]]]] = []
    shapes = triangle_count = off_screen = 0
    for light in list(layer):
        spec = _light_spec(light)
        if spec is None:
            continue
        x, y, radius = spec[0], spec[1], spec[2]
        if view is not None and (x + radius < view[0] or x - radius > view[2] or y + radius < view[1] or y - radius > view[3]):
            off_screen += 1  # it lights nothing on screen
            continue
        if (rects or polys) and casts.get(id(light), True):
            triangles, count = shadow_triangles(manager, x, y, radius)
            if count:
                shapes += count
                triangle_count += len(triangles) // 6
                centre = ((view[0] + view[2]) / 2, (view[1] + view[3]) / 2) if view else (x, y)
                wanted.append((math.hypot(x - centre[0], y - centre[1]), spec, [(1.0, triangles)]))
                continue
        plain.append(spec)
    wanted.sort(key=lambda item: item[0])  # nearest the middle of the view first
    over = wanted[budget:]
    plain.extend(spec for _d, spec, _p in over)
    shadowed = [(spec, passes) for _d, spec, passes in wanted[:budget]]
    try:
        compositor.render(diffuse=diffuse, plain=plain, shadowed=shadowed, ambient=manager._ambient_rgb(),
                          camera=camera, target=getattr(layer, "window", None) or ctx.screen)
    except _gl_failures() as exc:  # a GL failure mid-frame: the room is lit, without shadows, not black
        _log_swallow("LCMP-002", f"engine/lighting/light_compositor.py render: {exc}", once=True)
        manager._last_lighting_stats = {"shadows_mode": manager.shadows_mode, "renderer": "unshadowed",
                                        "shadows_unavailable": f"render failed: {type(exc).__name__}"}
        return False
    finally:
        restore = getattr(getattr(window, "camera_controller", None), "use_gui_camera", None)
        if callable(restore):
            restore()
    manager._last_lighting_stats = {
        "shadows_mode": manager.shadows_mode, "renderer": "per_light",
        "lights": len(plain) + len(shadowed) + off_screen, "lights_drawn": len(plain) + len(shadowed),
        "lights_off_screen": off_screen, "shadowed_lights": len(shadowed), "shadow_light_budget": budget,
        "lights_over_budget": len(over), "occluder_count": len(rects) + len(polys),
        "shadow_poly_count": shapes, "shadow_triangles": triangle_count,
    }
    if over:
        manager._log_counter_once("shadow_budget", f"{len(wanted)} lights cast shadows here; {len(over)} beyond the "
                                  f"budget of {budget} are drawn without shadows.")
    return True
