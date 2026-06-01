from __future__ import annotations

import importlib.util
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

ClockFn = Callable[[], float]
StageRecorder = Callable[[str], None]

TIMING_KEYS = (
    "pre_update_behaviour_ms",
    "update_behaviour_ms",
    "movement_ms",
    "animation_ms",
    "late_update_ms",
    "event_delivery_ms",
    "compute_draw_plan_ms",
    "execute_scene_plan_ms",
    "frame_total_ms",
)
COUNTER_KEYS = ("sprites", "behaviours", "events", "draw_ops")


def _load_part_module(name: str) -> Any:
    path = Path(__file__).resolve().parents[1] / "scene_controller_parts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_mesh_bench_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load scene controller part: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class FrameStageBenchmarkResult:
    timings: dict[str, float]
    counters: dict[str, int]


class _BenchController:
    pass


_load_part_module("runtime_hooks").bind_runtime_hooks_methods(_BenchController)
_load_part_module("animation_runtime").bind_animation_runtime_methods(_BenchController)


class _BenchBehaviour:
    def __init__(self, *, subscribed: frozenset[str] | None = None) -> None:
        self._subscribed = subscribed
        self.events_seen = 0

    def subscribed_event_types(self) -> frozenset[str] | None: return self._subscribed
    def pre_update(self, _dt: float) -> None: return
    def update(self, _dt: float) -> None: return
    def late_update(self, _dt: float) -> None: return
    def on_event(self, _event: Any) -> None: self.events_seen += 1


def build_synthetic_scene(*, sprite_count: int, behaviours_per_sprite: int) -> Any:
    controller = _BenchController()
    controller.window = SimpleNamespace(strict_mode=False)
    sprites = [_make_sprite(index, behaviours_per_sprite) for index in range(sprite_count)]
    controller.layers = {"background": [], "entities": sprites, "foreground": []}
    return controller


def run_frame_stage_benchmark(
    *,
    sprite_count: int = 500,
    behaviours_per_sprite: int = 2,
    event_count: int = 3,
    clock_fn: ClockFn = time.perf_counter,
    stage_recorder: StageRecorder | None = None,
) -> FrameStageBenchmarkResult:
    controller = build_synthetic_scene(
        sprite_count=sprite_count,
        behaviours_per_sprite=behaviours_per_sprite,
    )
    events = [SimpleNamespace(type="bench_event") for _ in range(max(0, int(event_count)))]
    timings: dict[str, float] = {}
    frame_start = clock_fn()

    stage_methods = (
        ("pre_update_behaviour_ms", "_pre_update_behaviour_stage"),
        ("update_behaviour_ms", "_update_behaviour_stage"),
        ("movement_ms", "_update_movement_stage"),
        ("animation_ms", "_update_animation_stage"),
        ("late_update_ms", "_late_update_stage"),
    )
    for key, method_name in stage_methods:
        timings[key] = _time_call(
            key,
            lambda name=method_name: _call_stage(controller, name),
            clock_fn,
            stage_recorder,
        )

    timings["event_delivery_ms"] = _time_call(
        "event_delivery_ms",
        lambda: controller._deliver_events_to_behaviours(events),
        clock_fn,
        stage_recorder,
    )

    sprites = list(controller.layers["entities"])
    from engine.scene_render_pipeline import RenderContext, compute_draw_plan, execute_scene_plan

    ctx = RenderContext(
        camera_x=0.0, camera_y=0.0, viewport_w=1280.0, viewport_h=720.0,
        zoom=1.0, sprites=sprites, shadows_enabled=False, use_culling=False,
    )
    plan_box: dict[str, Any] = {}
    timings["compute_draw_plan_ms"] = _time_call(
        "compute_draw_plan_ms",
        lambda: plan_box.setdefault("plan", compute_draw_plan(ctx)),
        clock_fn,
        stage_recorder,
    )
    commands: list[Any] = []
    queue = SimpleNamespace(commands=commands, submit=commands.append)
    timings["execute_scene_plan_ms"] = _time_call(
        "execute_scene_plan_ms",
        lambda: execute_scene_plan(plan_box["plan"], render_queue=queue, use_batching=True),
        clock_fn,
        stage_recorder,
    )
    timings["frame_total_ms"] = max(0.0, (clock_fn() - frame_start) * 1000.0)

    counters = {"sprites": int(sprite_count), "events": len(events), "draw_ops": len(commands)}
    counters["behaviours"] = int(sprite_count) * int(behaviours_per_sprite)
    return FrameStageBenchmarkResult(timings=timings, counters=counters)


def format_benchmark_result(result: FrameStageBenchmarkResult) -> str:
    lines: list[str] = []
    for key in TIMING_KEYS:
        lines.append(f"{key}: {float(result.timings.get(key, 0.0)):.6f}")
    for key in COUNTER_KEYS:
        lines.append(f"{key}: {int(result.counters.get(key, 0))}")
    return "\n".join(lines)


def _time_call(
    stage_name: str,
    call: Callable[[], Any],
    clock_fn: ClockFn,
    stage_recorder: StageRecorder | None,
) -> float:
    if stage_recorder is not None:
        stage_recorder(stage_name)
    start = clock_fn()
    call()
    return max(0.0, (clock_fn() - start) * 1000.0)


def _call_stage(controller: Any, method_name: str) -> None:
    if method_name != "_update_animation_stage" or "engine.scene_controller_core" in sys.modules:
        getattr(controller, method_name)(1.0 / 60.0)
        return
    sys.modules["engine.scene_controller_core"] = SimpleNamespace(tick_animation_state=lambda *_args: None)
    try:
        getattr(controller, method_name)(1.0 / 60.0)
    finally:
        sys.modules.pop("engine.scene_controller_core", None)


def _make_sprite(index: int, behaviours_per_sprite: int) -> SimpleNamespace:
    behaviours: list[_BenchBehaviour] = []
    for behaviour_index in range(max(0, int(behaviours_per_sprite))):
        subscribed = frozenset({"bench_event"}) if behaviour_index % 2 == 0 else frozenset({"other_event"})
        behaviours.append(_BenchBehaviour(subscribed=subscribed))
    return SimpleNamespace(
        mesh_name=f"bench_{index}",
        frozen=False,
        update=lambda: None,
        center_x=float(index % 100),
        center_y=float(index),
        width=32,
        height=32,
        scale=1.0,
        angle=0.0,
        alpha=255,
        color=(255, 255, 255, 255),
        texture=SimpleNamespace(name="bench_texture"),
        mesh_texture_key=("bench", "texture"),
        mesh_entity_data={"id": f"bench_{index}", "render_layer": index % 4, "depth_z": 0.0},
        mesh_behaviours_runtime=behaviours,
    )
