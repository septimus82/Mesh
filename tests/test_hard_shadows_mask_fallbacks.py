from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from engine.lighting import LightManager


def test_render_shadow_mask_returns_texture_on_fbo_failure() -> None:
    from engine.lighting.shadows import Viewport, render_shadow_mask

    sentinel_tex = object()

    class _Ctx:
        def clear(self, *_args):  # noqa: ANN003
            return None

        def program(self, **_kwargs):  # noqa: ANN003
            raise RuntimeError("compile failed")

    class _Fbo:
        def activate(self):
            class _CM:
                def __enter__(self_inner):  # noqa: ANN001
                    return None

                def __exit__(self_inner, exc_type, exc, tb):  # noqa: ANN001
                    return False

            return _CM()

    tex = render_shadow_mask(
        renderer=SimpleNamespace(ctx=_Ctx()),
        polygons=[[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]],
        viewport=Viewport(x=0.0, y=0.0, width=64.0, height=64.0),
        target_texture=sentinel_tex,
        target_fbo=_Fbo(),
    )
    assert tex is sentinel_tex
