from __future__ import annotations

from types import SimpleNamespace

from engine.lighting.shadows import Viewport, render_shadow_mask


def test_render_shadow_mask_uses_fbo_use_when_no_activate() -> None:
    sentinel_tex = object()

    class _Ctx:
        def clear(self, *_args):  # noqa: ANN003
            return None

        def program(self, **_kwargs):  # noqa: ANN003
            class _Prog:
                def __setitem__(self, _k, _v):  # noqa: ANN001
                    return None

            return _Prog()

    class _Fbo:
        def __init__(self) -> None:
            self.used = False

        def use(self) -> None:
            self.used = True

    fbo = _Fbo()
    tex = render_shadow_mask(
        renderer=SimpleNamespace(ctx=_Ctx(), show_debug=False),
        polygons=[],
        viewport=Viewport(x=0.0, y=0.0, width=64.0, height=64.0),
        target_texture=sentinel_tex,
        target_fbo=fbo,
    )
    assert fbo.used is True
    assert tex is sentinel_tex

