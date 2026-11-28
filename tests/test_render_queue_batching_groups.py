from __future__ import annotations

import pytest

from engine.render_queue import DrawSpriteCmd, SpriteDrawList


def test_render_queue_batching_groups() -> None:
    draw_list = SpriteDrawList()
    draw_list.submit(
        DrawSpriteCmd(
            texture_key="tex_a",
            x=0.0,
            y=0.0,
            scale=1.0,
            alpha=255.0,
            rotation=0.0,
            layer=0,
            blend_mode="normal",
        )
    )
    draw_list.submit(
        DrawSpriteCmd(
            texture_key="tex_b",
            x=1.0,
            y=1.0,
            scale=1.0,
            alpha=200.0,
            rotation=0.0,
            layer=0,
            blend_mode="normal",
        )
    )
    draw_list.submit(
        DrawSpriteCmd(
            texture_key="tex_a",
            x=2.0,
            y=2.0,
            scale=1.0,
            alpha=180.0,
            rotation=0.0,
            layer=1,
            blend_mode="normal",
        )
    )
    draw_list.submit(
        DrawSpriteCmd(
            texture_key="tex_a",
            x=3.0,
            y=3.0,
            scale=1.0,
            alpha=160.0,
            rotation=0.0,
            layer=0,
            blend_mode="additive",
        )
    )

    batches = draw_list.build_batches()
    keys = [(key.layer, key.blend_mode, key.texture_key) for key, _ in batches]
    assert keys == [
        (0, "normal", "tex_a"),
        (0, "normal", "tex_b"),
        (1, "normal", "tex_a"),
        (0, "additive", "tex_a"),
    ]
    assert [len(cmds) for _, cmds in batches] == [1, 1, 1, 1]


@pytest.mark.fast
def test_batching_keeps_depth_order_when_a_texture_repeats() -> None:
    """Found by the capability lab: two sprites sharing a texture were batched together and both
    drawn before a different sprite that sits between them in depth (y-sort)."""

    def cmd(texture: str, y: float) -> DrawSpriteCmd:
        return DrawSpriteCmd(texture_key=texture, x=0.0, y=y, scale=1.0, alpha=255.0, rotation=0.0, layer=0,
                             blend_mode="normal")

    draw_list = SpriteDrawList()
    for c in (cmd("red", 250.0), cmd("blue", 230.0), cmd("red", 210.0), cmd("red", 200.0)):
        draw_list.submit(c)
    batches = draw_list.build_batches()
    assert [(key.texture_key, [c.y for c in cmds]) for key, cmds in batches] == [
        ("red", [250.0]), ("blue", [230.0]), ("red", [210.0, 200.0])]
