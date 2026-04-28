"""Post-processing pipeline for screen-space visual effects.

Provides a composable chain of full-screen shader effects (vignette,
color grading, screen fade, CRT scanlines) that run after world-space
rendering but before GUI overlay drawing.

Usage::

    pp = PostProcessPipeline()
    pp.add_effect(Vignette(strength=0.4))
    pp.add_effect(ColorGrading(brightness=1.1, contrast=1.05))

    # in on_draw():
    pp.begin(window)        # redirect drawing to offscreen FBO
    ... draw world ...
    pp.end(window)          # blit through effect chain back to screen
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.arcade_compat import activate_framebuffer, clear_framebuffer, close_framebuffer_activation
from engine.logging_tools import get_logger
from engine.swallowed_exceptions import _log_swallow


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Base effect
# ---------------------------------------------------------------------------

class PostProcessEffect:
    """Base class for a single post-processing effect.

    Subclasses must provide *fragment_source* (a ``#version 330`` GLSL
    fragment shader) and may override *uniforms()* to push per-frame
    parameters.  The vertex shader is always a simple full-screen quad.
    """

    name: str = "base"
    enabled: bool = True

    # Subclasses override ------------------------------------------------

    @property
    def fragment_source(self) -> str:  # pragma: no cover
        raise NotImplementedError

    def uniforms(self) -> Dict[str, Any]:
        """Return uniform name → value pairs for the current frame."""
        return {}

    # Internal -----------------------------------------------------------

    _VERTEX_SOURCE: str = """
    #version 330
    in vec2 in_vert;
    in vec2 in_uv;
    out vec2 v_uv;
    void main() {
        gl_Position = vec4(in_vert, 0.0, 1.0);
        v_uv = in_uv;
    }
    """

    def _get_program(self, ctx: Any) -> Any:
        """Compile (and cache) the shader program."""
        key = f"_mesh_pp_{self.name}_program"
        prog = getattr(ctx, key, None)
        if prog is None:
            prog = ctx.program(
                vertex_shader=self._VERTEX_SOURCE,
                fragment_shader=self.fragment_source,
            )
            setattr(ctx, key, prog)
        return prog


# ---------------------------------------------------------------------------
# Built-in effects
# ---------------------------------------------------------------------------

@dataclass
class Vignette(PostProcessEffect):
    """Darkens screen edges for a cinematic look."""

    name: str = "vignette"
    strength: float = 0.4
    radius: float = 0.75

    @property
    def fragment_source(self) -> str:
        return """
        #version 330
        uniform sampler2D u_texture;
        uniform float u_strength;
        uniform float u_radius;
        in vec2 v_uv;
        out vec4 fragColor;
        void main() {
            vec4 color = texture(u_texture, v_uv);
            float dist = distance(v_uv, vec2(0.5));
            float vig = smoothstep(u_radius, u_radius - 0.45, dist);
            color.rgb *= mix(1.0, vig, u_strength);
            fragColor = color;
        }
        """

    def uniforms(self) -> Dict[str, Any]:
        return {"u_strength": self.strength, "u_radius": self.radius}


@dataclass
class ColorGrading(PostProcessEffect):
    """Brightness / contrast / saturation adjustment."""

    name: str = "color_grading"
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0

    @property
    def fragment_source(self) -> str:
        return """
        #version 330
        uniform sampler2D u_texture;
        uniform float u_brightness;
        uniform float u_contrast;
        uniform float u_saturation;
        in vec2 v_uv;
        out vec4 fragColor;
        void main() {
            vec4 color = texture(u_texture, v_uv);
            // Brightness
            color.rgb *= u_brightness;
            // Contrast (pivot at 0.5)
            color.rgb = (color.rgb - 0.5) * u_contrast + 0.5;
            // Saturation
            float luma = dot(color.rgb, vec3(0.2126, 0.7152, 0.0722));
            color.rgb = mix(vec3(luma), color.rgb, u_saturation);
            fragColor = color;
        }
        """

    def uniforms(self) -> Dict[str, Any]:
        return {
            "u_brightness": self.brightness,
            "u_contrast": self.contrast,
            "u_saturation": self.saturation,
        }


@dataclass
class ScreenFade(PostProcessEffect):
    """Fade the screen toward a solid colour (useful for scene transitions)."""

    name: str = "screen_fade"
    fade_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fade_amount: float = 0.0  # 0 = no fade, 1 = fully opaque

    @property
    def fragment_source(self) -> str:
        return """
        #version 330
        uniform sampler2D u_texture;
        uniform vec3 u_fade_color;
        uniform float u_fade_amount;
        in vec2 v_uv;
        out vec4 fragColor;
        void main() {
            vec4 color = texture(u_texture, v_uv);
            color.rgb = mix(color.rgb, u_fade_color, u_fade_amount);
            fragColor = color;
        }
        """

    def uniforms(self) -> Dict[str, Any]:
        return {
            "u_fade_color": self.fade_color,
            "u_fade_amount": self.fade_amount,
        }


@dataclass
class CRTEffect(PostProcessEffect):
    """Retro CRT scanline + slight curvature effect."""

    name: str = "crt"
    scanline_intensity: float = 0.15
    curvature: float = 0.02

    @property
    def fragment_source(self) -> str:
        return """
        #version 330
        uniform sampler2D u_texture;
        uniform vec2 u_resolution;
        uniform float u_scanline_intensity;
        uniform float u_curvature;
        in vec2 v_uv;
        out vec4 fragColor;
        void main() {
            // Barrel distortion
            vec2 uv = v_uv * 2.0 - 1.0;
            float r2 = dot(uv, uv);
            uv *= 1.0 + u_curvature * r2;
            uv = uv * 0.5 + 0.5;

            if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
                fragColor = vec4(0.0, 0.0, 0.0, 1.0);
                return;
            }

            vec4 color = texture(u_texture, uv);

            // Scanlines
            float scanline = sin(uv.y * u_resolution.y * 3.14159) * 0.5 + 0.5;
            color.rgb -= u_scanline_intensity * (1.0 - scanline);

            fragColor = color;
        }
        """

    def uniforms(self) -> Dict[str, Any]:
        return {
            "u_scanline_intensity": self.scanline_intensity,
            "u_curvature": self.curvature,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@dataclass
class _PingPongTargets:
    """Two offscreen FBOs for chaining effects."""

    width: int
    height: int
    tex_a: Any = None
    fbo_a: Any = None
    tex_b: Any = None
    fbo_b: Any = None


class PostProcessPipeline:
    """Manages a chain of :class:`PostProcessEffect` instances.

    Typical frame lifecycle::

        pipeline.begin(window)   # redirect to offscreen FBO
        ...  draw world ...
        pipeline.end(window)     # run effect chain → screen
    """

    def __init__(self) -> None:
        self.effects: List[PostProcessEffect] = []
        self._targets: Optional[_PingPongTargets] = None
        self._quad: Any = None
        self._active: bool = False
        self._begin_fbo_activation_cm: Any | None = None

    # Public API ----------------------------------------------------------

    def add_effect(self, effect: PostProcessEffect) -> None:
        """Append an effect to the chain."""
        self.effects.append(effect)

    def remove_effect(self, name: str) -> bool:
        """Remove the first effect matching *name*. Returns ``True`` if found."""
        for i, e in enumerate(self.effects):
            if e.name == name:
                self.effects.pop(i)
                return True
        return False

    def get_effect(self, name: str) -> Optional[PostProcessEffect]:
        """Return the first effect matching *name*, or ``None``."""
        for e in self.effects:
            if e.name == name:
                return e
        return None

    @property
    def has_active_effects(self) -> bool:
        """Return ``True`` if any enabled effect is in the chain."""
        return any(e.enabled for e in self.effects)

    def begin(self, window: Any) -> None:
        """Redirect subsequent draw calls into the offscreen FBO.

        When there are no active effects the call is a no-op so there is
        zero overhead when the pipeline is empty.
        """
        if not self.has_active_effects:
            return

        targets = self._ensure_targets(window)
        if targets is None:
            return

        close_framebuffer_activation(self._begin_fbo_activation_cm)
        self._begin_fbo_activation_cm = None
        backend, activation_cm = activate_framebuffer(targets.fbo_a, backend="auto")
        if backend == "none":
            return
        ctx = self._get_ctx(window)
        if ctx is None:
            close_framebuffer_activation(activation_cm)
            return
        self._active = True
        self._begin_fbo_activation_cm = activation_cm
        clear_framebuffer(ctx, targets.fbo_a, 0.0, 0.0, 0.0, 0.0)

    def end(self, window: Any) -> None:
        """Run the effect chain and blit the result to the screen."""
        if not self._active:
            return
        self._active = False
        close_framebuffer_activation(self._begin_fbo_activation_cm)
        self._begin_fbo_activation_cm = None

        targets = self._targets
        if targets is None:  # pragma: no cover - defensive
            window.use()
            return

        enabled = [e for e in self.effects if e.enabled]
        if not enabled:  # pragma: no cover
            window.use()
            self._blit_texture(window, targets.tex_a)
            return

        ctx = self._get_ctx(window)
        if ctx is None:  # pragma: no cover
            window.use()
            return

        # Ping-pong through effects
        src_tex = targets.tex_a
        for i, effect in enumerate(enabled):
            is_last = (i == len(enabled) - 1)
            pass_activation_cm: Any | None = None
            try:
                if is_last:
                    # Final effect draws directly to the screen.
                    window.use()
                else:
                    dst_fbo = targets.fbo_b if (i % 2 == 0) else targets.fbo_a
                    backend, pass_activation_cm = activate_framebuffer(dst_fbo, backend='auto')
                    if backend == 'none':
                        window.use()
                    clear_framebuffer(ctx, dst_fbo, 0.0, 0.0, 0.0, 0.0)

                program = effect._get_program(ctx)
                src_tex.use(0)
                program['u_texture'] = 0

                # Set effect-specific uniforms.
                for uname, uval in effect.uniforms().items():
                    try:
                        program[uname] = uval
                    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                        _log_swallow("POST-001", "engine/post_processing.py pass-only blanket swallow")
                        pass

                # CRT needs resolution.
                if 'u_resolution' in {
                    m.name for m in getattr(program, 'members', {}).values() if hasattr(m, 'name')
                } or effect.name == 'crt':
                    try:
                        program['u_resolution'] = (float(targets.width), float(targets.height))
                    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                        _log_swallow("POST-002", "engine/post_processing.py pass-only blanket swallow")
                        pass

                quad = self._ensure_quad(window)
                if quad is not None:
                    quad.render(program)

                # Swap source for next iteration.
                if not is_last:
                    src_tex = targets.tex_b if (i % 2 == 0) else targets.tex_a
            finally:
                close_framebuffer_activation(pass_activation_cm)

    # Internal helpers ----------------------------------------------------

    @staticmethod
    def _get_ctx(window: Any) -> Any:
        ctx = getattr(window, "ctx", None)
        if ctx is not None:
            return ctx
        try:
            from engine import optional_arcade
            win = optional_arcade.arcade.get_window()
            return getattr(win, "ctx", None)
        except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("PSPR-001", "engine/post_processing.py blanket swallow", once=True)
            return None

    def _ensure_targets(self, window: Any) -> Optional[_PingPongTargets]:
        w = getattr(window, "width", 0)
        h = getattr(window, "height", 0)
        if w <= 0 or h <= 0:
            return None

        if self._targets is not None and self._targets.width == w and self._targets.height == h:
            return self._targets

        ctx = self._get_ctx(window)
        if ctx is None:
            return None

        try:
            tex_a = ctx.texture((w, h), components=4)
            fbo_a = ctx.framebuffer(color_attachments=[tex_a])
            tex_b = ctx.texture((w, h), components=4)
            fbo_b = ctx.framebuffer(color_attachments=[tex_b])
        except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("PSPR-002", "engine/post_processing.py blanket swallow", once=True)
            logger.warning("[PostProcess] Failed to create offscreen targets")
            return None

        self._targets = _PingPongTargets(
            width=w, height=h,
            tex_a=tex_a, fbo_a=fbo_a,
            tex_b=tex_b, fbo_b=fbo_b,
        )
        return self._targets

    def _ensure_quad(self, window: Any) -> Any:
        if self._quad is not None:
            return self._quad
        try:
            from engine import optional_arcade
            self._quad = optional_arcade.arcade.gl.geometry.quad_2d_fs()
            return self._quad
        except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("PSPR-003", "engine/post_processing.py blanket swallow", once=True)
            return None

    def _blit_texture(self, window: Any, tex: Any) -> None:
        """Blit a texture to the screen with a simple passthrough shader."""
        ctx = self._get_ctx(window)
        if ctx is None:  # pragma: no cover
            return

        key = "_mesh_pp_passthrough_program"
        prog = getattr(ctx, key, None)
        if prog is None:
            prog = ctx.program(
                vertex_shader=PostProcessEffect._VERTEX_SOURCE,
                fragment_shader=self._PASSTHROUGH_FRAGMENT_SOURCE,
            )
            setattr(ctx, key, prog)

        tex.use(0)
        prog["u_texture"] = 0
        quad = self._ensure_quad(window)
        if quad is not None:
            quad.render(prog)

    _PASSTHROUGH_FRAGMENT_SOURCE: str = """
                #version 330
                uniform sampler2D u_texture;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() {
                    fragColor = texture(u_texture, v_uv);
                }
                """

    def reload_shaders(
        self,
        window: Any,
        *,
        changed_paths: tuple[str, ...] | None = None,
    ) -> dict[str, int]:
        """Best-effort shader recompilation with last-good fallback."""
        _ = changed_paths  # Reserved for richer diagnostics; compilation scope is post-process only.
        counts = {
            "shader_programs_reloaded": 0,
            "shader_programs_failed": 0,
        }
        ctx = self._get_ctx(window)
        if ctx is None:
            return counts

        for effect in self.effects:
            cache_key = f"_mesh_pp_{effect.name}_program"
            previous_program = getattr(ctx, cache_key, None)
            try:
                compiled = ctx.program(
                    vertex_shader=PostProcessEffect._VERTEX_SOURCE,
                    fragment_shader=effect.fragment_source,
                )
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("PSPR-004", "engine/post_processing.py blanket swallow", once=True)
                counts["shader_programs_failed"] += 1
                if previous_program is not None:
                    setattr(ctx, cache_key, previous_program)
                logger.warning(
                    "[PostProcess] Shader reload failed for effect '%s': %s",
                    effect.name,
                    exc,
                )
                continue
            setattr(ctx, cache_key, compiled)
            counts["shader_programs_reloaded"] += 1

        passthrough_key = "_mesh_pp_passthrough_program"
        previous_passthrough = getattr(ctx, passthrough_key, None)
        try:
            passthrough = ctx.program(
                vertex_shader=PostProcessEffect._VERTEX_SOURCE,
                fragment_shader=self._PASSTHROUGH_FRAGMENT_SOURCE,
            )
        except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("PSPR-005", "engine/post_processing.py blanket swallow", once=True)
            counts["shader_programs_failed"] += 1
            if previous_passthrough is not None:
                setattr(ctx, passthrough_key, previous_passthrough)
            logger.warning("[PostProcess] Shader reload failed for passthrough program: %s", exc)
        else:
            setattr(ctx, passthrough_key, passthrough)
            counts["shader_programs_reloaded"] += 1
        return counts
