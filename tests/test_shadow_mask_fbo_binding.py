from __future__ import annotations

from types import SimpleNamespace

from engine.lighting.shadows import Viewport, render_shadow_mask


def test_render_shadow_mask_uses_fbo_use_when_available(monkeypatch) -> None:
    import arcade

    sentinel = object()
    called: list[str] = []

    monkeypatch.setattr(arcade, "draw_polygon_filled", lambda *a, **k: called.append("draw"), raising=False)  # noqa: ARG005

    class FakeScreen:
        def use(self) -> None:
            called.append("screen.use")

    class FakeCtx:
        def __init__(self) -> None:
            self.screen = FakeScreen()

        def clear(self, *_a):  # noqa: ANN003
            called.append("ctx.clear")

    class FakeFBOUse:
        def __init__(self) -> None:
            self.used = False

        def use(self) -> None:
            self.used = True
            called.append("fbo.use")

        def clear(self, *_a):  # noqa: ANN003
            called.append("fbo.clear")

    tex = render_shadow_mask(
        renderer=SimpleNamespace(ctx=FakeCtx()),
        polygons=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
        viewport=Viewport(x=0.0, y=0.0, width=64.0, height=64.0),
        target_texture=sentinel,
        target_fbo=FakeFBOUse(),
    )
    assert tex is sentinel
    assert "fbo.use" in called
    assert "screen.use" in called


def test_render_shadow_mask_uses_fbo_activate_when_no_use(monkeypatch) -> None:
    import arcade

    sentinel = object()
    called: list[str] = []

    monkeypatch.setattr(arcade, "draw_polygon_filled", lambda *a, **k: called.append("draw"), raising=False)  # noqa: ARG005

    class FakeScreen:
        def use(self) -> None:
            called.append("screen.use")

    class FakeCtx:
        def __init__(self) -> None:
            self.screen = FakeScreen()

        def clear(self, *_a):  # noqa: ANN003
            called.append("ctx.clear")

    class FakeCM:
        def __enter__(self):  # noqa: ANN001
            called.append("activate.enter")
            return None

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            called.append("activate.exit")
            return False

    class FakeFBOActivate:
        def activate(self):  # noqa: ANN201
            called.append("fbo.activate")
            return FakeCM()

        def clear(self, *_a):  # noqa: ANN003
            called.append("fbo.clear")

    tex = render_shadow_mask(
        renderer=SimpleNamespace(ctx=FakeCtx()),
        polygons=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
        viewport=Viewport(x=0.0, y=0.0, width=64.0, height=64.0),
        target_texture=sentinel,
        target_fbo=FakeFBOActivate(),
    )
    assert tex is sentinel
    assert "fbo.activate" in called
    assert "activate.enter" in called
    assert "activate.exit" in called
    assert "screen.use" in called


def test_render_shadow_mask_returns_none_without_use_or_activate() -> None:
    sentinel = object()

    class FakeCtx:
        pass

    class FakeFBO:
        pass

    tex = render_shadow_mask(
        renderer=SimpleNamespace(ctx=FakeCtx()),
        polygons=[],
        viewport=Viewport(x=0.0, y=0.0, width=64.0, height=64.0),
        target_texture=sentinel,
        target_fbo=FakeFBO(),
    )
    assert tex is None

