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
// u_mode 0: identity. 1: the grade and the vignette (engine.hd2d.post.Post.uniforms).
uniform int u_mode;
uniform vec3 u_wb; uniform float u_exposure; uniform float u_contrast; uniform float u_saturation;
uniform vec3 u_shadow_tint; uniform vec3 u_highlight_tint; uniform float u_split; uniform float u_protect;
uniform float u_vignette;
in vec2 v_uv; out vec4 f_color;
vec3 lin(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
vec3 enc(vec3 l) { l = clamp(l, 0.0, 1.0); return mix(l * 12.92, 1.055 * pow(l, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, l)); }
float luma(vec3 l) { return dot(l, vec3(0.2126, 0.7152, 0.0722)); }
void main() {
    ivec2 size = textureSize(u_color, 0);
    ivec2 top = size - 1;
    ivec2 px = clamp(ivec2(floor(v_uv * vec2(size))), ivec2(0), top);
    vec4 c = texelFetch(u_color, px, 0);
    if (u_mode == 0) { f_color = c; return; }
    vec3 o = lin(c.rgb);
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
        self._configured: Any = None  # the Post its grade uniforms were last set for (None: identity)
        self.uniform_updates = 0  # how many times they were set (once per change of the room's settings)

    def configure(self, post: Any) -> None:
        """The pass's mode: ``post`` (an active engine.hd2d.post.Post) grades with it; None is the identity. Its
        uniforms are set only when that changes (the room's settings are one object until they're edited)."""
        if post is self._configured:
            return
        p = self.program
        if post is None:
            p["u_mode"] = 0
        else:
            for name, value in post.uniforms().items():
                p[name] = value
            p["u_mode"] = 1
        self._configured = post
        self.uniform_updates += 1

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
