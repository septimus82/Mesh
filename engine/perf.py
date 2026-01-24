from __future__ import annotations

import collections
import enum
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Deque


class PerfMetric(str, enum.Enum):
    FRAME_TOTAL_MS = "frame_total_ms"
    UPDATE_MS = "update_ms"
    DRAW_MS = "draw_ms"


@dataclass
class MetricStats:
    count: int
    mean: float
    p50: float
    p95: float
    p99: float
    max: float
    stddev: float = 0.0


@dataclass
class PerfSnapshot:
    metrics: dict[str, MetricStats]
    meta: dict[str, Any] = field(default_factory=dict)


class PerfStats:
    """Lightweight circular buffer performance tracker."""

    def __init__(self, history_size: int = 600) -> None:
        self.history_size = history_size
        self.samples: dict[str, Deque[float]] = collections.defaultdict(
            lambda: collections.deque(maxlen=history_size)
        )
        self.counters: dict[str, int] = {}
        # Frame state
        self._frame_start_time: float = 0.0
        self._update_start_time: float = 0.0
        self._draw_start_time: float = 0.0
        self._frame_index: int = 0

    def enter_frame(self) -> None:
        """Mark start of a new frame loop."""
        now = time.perf_counter()
        if self._frame_start_time > 0:
            # Complete previous frame
            total_duration = (now - self._frame_start_time) * 1000.0
            self.samples[PerfMetric.FRAME_TOTAL_MS].append(total_duration)
        
        self._frame_start_time = now
        self._frame_index += 1

    def mark_update_start(self) -> None:
        self._update_start_time = time.perf_counter()

    def mark_update_end(self) -> None:
        if self._update_start_time > 0:
            duration = (time.perf_counter() - self._update_start_time) * 1000.0
            self.samples[PerfMetric.UPDATE_MS].append(duration)
            self._update_start_time = 0.0

    def mark_draw_start(self) -> None:
        self._draw_start_time = time.perf_counter()

    def mark_draw_end(self) -> None:
        if self._draw_start_time > 0:
            duration = (time.perf_counter() - self._draw_start_time) * 1000.0
            self.samples[PerfMetric.DRAW_MS].append(duration)
            self._draw_start_time = 0.0

    def set_counter(self, name: str, value: int) -> None:
        self.counters[str(name)] = int(value)

    def add_counter(self, name: str, delta: int) -> None:
        key = str(name)
        self.counters[key] = int(self.counters.get(key, 0)) + int(delta)

    def snapshot(self) -> PerfSnapshot:
        """Compute stats for current buffer."""
        metrics: dict[str, MetricStats] = {}
        for key, values in self.samples.items():
            if not values:
                continue
            
            data = sorted(values)
            n = len(data)
            mean = sum(data) / n
            variance = sum((x - mean) ** 2 for x in data) / n
            stddev = math.sqrt(variance)
            
            metrics[key] = MetricStats(
                count=n,
                mean=round(mean, 3),
                stddev=round(stddev, 3),
                p50=round(data[int(n * 0.50)], 3),
                p95=round(data[int(n * 0.95)], 3),
                p99=round(data[int(n * 0.99)], 3),
                max=round(data[-1], 3),
            )
            
        return PerfSnapshot(metrics=metrics, meta={"counters": dict(self.counters)})
