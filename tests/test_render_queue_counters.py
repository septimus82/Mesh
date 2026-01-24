from __future__ import annotations

from engine.render_queue import DrawSpriteCmd, RenderQueueStats, SpriteRenderQueue, estimate_batch_stats


class _StubRenderer:
    available = True

    def draw(self, draw_list):  # noqa: ANN001
        return estimate_batch_stats(draw_list)


def test_render_queue_counters() -> None:
    queue = SpriteRenderQueue(_StubRenderer())
    queue.begin_frame()

    queue.submit(
        DrawSpriteCmd(
            texture_key="tex_a",
            x=0.0,
            y=0.0,
            scale=1.0,
            alpha=255.0,
            rotation=0.0,
            layer=0,
        )
    )
    queue.submit(
        DrawSpriteCmd(
            texture_key="tex_b",
            x=1.0,
            y=1.0,
            scale=1.0,
            alpha=255.0,
            rotation=0.0,
            layer=0,
        )
    )
    stats_a = queue.flush()
    assert isinstance(stats_a, RenderQueueStats)

    queue.submit(
        DrawSpriteCmd(
            texture_key="tex_b",
            x=2.0,
            y=2.0,
            scale=1.0,
            alpha=255.0,
            rotation=0.0,
            layer=1,
        )
    )
    queue.flush()

    assert queue.stats.sprites_submitted == 3
    assert queue.stats.batches_drawn == 3
    assert queue.stats.draw_calls_estimate == 3
    assert queue.stats.sprites_drawn == 3
