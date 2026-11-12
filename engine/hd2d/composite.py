"""The HD-2D final composite (M17-L4-1): the one place the rendered world becomes the picture, shared by the game
and Mesh Studio's editing view.

``Hd2dRenderer.draw`` renders the world into its own framebuffer (RGBA8 colour + DEPTH24 depth texture), then makes
the picture in the framebuffer that was active when it was called (the window, or Studio's canvas viewport):

- **blit** (every room today): the world's colour copied as it is. Nothing here is allocated.
- **depth of field** (#460): the DoF pass in the blit's place, reading colour and depth.
- **composite** (this module): a full-picture pass reading the world's colour and depth, in the blit's place. With
  the depth of field too, the DoF writes straight into the composite's input (``chain_target``) and the composite
  reads it: one pass each, no copy of the frame.

Studio's lines (grid, selection, handles) are drawn after whatever made the picture, never through it
(``Hd2dRenderer._overlay_after``), and Mesh's HUD, dialogue and menus are drawn after the renderer returns: neither
ever passes through the composite.

Two modes. **Identity** writes each world texel exactly (``texelFetch``: no filtering, no colour conversion, alpha
kept): reached through ``Hd2dRenderer.force_identity_composite`` (a test/diagnostic switch, not a setting).
**Grade** (M17-L4-2, the room's ``settings.hd2d.post``: engine.hd2d.post) decodes the texel to linear light, grades
it (white balance, exposure, luminance contrast with a soft shoulder, saturation, split toning, highlight protection),
darkens toward the picture's corners (the vignette, in a circle of the picture: right in Studio's canvas and any
size), encodes it again, alpha kept. Its uniforms are set when the room's settings change, not every frame.
**Haze** (M17-L4-3, the room's ``settings.hd2d.haze``: engine.hd2d.haze), in the same pass and before the grade: each
pixel's own depth (the world's depth texture, linearised as the depth of field's) moves it toward the lit haze colour
in linear light by engine.hd2d.haze.amount; nearer than the onset (and where nothing was drawn) the texel is kept
exactly. Only the onset changes per frame (``frame``: one uniform, set when it moves). No pass, texture or target is
added for it.

GPU objects are made the first time they are needed and freed by ``release`` (the renderer's own, on scene change or
window close); the chain target is remade when the picture's size changes.
"""

from __future__ import annotations

from typing import Any

COMPOSITE_FS = """
#version 330
// The world's own pixel under this one, from the quad's coordinates (not gl_FragCoord): right in a viewport anywhere
// in the window, Mesh Studio's canvas included (as engine.hd2d.dof's pass). u_depth: the world's depth, bound for the
// effects that read it (L4-2 onwards); the identity composite doesn't.
uniform sampler2D u_color; uniform sampler2D u_depth;
// u_mode 0: identity. 1: the effects: the haze (u_haze > 0: engine.hd2d.haze), then the grade and the vignette
// (u_grade 1: engine.hd2d.post.Post.uniforms).
uniform int u_mode; uniform int u_grade;
uniform vec3 u_wb; uniform float u_exposure; uniform float u_contrast; uniform float u_saturation;
uniform vec3 u_shadow_tint; uniform vec3 u_highlight_tint; uniform float u_split; uniform float u_protect;
uniform float u_vignette;
// the haze: its strength, its lit colour (linear), where it begins and how far it takes (m along the view axis), and
// the camera's clip planes to read the depth buffer in metres (engine.hd2d.dof's linearisation)
uniform float u_haze; uniform vec3 u_haze_color; uniform float u_haze_onset; uniform float u_haze_falloff;
uniform int u_ortho; uniform float u_near; uniform float u_far;
in vec2 v_uv; out vec4 f_color;
float view_depth(float d) {
    if (u_ortho == 1) return u_near + d * (u_far - u_near);
    return u_near * u_far / (u_far - d * (u_far - u_near));
}
vec3 lin(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
vec3 enc(vec3 l) { l = clamp(l, 0.0, 1.0); return mix(l * 12.92, 1.055 * pow(l, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, l)); }
float luma(vec3 l) { return dot(l, vec3(0.2126, 0.7152, 0.0722)); }
void main() {
    ivec2 size = textureSize(u_color, 0);
    ivec2 top = size - 1;
    ivec2 px = clamp(ivec2(floor(v_uv * vec2(size))), ivec2(0), top);
    vec4 c = texelFetch(u_color, px, 0);
    if (u_mode == 0) { f_color = c; return; }
    float a = 0.0;
    float d = texelFetch(u_depth, px, 0).r;
    if (u_haze > 0.0 && d < 1.0) {  // (nothing drawn there: the room's backdrop, not distant scenery: never hazed)
        float x = max(view_depth(d) - u_haze_onset, 0.0) / u_haze_falloff;  // no corner at the onset: no edge
        a = u_haze * (1.0 - exp(-3.0 * x * x));
    }
    if (u_grade == 0 && a <= 0.0) { f_color = c; return; }  // nearer than the haze, no grade: the texel exactly
    vec3 o = lin(c.rgb);
    if (a > 0.0) o = mix(o, u_haze_color, a);             // in linear light, before the grade
    if (u_grade == 0) { f_color = vec4(enc(o), c.a); return; }
    vec3 g = o * u_wb * u_exposure;
    float y0 = luma(o);
    float y = max(luma(g), 1e-5);
    float y2 = 0.18 * pow(y / 0.18, u_contrast);         // contrast on luminance, about mid-grey
    float m = max(y0, 0.8);
    if (y2 > m) y2 = m + (y2 - m) / (1.0 + (y2 - m) * 4.0);  // soft shoulder over what was there: no clipping added
    g *= y2 / y;
    float yy = luma(g);
    g = mix(vec3(yy), g, u_saturation);
    float t = clamp(yy / 0.36, 0.0, 1.0);                 // split toning: shadows -> highlights
    g *= mix(vec3(1.0), mix(u_shadow_tint, u_highlight_tint, t), u_split);
    float keep = u_protect * smoothstep(0.55, 0.95, max(max(o.r, o.g), o.b));
    g = mix(g, o, keep);                                   // the brightest pixels keep their own colour
    vec3 soft = 0.9 + (g - 0.9) / (1.0 + (g - 0.9) * 10.0);  // a channel pushed past 0.9 eases toward 1: no new clip
    g = mix(g, max(soft, o), vec3(greaterThan(g, max(o, vec3(0.9)))));
    vec2 q = (vec2(px) + 0.5) / vec2(size) - 0.5;
    q.x *= float(size.x) / float(size.y);                  // a circle in the picture
    float r = length(q) / length(vec2(0.5 * float(size.x) / float(size.y), 0.5));  // 0 centre, 1 corner
    g *= 1.0 - u_vignette * smoothstep(0.55, 1.05, r);
    f_color = vec4(enc(g), c.a);
}
"""


class FinalComposite:
    """The composite pass: one program, drawn with the renderer's own full-picture quad, and (only while the depth of
    field runs before it) one colour target the picture's size."""

    def __init__(self, ctx: Any, vertex_shader: str) -> None:
        self.ctx = ctx
        self.program = ctx.program(vertex_shader=vertex_shader, fragment_shader=COMPOSITE_FS)
        self._chain: tuple[Any, Any] | None = None  # (framebuffer, its colour texture)
        self.chain_allocations = 0  # how many times a chain target was made (resizes make a new one)
        self.program["u_color"] = 0
        self.program.set_uniform_safe("u_depth", 1)
        self.program["u_mode"] = 0
        from engine.hd2d.dof import FAR, NEAR  # noqa: PLC0415  # (the renderer's clip planes)

        for name, value in (("u_grade", 0), ("u_haze", 0.0), ("u_near", NEAR), ("u_far", FAR), ("u_ortho", 0),
                            ("u_haze_onset", 0.0)):
            self.program.set_uniform_safe(name, value)
        self._configured: Any = (None, None)  # the Post and haze values its uniforms were last set for
        self.uniform_updates = 0  # how many times they were set (once per change of the room's settings)
        self._frame: tuple[float, int] | None = None  # the haze's onset and the camera's kind, last set

    def configure(self, post: Any, haze: dict[str, Any] | None = None) -> None:
        """The pass's mode: ``post`` (an active engine.hd2d.post.Post) grades with it; ``haze`` (engine.hd2d.haze
        .uniforms, of an active haze) hazes first; neither is the identity. Its uniforms are set only when that
        changes (the room's settings are one object until they're edited; the haze's values compare equal)."""
        if post is self._configured[0] and haze == self._configured[1]:
            return
        p = self.program
        if post is not None:
            for name, value in post.uniforms().items():
                p[name] = value
        p["u_grade"] = 1 if post is not None else 0
        if haze is not None:
            for name, value in haze.items():
                p[name] = value
        else:
            p.set_uniform_safe("u_haze", 0.0)
        p["u_mode"] = 1 if post is not None or haze is not None else 0
        self._configured = (post, haze)
        self.uniform_updates += 1

    def frame(self, onset: float, ortho: bool) -> None:
        """This frame's haze onset (m along the view axis) and camera kind: set only when they change."""
        key = (onset, 1 if ortho else 0)
        if key != self._frame:
            self.program["u_haze_onset"] = onset
            self.program["u_ortho"] = key[1]
            self._frame = key

    def chain_target(self, size: tuple[int, int]) -> tuple[Any, Any]:
        """(framebuffer, colour texture) the depth of field draws into when the composite follows it: RGBA8 like the
        world's colour, ``size`` (the picture's), Nearest; made once, remade on a new size."""
        if self._chain is not None and tuple(self._chain[1].size) == tuple(size):
            return self._chain
        self._free_chain()
        ctx = self.ctx
        colour = ctx.texture(size, components=4)
        try:
            fbo = ctx.framebuffer(color_attachments=[colour])
        except BaseException:
            colour.delete()
            raise
        colour.filter = (ctx.NEAREST, ctx.NEAREST)
        self._chain = (fbo, colour)
        self.chain_allocations += 1
        return self._chain

    def render(self, quad: Any, colour: Any, depth: Any) -> None:
        """Draw the picture from ``colour`` (and ``depth``) into the active framebuffer (its viewport set by the
        caller, blending off)."""
        p = self.program
        colour.use(0)
        depth.use(1)
        quad.render(p)
        from pyglet import gl as raw  # noqa: PLC0415  # (arcade has no unbind)

        raw.glActiveTexture(raw.GL_TEXTURE1)  # the world's depth isn't left bound where the next frame draws into it
        raw.glBindTexture(raw.GL_TEXTURE_2D, 0)
        raw.glActiveTexture(raw.GL_TEXTURE0)

    def gl_objects(self) -> list[Any]:
        return [self.program, *(self._chain or ())]

    def _free_chain(self) -> None:
        if self._chain is not None:
            fbo, colour = self._chain
            fbo.delete()
            colour.delete()
            self._chain = None

    def release(self) -> None:
        self._free_chain()
        self.program.delete()


def final_stage(*, dof: bool, composite: bool) -> str:
    """What makes the picture this frame: "blit", "dof", "composite" or "dof+composite"."""
    if composite:
        return "dof+composite" if dof else "composite"
    return "dof" if dof else "blit"


def overlay_after(stage: str) -> bool:
    """Whether Studio's lines are drawn after the picture is made (sharp, untouched by the pass) rather than into the
    world before the blit: every stage but the plain blit."""
    return stage != "blit"


__all__ = ["COMPOSITE_FS", "FinalComposite", "final_stage", "overlay_after"]
