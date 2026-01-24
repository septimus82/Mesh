from __future__ import annotations


def test_hard_shadows_backend_headless_safe() -> None:
    from engine.lighting.hard_shadows_backend import composite_to_window, ensure_render_targets

    class _Window:
        width = 320
        height = 200
        ctx = None

        def use(self) -> None:  # pragma: no cover
            return

    window = _Window()
    assert ensure_render_targets(window, (window.width, window.height)) is None
    assert (
        composite_to_window(
            window,
            diffuse_tex=object(),
            light_tex=object(),
            mask_tex=object(),
            ambient_color=(10, 10, 10, 255),
        )
        is False
    )

