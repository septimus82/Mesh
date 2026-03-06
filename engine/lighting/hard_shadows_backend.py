from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import engine.optional_arcade as optional_arcade


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


@dataclass(slots=True)
class HardShadowsTargets:
    width: int
    height: int
    light_tex: Any
    light_fbo: Any
    mask_tex: Any
    mask_fbo: Any


def ensure_render_targets(window: Any, size: tuple[int, int]) -> HardShadowsTargets | None:
    """
    Create (or reuse) framebuffer-backed render targets for hard-shadow compositing.

    Returns a target framebuffer/texture suitable for passing to Arcade 3.x LightLayer.draw(target=...).
    """
    if optional_arcade.arcade is None:  # pragma: no cover
        return None

    w, h = int(size[0]), int(size[1])
    if w <= 0 or h <= 0:
        return None

    existing = getattr(window, "_mesh_hard_shadows_targets", None)
    if isinstance(existing, HardShadowsTargets) and existing.width == w and existing.height == h:
        return existing

    ctx = getattr(window, "ctx", None)
    if ctx is None:
        try:
            win = optional_arcade.arcade.get_window()
            ctx = getattr(win, "ctx", None)
        except Exception:  # noqa: BLE001
            ctx = None
    if ctx is None:
        return None

    try:
        light_tex = ctx.texture((w, h), components=4)
        light_fbo = ctx.framebuffer(color_attachments=[light_tex])
        mask_tex = ctx.texture((w, h), components=4)
        mask_fbo = ctx.framebuffer(color_attachments=[mask_tex])
    except Exception:  # noqa: BLE001
        return None

    targets = HardShadowsTargets(
        width=w,
        height=h,
        light_tex=light_tex,
        light_fbo=light_fbo,
        mask_tex=mask_tex,
        mask_fbo=mask_fbo,
    )
    setattr(window, "_mesh_hard_shadows_targets", targets)
    return targets


def composite_to_window(
    window: Any,
    *,
    diffuse_tex: Any,
    light_tex: Any,
    mask_tex: Any,
    ambient_color: tuple[int, int, int, int],
) -> bool:
    """
    Composite hard shadows with the light buffer (Arcade 3.x) using a full-screen quad.

    Convention:
    - `mask_tex` is white=lit, black=shadow
    - `light_tex` is the LightLayer output (already includes ambient + lights)
    - output = ambient_part + (lit - ambient_part) * mask
    """
    ctx = getattr(window, "ctx", None)
    if ctx is None:
        return False

    if optional_arcade.arcade is None:  # pragma: no cover
        return False

    if diffuse_tex is None or light_tex is None or mask_tex is None:
        return False

    try:
        quad = getattr(window, "_mesh_hard_shadows_quad", None)
        if quad is None:
            quad = optional_arcade.arcade.gl.geometry.quad_2d_fs()
            setattr(window, "_mesh_hard_shadows_quad", quad)

        program = getattr(window, "_mesh_hard_shadows_program", None)
        if program is None:
            program = ctx.program(
                vertex_shader="""
                #version 330
                in vec2 in_vert;
                in vec2 in_uv;
                out vec2 v_uv;
                void main() {
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                    v_uv = in_uv;
                }
                """,
                fragment_shader="""
                #version 330
                uniform sampler2D diffuse_tex;
                uniform sampler2D light_tex;
                uniform sampler2D mask_tex;
                uniform vec3 ambient;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() {
                    vec4 diffuse = texture(diffuse_tex, v_uv);
                    vec3 lit_rgb = texture(light_tex, v_uv).rgb;
                    float m = texture(mask_tex, v_uv).r;
                    vec3 ambient_part = diffuse.rgb * ambient;
                    vec3 light_part = max(lit_rgb - ambient_part, vec3(0.0));
                    vec3 out_rgb = ambient_part + light_part * m;
                    fragColor = vec4(out_rgb, diffuse.a);
                }
                """,
            )
            setattr(window, "_mesh_hard_shadows_program", program)

        ambient = (
            float(ambient_color[0]) / 255.0,
            float(ambient_color[1]) / 255.0,
            float(ambient_color[2]) / 255.0,
        )
        program["ambient"] = ambient

        try:
            diffuse_tex.use(0)
            light_tex.use(1)
            mask_tex.use(2)
        except Exception:  # noqa: BLE001
            return False

        program["diffuse_tex"] = 0
        program["light_tex"] = 1
        program["mask_tex"] = 2

        try:
            window.use()
        except Exception:  # noqa: BLE001
            _log_swallow("HARD-001", "engine/lighting/hard_shadows_backend.py pass-only blanket swallow")
            pass
        quad.render(program)
        return True
    except Exception:  # noqa: BLE001
        return False
