from __future__ import annotations

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
