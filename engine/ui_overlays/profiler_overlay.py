from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from engine.text_draw import TextCache, draw_text_cached

from .common import (
    UIElement,
    _draw_tb_rectangle_outline,
    _draw_rectangle_filled,
)

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


def _metric_line(perf_snapshot: Any, metric_name: str, label: str) -> str:
    metrics = getattr(perf_snapshot, "metrics", None)
    metric_map = metrics if isinstance(metrics, dict) else {}
    stats = metric_map.get(metric_name)
    if stats is None:
        return f"{label}: n/a"
    p95 = float(getattr(stats, "p95", 0.0) or 0.0)
    max_v = float(getattr(stats, "max", 0.0) or 0.0)
    return f"{label}: p95={p95:.2f}ms max={max_v:.2f}ms"


def render_rows(
    perf_snapshot: Any,
    overlay_perf_snapshot: dict[str, Any] | None = None,
    runtime_summary: dict[str, Any] | None = None,
) -> list[str]:
    lines = ["PROFILER (Shift+F6)"]

    fps = float(optional_arcade.arcade.get_fps())
    summary = runtime_summary if isinstance(runtime_summary, dict) else {}
    draw_calls = summary.get("draw_calls")
    try:
        draw_calls_int: int | None = int(draw_calls) if draw_calls is not None else None
    except (TypeError, ValueError):
        draw_calls_int = None
    if draw_calls_int is None:
        counters = getattr(perf_snapshot, "meta", None)
        if isinstance(counters, dict):
            raw_counters = counters.get("counters")
            if isinstance(raw_counters, dict):
                raw_draw_calls = raw_counters.get("render.draw_calls", raw_counters.get("render_draw_calls", 0))
                if raw_draw_calls is None:
                    draw_calls_int = 0
                else:
                    try:
                        draw_calls_int = int(raw_draw_calls)
                    except (TypeError, ValueError):
                        draw_calls_int = 0
        else:
            draw_calls_int = 0

    entity_count = int(summary.get("entity_count", 0) or 0)
    hot_reload_enabled = bool(summary.get("hot_reload_enabled", False))
    hot_reload_running = bool(summary.get("hot_reload_running", False))
    rumble_enabled = bool(summary.get("rumble_enabled", False))
    rumble_backend_connected = bool(summary.get("rumble_backend_connected", False))
    try:
        rumble_strength = float(summary.get("rumble_strength", 1.0) or 1.0)
    except (TypeError, ValueError):
        rumble_strength = 1.0
    rumble_strength = max(0.0, min(rumble_strength, 1.0))
    lines.append(f"summary: fps={fps:.1f} entities={entity_count} draw_calls={int(draw_calls_int or 0)}")
    lines.append(
        f"dev: hot_reload_enabled={'1' if hot_reload_enabled else '0'} "
        f"running={'1' if hot_reload_running else '0'}"
    )
    lines.append(
        f"dev: rumble_enabled={'1' if rumble_enabled else '0'} "
        f"strength={rumble_strength:.2f} "
        f"backend={'1' if rumble_backend_connected else '0'}"
    )
    if hot_reload_enabled or hot_reload_running:
        shader_reloaded = int(summary.get("shader_reloaded", 0) or 0)
        shader_failed = int(summary.get("shader_failed", 0) or 0)
        textures_reloaded = int(summary.get("textures_reloaded", 0) or 0)
        textures_failed = int(summary.get("textures_failed", 0) or 0)
        audio_reloaded = int(summary.get("audio_reloaded", 0) or 0)
        audio_failed = int(summary.get("audio_failed", 0) or 0)
        lines.append(f"hot_reload: shaders reloaded={shader_reloaded} failed={shader_failed}")
        if shader_failed > 0:
            lines.append("hot_reload: WARN shader reload failures detected")
        lines.append(f"hot_reload: textures reloaded={textures_reloaded} failed={textures_failed}")
        if textures_failed > 0:
            lines.append("hot_reload: WARN texture reload failures detected")
        lines.append(f"hot_reload: audio reloaded={audio_reloaded} failed={audio_failed}")
        if audio_failed > 0:
            lines.append("hot_reload: WARN audio reload failures detected")

    lines.append(_metric_line(perf_snapshot, "frame_total_ms", "frame"))
    lines.append(_metric_line(perf_snapshot, "update_ms", "update"))
    lines.append(_metric_line(perf_snapshot, "draw_ms", "draw"))

    overlay_metrics: dict[str, Any] = {}
    if isinstance(overlay_perf_snapshot, dict):
        metrics = overlay_perf_snapshot.get("metrics")
        if isinstance(metrics, dict):
            overlay_metrics = metrics
        else:
            overlay_metrics = overlay_perf_snapshot
    lines.append("overlay_provider_ms:")
    for provider_name in ("providers_total", "command_palette_provider"):
        bucket = overlay_metrics.get(provider_name, {})
        bucket_map = bucket if isinstance(bucket, dict) else {}
        count = int(bucket_map.get("count", 0) or 0)
        total_ms = float(bucket_map.get("total_ms", 0.0) or 0.0)
        max_ms = float(bucket_map.get("max_ms", 0.0) or 0.0)
        lines.append(
            f"{provider_name}: n={count} total={total_ms:.2f}ms max={max_ms:.2f}ms"
        )

    return lines


class ProfilerOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.visible = False
        self.provider = provider
        self._text_cache = TextCache()

    def toggle(self) -> bool:
        self.visible = not self.visible
        return self.visible

    def draw(self) -> None:
        if not self.visible:
            return

        payload: dict[str, Any] = {}
        if callable(self.provider):
            try:
                value = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: profiler overlay should keep rendering even if an optional provider callback fails
                value = None
            if isinstance(value, dict):
                payload = value

        if not bool(payload.get("profiler_enabled", False)):
            return

        rows_value = payload.get("profiler_rows")
        rows = rows_value if isinstance(rows_value, list) else []
        lines = [str(row or "").rstrip() for row in rows if str(row or "").strip()]
        if not lines:
            return

        width = min(520.0, max(360.0, self.window.width - 40.0))
        height = max(132.0, 28.0 + 16.0 * float(len(lines)))
        left = 20.0
        top = self.window.height - 20.0
        right = left + width
        bottom = top - height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)
        draw_text_cached(
            "\n".join(lines),
            left + 12.0,
            top - 12.0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )
