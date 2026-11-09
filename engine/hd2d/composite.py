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

L4-1 only has the **identity** composite: it writes each world texel exactly (``texelFetch``: no filtering, no colour
conversion, alpha kept), so turning it on changes no pixel. It exists to carry the effects L4-2 adds; in this PR it
is reached only through ``Hd2dRenderer.force_identity_composite`` (a test/diagnostic switch, not a setting: nothing
is saved, nothing shows in Studio).

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
in vec2 v_uv; out vec4 f_color;
void main() {
    ivec2 top = textureSize(u_color, 0) - 1;
    ivec2 px = clamp(ivec2(floor(v_uv * vec2(top + 1))), ivec2(0), top);
    f_color = texelFetch(u_color, px, 0);
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
        p["u_color"] = 0
        p.set_uniform_safe("u_depth", 1)
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
