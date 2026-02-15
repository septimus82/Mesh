"""Tests for the post-processing pipeline."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch, call

import pytest

pytestmark = [pytest.mark.fast]

# ---------------------------------------------------------------------------
# Helpers to build lightweight mocks of Arcade GL resources
# ---------------------------------------------------------------------------


def _make_ctx():
    """Return a mock OpenGL context with texture/framebuffer/program factories."""
    ctx = MagicMock()

    def _make_texture(size, components=4):
        tex = MagicMock()
        tex.size = size
        tex.components = components
        return tex

    def _make_fbo(color_attachments=None):
        fbo = MagicMock()
        fbo.color_attachments = color_attachments or []
        return fbo

    def _make_program(**kwargs):
        prog = MagicMock()
        prog.members = {}
        # Support dict-style uniform assignment
        _uniforms: dict = {}
        prog.__setitem__ = lambda self, k, v: _uniforms.__setitem__(k, v)
        prog.__getitem__ = lambda self, k: _uniforms.get(k)
        return prog

    ctx.texture = _make_texture
    ctx.framebuffer = _make_fbo
    ctx.program = _make_program
    return ctx


def _make_window(width=800, height=600):
    """Return a mock GameWindow with ctx and .use()."""
    window = MagicMock()
    window.width = width
    window.height = height
    window.ctx = _make_ctx()
    return window


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from engine.post_processing import (
    PostProcessEffect,
    PostProcessPipeline,
    Vignette,
    ColorGrading,
    ScreenFade,
    CRTEffect,
)


# ===========================================================================
# PostProcessEffect base
# ===========================================================================


class TestPostProcessEffectBase:
    def test_fragment_source_not_implemented(self):
        e = PostProcessEffect()
        with pytest.raises(NotImplementedError):
            _ = e.fragment_source

    def test_uniforms_default_empty(self):
        e = PostProcessEffect()
        assert e.uniforms() == {}


# ===========================================================================
# Vignette
# ===========================================================================


class TestVignette:
    def test_defaults(self):
        v = Vignette()
        assert v.name == "vignette"
        assert v.enabled is True
        assert v.strength == 0.4
        assert v.radius == 0.75

    def test_custom_params(self):
        v = Vignette(strength=0.8, radius=0.5)
        assert v.strength == 0.8
        assert v.radius == 0.5

    def test_uniforms(self):
        v = Vignette(strength=0.6, radius=0.9)
        u = v.uniforms()
        assert u["u_strength"] == 0.6
        assert u["u_radius"] == 0.9

    def test_fragment_source_is_glsl(self):
        v = Vignette()
        src = v.fragment_source
        assert "#version 330" in src
        assert "u_strength" in src
        assert "u_radius" in src


# ===========================================================================
# ColorGrading
# ===========================================================================


class TestColorGrading:
    def test_defaults(self):
        cg = ColorGrading()
        assert cg.brightness == 1.0
        assert cg.contrast == 1.0
        assert cg.saturation == 1.0

    def test_uniforms(self):
        cg = ColorGrading(brightness=1.2, contrast=0.9, saturation=1.1)
        u = cg.uniforms()
        assert u["u_brightness"] == 1.2
        assert u["u_contrast"] == 0.9
        assert u["u_saturation"] == 1.1


# ===========================================================================
# ScreenFade
# ===========================================================================


class TestScreenFade:
    def test_defaults(self):
        sf = ScreenFade()
        assert sf.fade_amount == 0.0
        assert sf.fade_color == (0.0, 0.0, 0.0)

    def test_uniforms(self):
        sf = ScreenFade(fade_color=(1.0, 0.0, 0.0), fade_amount=0.5)
        u = sf.uniforms()
        assert u["u_fade_color"] == (1.0, 0.0, 0.0)
        assert u["u_fade_amount"] == 0.5


# ===========================================================================
# CRTEffect
# ===========================================================================


class TestCRTEffect:
    def test_defaults(self):
        crt = CRTEffect()
        assert crt.scanline_intensity == 0.15
        assert crt.curvature == 0.02

    def test_uniforms(self):
        crt = CRTEffect(scanline_intensity=0.3, curvature=0.05)
        u = crt.uniforms()
        assert u["u_scanline_intensity"] == 0.3
        assert u["u_curvature"] == 0.05

    def test_fragment_source_has_resolution(self):
        crt = CRTEffect()
        assert "u_resolution" in crt.fragment_source


# ===========================================================================
# PostProcessPipeline
# ===========================================================================


class TestPipelineBasic:
    def test_empty_pipeline(self):
        pp = PostProcessPipeline()
        assert pp.effects == []
        assert pp.has_active_effects is False

    def test_add_remove_effect(self):
        pp = PostProcessPipeline()
        v = Vignette()
        pp.add_effect(v)
        assert pp.has_active_effects is True
        assert len(pp.effects) == 1

        assert pp.remove_effect("vignette") is True
        assert pp.effects == []
        assert pp.remove_effect("vignette") is False

    def test_get_effect(self):
        pp = PostProcessPipeline()
        v = Vignette()
        pp.add_effect(v)
        assert pp.get_effect("vignette") is v
        assert pp.get_effect("nonexistent") is None

    def test_disabled_effect_not_active(self):
        pp = PostProcessPipeline()
        v = Vignette()
        v.enabled = False
        pp.add_effect(v)
        assert pp.has_active_effects is False


class TestPipelineBeginEnd:
    """Test the begin/end lifecycle with mock GL resources."""

    def test_begin_noop_without_effects(self):
        pp = PostProcessPipeline()
        window = _make_window()
        pp.begin(window)
        # No FBO created
        assert pp._targets is None
        assert pp._active is False

    def test_begin_creates_targets(self):
        pp = PostProcessPipeline()
        pp.add_effect(Vignette())
        window = _make_window()
        pp.begin(window)
        assert pp._active is True
        assert pp._targets is not None
        assert pp._targets.width == 800
        assert pp._targets.height == 600
        assert pp._targets.fbo_a.use.called
        assert pp._targets.fbo_a.clear.called

    def test_end_without_begin_is_noop(self):
        pp = PostProcessPipeline()
        window = _make_window()
        pp.end(window)  # should not raise

    def test_begin_end_cycle_renders(self):
        """Verify that end() calls window.use() and renders via quad."""
        pp = PostProcessPipeline()
        pp.add_effect(Vignette())
        window = _make_window()

        # Patch quad creation
        mock_quad = MagicMock()
        with patch("engine.post_processing.PostProcessPipeline._ensure_quad", return_value=mock_quad):
            pp.begin(window)
            pp.end(window)

        window.use.assert_called()
        mock_quad.render.assert_called_once()

    def test_resize_recreates_targets(self):
        pp = PostProcessPipeline()
        pp.add_effect(Vignette())
        window = _make_window(800, 600)
        pp.begin(window)
        old_targets = pp._targets
        pp.end(window)

        # Resize
        window.width = 1024
        window.height = 768
        pp.begin(window)
        assert pp._targets is not old_targets
        assert pp._targets.width == 1024

    def test_multiple_effects_ping_pong(self):
        """Chain two effects; second reads from tex_b."""
        pp = PostProcessPipeline()
        pp.add_effect(Vignette())
        pp.add_effect(ColorGrading())
        window = _make_window()

        mock_quad = MagicMock()
        with patch("engine.post_processing.PostProcessPipeline._ensure_quad", return_value=mock_quad):
            pp.begin(window)
            pp.end(window)

        # quad.render should have been called twice (once per effect)
        assert mock_quad.render.call_count == 2

    def test_zero_size_window(self):
        """Pipeline gracefully handles zero-size window."""
        pp = PostProcessPipeline()
        pp.add_effect(Vignette())
        window = _make_window(0, 0)
        pp.begin(window)
        assert pp._active is False


class TestPipelineEdgeCases:
    def test_ctx_unavailable(self):
        """Pipeline is a no-op when ctx is None."""
        pp = PostProcessPipeline()
        pp.add_effect(Vignette())
        window = MagicMock()
        window.width = 800
        window.height = 600
        window.ctx = None
        # Also block the fallback path through optional_arcade
        with patch("engine.post_processing.PostProcessPipeline._get_ctx", return_value=None):
            pp.begin(window)
        assert pp._active is False

    def test_effect_program_caching(self):
        """get_program caches on ctx."""
        v = Vignette()
        ctx = _make_ctx()
        prog1 = v._get_program(ctx)
        prog2 = v._get_program(ctx)
        assert prog2 is prog1  # same object, cached

    def test_disabled_effect_skipped_in_chain(self):
        pp = PostProcessPipeline()
        v = Vignette()
        cg = ColorGrading()
        cg.enabled = False
        pp.add_effect(v)
        pp.add_effect(cg)
        window = _make_window()

        mock_quad = MagicMock()
        with patch("engine.post_processing.PostProcessPipeline._ensure_quad", return_value=mock_quad):
            pp.begin(window)
            pp.end(window)

        # Only 1 render call (vignette), ColorGrading is disabled
        assert mock_quad.render.call_count == 1


# ===========================================================================
# Integration with tick.on_draw
# ===========================================================================


class TestTickIntegration:
    """Verify tick.on_draw calls begin/end on the pipeline."""

    def test_on_draw_calls_pipeline(self):
        """on_draw should invoke pp.begin before drawing and pp.end after."""
        from engine.game_runtime import tick

        window = MagicMock()
        window.show_debug = False
        window.ai_debug_overlay_enabled = False
        window.engine_config.debug_mode = False
        window.game_over = False

        # Create a real pipeline and spy on begin/end
        pp = PostProcessPipeline()
        pp.begin = MagicMock()
        pp.end = MagicMock()
        window.post_process_pipeline = pp

        # Mock lighting as disabled
        window.lighting = None
        window.fog_overlay = None
        window.render_queue = None

        import os
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MESH_SHADOWCAST_DEBUG", None)
            tick.on_draw(window)

        pp.begin.assert_called_once_with(window)
        pp.end.assert_called_once_with(window)

    def test_on_draw_no_pipeline(self):
        """on_draw should handle missing pipeline gracefully."""
        from engine.game_runtime import tick

        window = MagicMock()
        window.show_debug = False
        window.ai_debug_overlay_enabled = False
        window.engine_config.debug_mode = False
        window.game_over = False
        window.post_process_pipeline = None
        window.lighting = None
        window.fog_overlay = None
        window.render_queue = None

        import os
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MESH_SHADOWCAST_DEBUG", None)
            tick.on_draw(window)  # should not raise
