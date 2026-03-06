from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class BatchKey:
    layer: int
    blend_mode: str
    texture_key: Any


@dataclass(slots=True)
class DrawSpriteCmd:
    texture_key: Any
    x: float
    y: float
    scale: float
    alpha: float
    rotation: float
    layer: int
    blend_mode: str = "normal"
    texture: Any | None = None
    color: Any | None = None


@dataclass(slots=True)
class RenderQueueStats:
    sprites_submitted: int = 0
    batches_drawn: int = 0
    draw_calls_estimate: int = 0
    sprites_drawn: int = 0

    def add(self, other: "RenderQueueStats") -> None:
        self.sprites_submitted += int(other.sprites_submitted)
        self.batches_drawn += int(other.batches_drawn)
        self.draw_calls_estimate += int(other.draw_calls_estimate)
        self.sprites_drawn += int(other.sprites_drawn)


@dataclass(slots=True)
class SpriteDrawList:
    commands: list[DrawSpriteCmd] = field(default_factory=list)
    sprites_submitted: int = 0

    def clear(self) -> None:
        self.commands.clear()
        self.sprites_submitted = 0

    def submit(self, cmd: DrawSpriteCmd) -> None:
        self.commands.append(cmd)
        self.sprites_submitted += 1

    def build_batches(self) -> list[tuple[BatchKey, list[DrawSpriteCmd]]]:
        batches: dict[BatchKey, list[DrawSpriteCmd]] = {}
        order: list[BatchKey] = []
        for cmd in self.commands:
            key = BatchKey(
                layer=int(cmd.layer),
                blend_mode=str(cmd.blend_mode or "normal"),
                texture_key=cmd.texture_key,
            )
            if key not in batches:
                batches[key] = []
                order.append(key)
            batches[key].append(cmd)
        return [(key, batches[key]) for key in order]


def estimate_batch_stats(draw_list: SpriteDrawList) -> RenderQueueStats:
    batches = draw_list.build_batches()
    stats = RenderQueueStats()
    stats.sprites_submitted = len(draw_list.commands)
    stats.batches_drawn = len(batches)
    stats.draw_calls_estimate = stats.batches_drawn
    stats.sprites_drawn = sum(len(cmds) for _, cmds in batches)
    return stats


class SpriteRenderQueue:
    def __init__(self, renderer: Any | None = None) -> None:
        self.renderer = renderer
        self.draw_list = SpriteDrawList()
        self.stats = RenderQueueStats()

    def is_enabled(self) -> bool:
        if self.renderer is None:
            return False
        available = getattr(self.renderer, "available", True)
        return bool(available)

    def begin_frame(self) -> None:
        self.draw_list.clear()
        self.stats = RenderQueueStats()

    def submit(self, cmd: DrawSpriteCmd) -> None:
        self.draw_list.submit(cmd)

    def flush(self) -> RenderQueueStats:
        renderer = self.renderer
        if renderer is None:
            self.draw_list.clear()
            return RenderQueueStats()
        if not self.is_enabled():
            self.draw_list.clear()
            return RenderQueueStats()

        stats = renderer.draw(self.draw_list)
        if not isinstance(stats, RenderQueueStats):
            stats = RenderQueueStats()
        self.stats.add(stats)
        self.draw_list.clear()
        return stats

    def finalize(self, perf_stats: Any | None) -> None:
        if perf_stats is None:
            return
        setter = getattr(perf_stats, "set_counter", None)
        if not callable(setter):
            return
        setter("render_sprites_submitted", self.stats.sprites_submitted)
        setter("render_batches_drawn", self.stats.batches_drawn)
        setter("render.draw_calls", self.stats.draw_calls_estimate)
        setter("render_draw_calls", self.stats.draw_calls_estimate)
        setter("render_sprites_drawn", self.stats.sprites_drawn)
