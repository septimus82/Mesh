from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_synthetic_builder_exact_counts_without_arcade_import() -> None:
    sys.modules.pop("arcade", None)
    from engine.tooling.frame_stage_benchmark import build_synthetic_scene

    for sprite_count in (500, 2000):
        scene = build_synthetic_scene(sprite_count=sprite_count, behaviours_per_sprite=2)
        sprites = list(scene.layers["entities"])

        assert len(sprites) == sprite_count
        assert sum(len(sprite.mesh_behaviours_runtime) for sprite in sprites) == sprite_count * 2
        assert "arcade" not in sys.modules


def test_benchmark_invokes_update_stages_in_deterministic_order() -> None:
    from engine.tooling.frame_stage_benchmark import run_frame_stage_benchmark

    calls: list[str] = []
    result = run_frame_stage_benchmark(
        sprite_count=3,
        behaviours_per_sprite=1,
        event_count=1,
        stage_recorder=calls.append,
    )

    assert calls[:5] == [
        "pre_update_behaviour_ms",
        "update_behaviour_ms",
        "movement_ms",
        "animation_ms",
        "late_update_ms",
    ]
    assert result.counters["sprites"] == 3


def test_event_delivery_reports_timing_key_for_subscribed_and_unsubscribed_behaviours() -> None:
    from engine.tooling.frame_stage_benchmark import run_frame_stage_benchmark

    result = run_frame_stage_benchmark(sprite_count=4, behaviours_per_sprite=2, event_count=2)

    assert result.counters["events"] == 2
    assert result.counters["behaviours"] == 8
    value = result.timings["event_delivery_ms"]
    assert isinstance(value, float)
    assert value >= 0.0


def test_render_benchmark_reports_compute_and_execute_separately() -> None:
    from engine.tooling.frame_stage_benchmark import run_frame_stage_benchmark

    result = run_frame_stage_benchmark(sprite_count=5, behaviours_per_sprite=0, event_count=0)

    for key in ("compute_draw_plan_ms", "execute_scene_plan_ms"):
        value = result.timings[key]
        assert isinstance(value, float)
        assert value >= 0.0
    assert result.counters["draw_ops"] == 5


def test_hot_path_modules_do_not_import_frame_stage_benchmark() -> None:
    root = Path(__file__).resolve().parents[1]
    hot_paths = (
        "engine/game_runtime/tick.py",
        "engine/scene_update_controller.py",
        "engine/scene_controller_parts/runtime_hooks.py",
        "engine/scene_controller_parts/animation_runtime.py",
        "engine/scene_controller_parts/rendering.py",
        "engine/scene_render_pipeline.py",
    )

    for rel_path in hot_paths:
        text = (root / rel_path).read_text(encoding="utf-8")
        assert "frame_stage_benchmark" not in text
