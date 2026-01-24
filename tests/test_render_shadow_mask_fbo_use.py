from __future__ import annotations

from types import SimpleNamespace

from engine.lighting.shadows import Viewport, render_shadow_mask


def test_render_shadow_mask_fbo_use_calls_use_and_returns_texture(monkeypatch) -> None:
    sentinel_tex = object()
    drawn: list[tuple[int, int]] = []

    import arcade

    def _draw_polygon_filled(points, color):  # noqa: ANN001,ARG001
        drawn.append((len(points), int(color[3]) if isinstance(color, (list, tuple)) and len(color) >= 4 else -1))

    monkeypatch.setattr(arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)

    class _Ctx:
        def clear(self, *_args):  # noqa: ANN003
            return None

    class _Fbo:
        def __init__(self) -> None:
            self.used = False
            self.clears: list[tuple[float, float, float, float] | tuple[()]] = []

        def use(self) -> None:
            self.used = True

        def clear(self, *args):  # noqa: ANN002
            self.clears.append(tuple(args))

    fbo = _Fbo()

    tex = render_shadow_mask(
        renderer=SimpleNamespace(ctx=_Ctx()),
        polygons=[[(10.0, 10.0), (20.0, 10.0), (15.0, 20.0)]],
        viewport=Viewport(x=0.0, y=0.0, width=64.0, height=64.0),
        target_texture=sentinel_tex,
        target_fbo=fbo,
    )

    assert fbo.used is True
    assert tex is sentinel_tex

