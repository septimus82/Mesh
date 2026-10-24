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

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow


def _gl_failures() -> tuple[type[BaseException], ...]:
    """What building or drawing with the GL layer raises when the driver or context can't do it."""
    found: list[type[BaseException]] = [RuntimeError, OSError, ValueError, TypeError, AttributeError]
    shader_error = getattr(getattr(optional_arcade.arcade, "gl", None), "ShaderException", None)
    if isinstance(shader_error, type) and issubclass(shader_error, BaseException):
        found.append(shader_error)
    from pyglet.gl.lib import GLException, MissingFunctionException  # noqa: PLC0415  # only reached when GL draws

    return (*found, GLException, MissingFunctionException)


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

# One vertex format for wall shadows and character shadows (14 floats): x, y, the pass's depth (overlapping
# shadows of one pass count once); a texture position in Arcade's sprite atlas (negative: solid, a wall);
# how much of the light it blocks; and, for a character, its own upright picture (world rectangle and atlas
# rectangle), so its shadow never darkens the character itself.
_OCCLUDER_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec2 in_uv;
in float in_amount;
in vec4 in_body;
in vec4 in_body_uv;
out vec2 v_uv;
out float v_amount;
out vec2 v_world;
flat out vec4 v_body;
flat out vec4 v_body_uv;
void main() {
    gl_Position = window.projection * window.view * vec4(in_pos.xy, 0.0, 1.0);
    gl_Position.z = in_pos.z * gl_Position.w;
    v_uv = in_uv;
    v_amount = in_amount;
    v_world = in_pos.xy;
    v_body = in_body;
    v_body_uv = in_body_uv;
}
"""

_OCCLUDER_FS = """
#version 330
uniform sampler2D atlas;
in vec2 v_uv;
in float v_amount;
in vec2 v_world;
flat in vec4 v_body;
flat in vec4 v_body_uv;
out vec4 f_color;
void main() {
    float a = 1.0;
    if (v_uv.x >= 0.0) a = texture(atlas, v_uv).a;  // a character: its picture's shape
    if (a < 0.05) discard;
    if (v_body.z > v_body.x && v_world.x >= v_body.x && v_world.x <= v_body.z && v_world.y >= v_body.y && v_world.y <= v_body.w) {
        vec2 t = (v_world - v_body.xy) / (v_body.zw - v_body.xy);
        if (texture(atlas, mix(v_body_uv.xy, v_body_uv.zw, t)).a > 0.3) discard;  // its own body stays lit
    }
    f_color = vec4(a * v_amount, 0.0, 0.0, 1.0);
}
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
_VERTEX = 14  # floats per occluder vertex
_SOLID = (-1.0, -1.0)  # "no picture": a wall blocks with its whole shape
_NO_BODY = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


class LightCompositor:
    """GPU resources for one window: built once, resized with the light layer."""

    def __init__(self, ctx: Any) -> None:
        gl = optional_arcade.arcade.gl
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
        self.triangles = ctx.buffer(reserve=56 * 1024)  # 14 floats a vertex
        self.occluder_vao = ctx.geometry([gl.BufferDescription(self.triangles, "3f 2f 1f 4f 4f",
                                                               ["in_pos", "in_uv", "in_amount", "in_body", "in_body_uv"])])
        self.fullscreen = gl.geometry.quad_2d_fs()
        self.accum: Any = None
        self.occlusion: Any = None

    def ensure(self, size: tuple[int, int]) -> None:
        if size == self.size and self.accum is not None:
            return
        # 8-bit RGB like Arcade's own light buffer: the same saturation, so unshadowed rooms look the same.
        self.accum = self.ctx.framebuffer(color_attachments=[self.ctx.texture(size, components=3)])
        self.occlusion = self.ctx.framebuffer(color_attachments=[self.ctx.texture(size, components=1, dtype="f2")],
                                              depth_attachment=self.ctx.depth_texture(size))
        self.size = size

    def _write(self, buffer: Any, data: array) -> None:
        nbytes = len(data) * 4
        while buffer.size < nbytes:
            buffer.orphan(size=buffer.size * 2)
        buffer.write(data)

    def _screen_box(self, camera: Any, spec: Any) -> tuple[int, int, int, int] | None:
        """The light's square (centre +- radius) in target pixels, clamped; None when it is off the target."""
        x, y, radius = spec[0], spec[1], spec[2]
        a = camera.project((x - radius, y - radius))
        b = camera.project((x + radius, y + radius))
        x0, x1 = sorted((float(a[0]), float(b[0])))
        y0, y1 = sorted((float(a[1]), float(b[1])))
        left, bottom = max(0, int(math.floor(x0)) - 2), max(0, int(math.floor(y0)) - 2)
        right, top = min(self.size[0], int(math.ceil(x1)) + 2), min(self.size[1], int(math.ceil(y1)) + 2)
        if right <= left or top <= bottom:
            return None
        return left, bottom, right - left, top - bottom

    def _draw_lights(self, lights: list[tuple[float, float, float, float, tuple[float, float, float]]], *,
                     shadowed: bool) -> None:
        data = array("f")
        for x, y, radius, attenuation, colour in lights:
            data.extend((x, y, radius, attenuation, *colour))
        self._write(self.instances, data)
        self.light_program["shadowed"] = 1 if shadowed else 0
        self.light_vao.render(self.light_program, mode=self.ctx.TRIANGLE_STRIP, instances=len(lights))

    def render(self, *, diffuse: Any, plain: list[Any], shadowed: list[tuple[Any, array]],
               ambient: tuple[int, int, int], camera: Any, target: Any, atlas: Any = None) -> None:
        """Add ``plain`` lights, then each shadowed light through its own mask, and combine onto ``target``.

        A light is ``(x, y, radius, attenuation, (r, g, b))`` in world units and 0-255 colour. A shadowed
        light comes with its occlusion triangles (the 14-float format above), pass after pass. A pass is the
        shadow seen from one point of the lamp; each of its triangles adds its amount to the mask once per
        pixel (the depth test stops two overlapping shadows of the same pass counting twice). A hard shadow is
        one pass; a soft one several passes from points spread over the lamp, all drawn at once. ``atlas`` is
        the sprite atlas texture character shadows take their shape from.
        """
        from pyglet import gl as pgl  # noqa: PLC0415  # Arcade has no depth-function setting: LESS, said outright

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
                # Only the light's own square on screen matters: clear and fill just that (scissor).
                box = self._screen_box(camera, spec)
                if box is None:
                    continue
                self.occlusion.use()
                self.occlusion.clear(depth=1.0, viewport=box)
                self.occlusion.scissor = box
                ctx.enable(ctx.DEPTH_TEST)
                pgl.glDepthFunc(pgl.GL_LESS)
                try:
                    if atlas is not None:
                        atlas.use(1)
                    self.occluder_program["atlas"] = 1
                    self._write(self.triangles, passes)
                    self.occluder_vao.render(self.occluder_program, mode=ctx.TRIANGLES, vertices=len(passes) // _VERTEX)
                finally:
                    ctx.disable(ctx.DEPTH_TEST)
                    self.occlusion.scissor = None
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
def _fan(poly: list[tuple[float, float]], depth: float, amount: float, out: array) -> None:
    """A convex polygon as triangles at ``depth`` (every shadow polygon here is convex: rays from the light)."""
    x0, y0 = poly[0]
    for (x1, y1), (x2, y2) in zip(poly[1:], poly[2:]):
        for x, y in ((x0, y0), (x1, y1), (x2, y2)):
            out.extend((x, y, depth, *_SOLID, amount, *_NO_BODY))


def _pass_depth(number: int, count: int) -> float:
    return 0.9 - 1.8 * (number + 1) / (count + 1)  # each pass nearer than the last


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
    return float(x), float(y), radius, attenuation, (colour[0], colour[1], colour[2])


# Shadow edges. A lamp is treated as a small disc: a soft shadow is the average of the shadows seen from
# points spread over it, so the edge blurs more the farther it falls from the wall (a real penumbra), and
# the shadow right at the wall's foot stays sharp. (size of the disc in px, points sampled)
SOFTNESS: dict[str, tuple[float, int]] = {"sharp": (0.0, 1), "soft": (10.0, 12), "softer": (22.0, 16)}
# How many points of the lamp a soft shadow samples, by quality (more: smoother edges, more GPU fill).
QUALITY_SAMPLES: dict[str, float] = {"low": 0.5, "normal": 1.0, "high": 1.75}


def shadow_look(manager: Any) -> tuple[float, int, float]:
    """The room's shadow edge (disc size px), passes and strength, from its preset and fine-tuning."""
    preset = str(getattr(manager, "shadow_softness", "sharp") or "sharp")
    size, count = SOFTNESS.get(preset, SOFTNESS["sharp"])
    edge = getattr(manager, "shadow_edge_px", None)
    if edge is not None:
        size = max(0.0, min(48.0, float(edge)))
        count = 1 if size <= 0 else max(count, 12)
    if size > 0:
        quality = QUALITY_SAMPLES.get(str(getattr(manager, "shadow_quality", "normal") or "normal"), 1.0)
        count = max(4, min(32, round(count * quality)))
    strength = max(0.0, min(1.0, float(getattr(manager, "shadow_strength", 1.0) or 0.0)))
    return size, count, strength


def _disc(size: float, count: int) -> list[tuple[float, float]]:
    """``count`` points spread evenly over a disc (a sunflower spiral); just the centre for a point lamp."""
    if size <= 0 or count <= 1:
        return [(0.0, 0.0)]
    golden = math.pi * (3.0 - math.sqrt(5.0))
    return [(math.cos(i * golden) * size * math.sqrt((i + 0.5) / count),
             math.sin(i * golden) * size * math.sqrt((i + 0.5) / count)) for i in range(count)]


def _lamp_points(x: float, y: float, size: float, count: int, rects: Any, polys: Any) -> list[tuple[float, float]]:
    """Where a soft lamp's light comes from: its disc's sample points, less those inside a wall. A point inside a
    wall casts no shadow of it (light_shadow_polygons), so a lamp beside a wall leaked wedges of light behind it."""
    from .shadows import _inside_polygon  # noqa: PLC0415

    points = _disc(size, count)
    if len(points) == 1:
        return points  # a point lamp: as Milestone 12 (inside a wall it casts nothing of it)
    clear = [(dx, dy) for dx, dy in points
             if not any(r.x < x + dx < r.x + r.width and r.y < y + dy < r.y + r.height for r in rects)
             and not any(_inside_polygon(x + dx, y + dy, poly) for poly in polys)]
    return clear or [(0.0, 0.0)]


def shadow_triangles(manager: Any, x: float, y: float, radius: float,
                     look: tuple[float, int, float]) -> tuple[list[array], int, array, list[tuple[float, float]]]:
    """The light's wall shadows: one triangle array per pass, how many shapes, all passes joined, and the lamp's
    sample points the passes are cast from. Cached per light position, size and look."""
    from .shadows import cull_occluders_for_light, cull_polygons_for_light, light_shadow_polygons  # noqa: PLC0415

    size, count, strength = look
    reach = math.ceil(radius / 32.0) * 32.0  # flicker changes the radius: build for the next size up and reuse it
    key = (round(x, 1), round(y, 1), reach, size, count, strength)
    cache: dict[Any, tuple[list[array], int, array, list[tuple[float, float]]]] = manager._shadow_cache
    hit = cache.get(key)
    if hit is not None:
        return hit
    rects, polys = manager._shadow_occluders
    near_rects = cull_occluders_for_light(x, y, reach + size, rects)
    near_polys = cull_polygons_for_light(x, y, reach + size, polys)
    passes: list[array] = []
    shapes_total = 0
    points = _lamp_points(x, y, size, count, near_rects, near_polys)
    for number, (dx, dy) in enumerate(points):
        triangles = array("f")
        shapes = light_shadow_polygons((x + dx, y + dy), reach, near_rects, near_polys)
        for shape in shapes:
            if len(shape) >= 3:
                _fan(shape, _pass_depth(number, len(points)), strength / len(points), triangles)
        shapes_total += len(shapes)
        passes.append(triangles)
    joined = array("f")
    for part in passes:
        joined.extend(part)
    if len(cache) > 512:  # a light moving every frame: keep the cache small
        cache.clear()
    cache[key] = (passes, shapes_total, joined, points)
    return cache[key]


# --------------------------------------------------------------------------------- character shadows
class CharacterShadow:
    """One character's shadow-casting picture this frame (see character_shadows)."""

    __slots__ = ("feet", "height", "half_width", "uv", "body", "body_uv", "strength", "length", "key")

    def __init__(self, feet: tuple[float, float], height: float, half_width: float, uv: tuple[float, float, float, float],
                 body: tuple[float, float, float, float], body_uv: tuple[float, float, float, float],
                 strength: float, length: float, key: int) -> None:
        self.feet, self.height, self.half_width, self.uv = feet, height, half_width, uv
        self.body, self.body_uv, self.strength, self.length, self.key = body, body_uv, strength, length, key


CHARACTER_TAGS = ("player", "npc")  # cast a shadow unless told not to (project_ops.casts_shadow); others when told to
DEFAULT_CHARACTER_STRENGTH = 0.85


def _cast_settings(data: dict[str, Any]) -> dict[str, Any] | None:
    """An entity's cast-shadow settings, or None if it casts none."""
    value = data.get("cast_shadow")
    settings = dict(value) if isinstance(value, dict) else {"enabled": value} if isinstance(value, bool) else {}
    enabled = settings.get("enabled")
    if enabled is None:
        enabled = data.get("tag") in CHARACTER_TAGS
    return settings if enabled else None


def _opaque_box(texture: Any, cache: dict[Any, tuple[int, int, int, int] | None]) -> tuple[int, int, int, int] | None:
    """The picture's non-transparent rectangle (left, top, right, bottom; image pixels, y down), cached."""
    name = getattr(texture, "atlas_name", None) or id(texture)
    if name not in cache:
        image = getattr(texture, "image", None)
        box = None
        if image is not None:
            try:
                box = image.getchannel("A").getbbox()
            except (ValueError, AttributeError):
                box = (0, 0, image.width, image.height)
        cache[name] = box
    return cache[name]


def character_shadows(manager: Any, window: Any, atlas: Any) -> list[CharacterShadow]:
    """The characters that cast shadows this frame, with what their pictures look like right now."""
    scene = getattr(window, "scene_controller", None)
    sprites = getattr(scene, "all_sprites", None) if scene is not None else None
    if not sprites or atlas is None:
        return []
    boxes: dict[Any, Any] = manager._opaque_boxes
    heights: dict[int, float] = manager._character_heights
    out: list[CharacterShadow] = []
    for sprite in sprites:
        data = getattr(sprite, "mesh_entity_data", None)
        if not isinstance(data, dict) or not getattr(sprite, "visible", True) or getattr(sprite, "alpha", 255) < 20:
            continue
        settings = _cast_settings(data)
        texture = getattr(sprite, "texture", None)
        if settings is None or texture is None:
            continue
        try:
            region = atlas.get_texture_region_info(texture.atlas_name)
        except (KeyError, AttributeError):
            continue  # not drawn yet (not in the atlas): next frame
        box = _opaque_box(texture, boxes)
        if box is None:
            continue
        tw, th = float(texture.width), float(texture.height)
        u0, v0, u1, _a, _b, v1, _c, _d = region.texture_coordinates  # v0: the picture's top row
        left, top, right, bottom = box
        # The shape from the feet (lowest opaque row) to the top of the head (highest opaque row).
        uv = (u0 + (u1 - u0) * left / tw, v0 + (v1 - v0) * bottom / th, u0 + (u1 - u0) * right / tw, v0 + (v1 - v0) * top / th)
        sx, sy = abs(float(getattr(sprite, "scale_x", 1.0) or 1.0)), abs(float(getattr(sprite, "scale_y", 1.0) or 1.0))
        cx, cy = float(sprite.center_x), float(sprite.center_y)
        feet = (cx + ((left + right) / 2 - tw / 2) * sx, cy - (bottom - th / 2) * sy)
        key = id(sprite)
        if key not in heights:  # once per character: the walk cycle must not make its shadow breathe
            heights[key] = max(4.0, (bottom - top) * sy)
        height = float(settings.get("height") or heights[key])
        half_w, half_h = tw * sx / 2, th * sy / 2
        body = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
        body_uv = (u0, v1, u1, v0)  # world bottom-left is the picture's bottom row
        strength = max(0.0, min(1.0, float(settings.get("strength", DEFAULT_CHARACTER_STRENGTH))))
        length = max(0.2, min(3.0, float(settings.get("length", 1.0))))
        out.append(CharacterShadow(feet, height, (right - left) * sx / 2, uv, body, body_uv, strength, length, key))
    return out


def _character_quad(char: CharacterShadow, lx: float, ly: float, radius: float, depth: float, amount: float,
                    out: array) -> bool:
    """The character's picture laid on the ground, from its feet away from a light at (lx, ly)."""
    fx, fy = char.feet
    dx, dy = fx - lx, fy - ly
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return False
    ux, uy = dx / dist, dy / dist
    # A lamp a little above head height: the shadow lengthens as the character walks away from it.
    length = max(char.height * 0.35, min(char.height * 4.0, dist * 1.25)) * char.length
    px, py = uy, -ux  # to the right, looking along the shadow
    hw, tip = char.half_width, char.half_width * 1.15
    u0, v_feet, u1, v_head = char.uv
    corners = ((fx - px * hw, fy - py * hw, u0, v_feet), (fx + px * hw, fy + py * hw, u1, v_feet),
               (fx + ux * length + px * tip, fy + uy * length + py * tip, u1, v_head),
               (fx + ux * length - px * tip, fy + uy * length - py * tip, u0, v_head))
    for i in (0, 1, 2, 0, 2, 3):
        x, y, u, v = corners[i]
        out.extend((x, y, depth, u, v, amount * char.strength, *char.body, *char.body_uv))
    return True


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
    softness = str(getattr(manager, "shadow_softness", "sharp") or "sharp")
    look = shadow_look(manager)
    atlas = getattr(ctx, "default_atlas", None)
    characters = character_shadows(manager, window, atlas) if getattr(manager, "character_shadows", True) else []
    disc = _disc(look[0], look[1])
    plain: list[Any] = []
    wanted: list[tuple[float, Any, array]] = []
    shapes = triangle_count = off_screen = character_casts = 0
    for light in list(layer):
        spec = _light_spec(light)
        if spec is None:
            continue
        x, y, radius = spec[0], spec[1], spec[2]
        if view is not None and (x + radius < view[0] or x - radius > view[2] or y + radius < view[1] or y - radius > view[3]):
            off_screen += 1  # it lights nothing on screen
            continue
        if not casts.get(id(light), True):
            plain.append(spec)
            continue
        walls, count, joined, points = (shadow_triangles(manager, x, y, radius, look) if (rects or polys)
                                        else ([], 0, array("f"), disc))
        near = [c for c in characters if math.hypot(c.feet[0] - x, c.feet[1] - y) < radius
                and not (c.body[0] - 4 <= x <= c.body[2] + 4 and c.body[1] - 4 <= y <= c.body[3] + 4)]  # its own lamp
        if not count and not near:
            plain.append(spec)
            continue
        if near:  # walls and characters, pass by pass: each pass nearer than the last
            data = array("f")
            for number, (ox, oy) in enumerate(points):
                if walls:
                    data.extend(walls[number])
                for char in near:
                    _character_quad(char, x + ox, y + oy, radius, _pass_depth(number, len(points)), look[2] / len(points),
                                    data)
            character_casts += len(near)
        else:
            data = joined
        shapes += count
        triangle_count += len(data) // (_VERTEX * 3)
        centre = ((view[0] + view[2]) / 2, (view[1] + view[3]) / 2) if view else (x, y)
        wanted.append((math.hypot(x - centre[0], y - centre[1]), spec, data))
    wanted.sort(key=lambda item: item[0])  # nearest the middle of the view first
    over = wanted[budget:]
    plain.extend(spec for _d, spec, _p in over)
    shadowed = [(spec, passes) for _d, spec, passes in wanted[:budget]]
    try:
        compositor.render(diffuse=diffuse, plain=plain, shadowed=shadowed, ambient=manager._ambient_rgb(),
                          camera=camera, target=getattr(layer, "window", None) or ctx.screen,
                          atlas=getattr(atlas, "texture", None))
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
        "shadow_poly_count": shapes, "shadow_triangles": triangle_count, "shadow_softness": softness,
        "shadow_edge_px": look[0], "shadow_passes": look[1], "shadow_strength": look[2],
        "characters": len(characters), "character_shadows": character_casts,
        "character_feet": [[round(c.feet[0], 1), round(c.feet[1], 1)] for c in characters[:16]],  # where shadows start
    }
    if over:
        manager._log_counter_once("shadow_budget", f"{len(wanted)} lights cast shadows here; {len(over)} beyond the "
                                  f"budget of {budget} are drawn without shadows.")
    return True
