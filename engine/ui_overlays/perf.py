from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from .common import UIElement

if TYPE_CHECKING:
    from engine.game import GameWindow


class PerfOverlay(UIElement):
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False

    def toggle(self) -> None:
        self.visible = not self.visible

    def draw(self) -> None:
        if not self.visible:
            return

        snapshot = self.window.perf_stats.snapshot()
        metrics = snapshot.metrics
        counters = snapshot.meta.get("counters", {}) if isinstance(snapshot.meta, dict) else {}

        lines = ["PERFORMANCE (P)"]
        
        # FPS
        fps = optional_arcade.arcade.get_fps()
        lines.append(f"FPS: {fps:.1f}")

        # Metrics
        for key in ["frame_total_ms", "update_ms", "draw_ms"]:
            stats = metrics.get(key)
            if stats:
                lines.append(f"{key:<15} p95: {stats.p95:>5.2f}ms  max: {stats.max:>5.2f}ms")
            else:
                lines.append(f"{key:<15} (no data)")

        if counters:
            lines.append("Render Batches")
            lines.append(f"sprites_submitted: {counters.get('render_sprites_submitted', 0)}")
            lines.append(f"batches_drawn: {counters.get('render_batches_drawn', 0)}")
            lines.append(f"draw_calls: {counters.get('render_draw_calls', 0)}")
            lines.append(f"sprites_drawn: {counters.get('render_sprites_drawn', 0)}")
            lines.append(f"sprites_culled: {counters.get('render_sprites_culled', 0)}")
            lines.append(f"particle_culled: {counters.get('particle_sprites_culled', 0)}")
            if any(key in counters for key in ("tile_chunks_drawn", "tile_sprites_drawn", "tile_draw_calls")):
                lines.append("Tilemap Batches")
                lines.append(f"tile_chunks: {counters.get('tile_chunks_drawn', 0)}")
                lines.append(f"tile_sprites: {counters.get('tile_sprites_drawn', 0)}")
                lines.append(f"tile_draw_calls: {counters.get('tile_draw_calls', 0)}")

        from engine.text_draw import draw_text_cached
        cache = getattr(self.window, "text_cache", None)

        start_y = self.window.height - 100
        for line in lines:
            draw_text_cached(
                line, 
                self.window.width - 220, 
                start_y, 
                color=optional_arcade.arcade.color.GREEN, 
                font_size=12, 
                width=200, 
                align="left",
                bold=True,
                cache=cache
            )
            start_y -= 16
