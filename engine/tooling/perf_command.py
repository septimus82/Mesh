from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from engine import json_io
from engine.config import EngineConfig
from engine.tooling.replay_script import load_replay_script, run_replay_script_with_window

if TYPE_CHECKING:  # pragma: no cover - typing only
    from engine.game import GameWindow

PERF_RUN_SCHEMA_VERSION = 1
PERF_SCENE_CAPTURE_SCHEMA_VERSION = 1
PERF_COMPARE_SCHEMA_VERSION = 1


def _get_engine_git_sha() -> str | None:
    env_sha = os.environ.get("MESH_GIT_SHA") or os.environ.get("GIT_SHA")
    if env_sha:
        return env_sha
    try:
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def handle_perf_run(args: argparse.Namespace) -> int:
    scenes_path = str(getattr(args, "scenes", "") or "").strip()
    if scenes_path:
        from engine.persistence_io import write_json_atomic
        from engine.tooling.perf_baselines import compare_perf_run_to_baseline
        from engine.tooling.perf_baselines import load_perf_baseline
        from engine.tooling.perf_baselines import run_perf_scene_capture

        scene_set_path = Path(scenes_path)
        if not scene_set_path.exists():
            print(f"Scene set not found: {scene_set_path}")
            return 1
        ticks = int(max(1, int(getattr(args, "ticks", 120))))
        run_payload = run_perf_scene_capture(scene_set_path=scene_set_path, ticks=ticks)
        run_payload["schema_version"] = PERF_SCENE_CAPTURE_SCHEMA_VERSION
        if args.out:
            write_json_atomic(Path(args.out), run_payload, indent=2, sort_keys=True, trailing_newline=True)

        baseline_path_raw = str(getattr(args, "perf_baseline", "") or "").strip()
        if not baseline_path_raw:
            return 0

        baseline_path = Path(baseline_path_raw)
        if not baseline_path.exists():
            print(f"Perf baseline not found: {baseline_path}")
            return 1

        baseline_payload = load_perf_baseline(baseline_path)
        compare_payload = compare_perf_run_to_baseline(
            run_payload=run_payload,
            baseline_payload=baseline_payload,
        )
        compare_payload["schema_version"] = PERF_COMPARE_SCHEMA_VERSION
        compare_out_raw = str(getattr(args, "compare_out", "") or "").strip()
        if compare_out_raw:
            write_json_atomic(Path(compare_out_raw), compare_payload, indent=2, sort_keys=True, trailing_newline=True)

        regressions = compare_payload.get("regressions", [])
        if isinstance(regressions, list) and regressions:
            print(f"[Mesh][Perf] Regressions detected: {len(regressions)}")
            for row in regressions[:10]:
                if not isinstance(row, dict):
                    continue
                print(
                    "[Mesh][Perf] "
                    f"{row.get('scene_id')} {row.get('metric')}: "
                    f"{row.get('baseline')} -> {row.get('current')} "
                    f"(allowed +{row.get('increase_allowed')})"
                )
            return 2
        return 0

    replay_raw = str(getattr(args, "replay", "") or "").strip()
    if not replay_raw:
        print("Missing required input: provide --replay or --scenes")
        return 2
    replay_path = Path(replay_raw)
    if not replay_path.exists():
        print(f"Replay not found: {replay_path}")
        return 1

    try:
        script = load_replay_script(replay_path)
    except Exception as e:
        print(f"Failed to load replay script: {e}")
        return 1

    # Capture window instance
    from engine.game import GameWindow

    window_ref: list[GameWindow] = []

    def window_factory(script_payload: dict[str, Any]) -> GameWindow:
        # We ignore script-specific window args if they conflict with our perf config,
        # but _default_window_factory usually sets up the scene path.
        # We'll replicate _default_window_factory's logic but return a REAL GameWindow.
        
        # NOTE: We are NOT using the lightweight ReplayWindow here.
        config = EngineConfig()
        config.debug_on_start = False
        
        # Respect script start scene if present
        scene_path = script_payload.get("scene_path")
        if scene_path:
             pass # GameWindow usually loads config.start_scene. 
                  # We might need to warp after creation if we can't inject it easily.
                  # EngineConfig doesn't usually take start_scene directly, it's in config.json.
        
        # Create real window
        # Force a reasonable resolution for perf consistency
        width, height = 1280, 720
        window = GameWindow(width, height, "Mesh Perf Run", config=config)
        
        # Warp if needed
        if scene_path:
            # We need to manually inject this because GameWindow.__init__ kicks off loading.
            # But GameWindow uses SceneLoader.
            # This is tricky because GameWindow loads the start scene immediately.
            # If the script specifies a different scene, we should warp.
            pass
            
        window_ref.append(window)
        return window

    print(f"[Mesh][Perf] Running replay logic from {replay_path}...")
    try:
        # Run the logic steps (e.g. set flags, give items)
        run_replay_script_with_window(script, window_factory=window_factory)
    except Exception as e:
        print(f"[Mesh][Perf] Error during replay script setup: {e}")
        return 1

    if not window_ref:
        print("[Mesh][Perf] Failed to create GameWindow.")
        return 1

    window = window_ref[0]

    snapshot = None
    duration = 0.0
    frames = args.frames
    try:
        # Warmup
        if args.warmup > 0:
            print(f"[Mesh][Perf] Warming up ({args.warmup} frames)...")
            for _ in range(args.warmup):
                window.on_update(1.0 / 60.0)
                window.on_draw()

        # Measurement
        print(f"[Mesh][Perf] Measuring ({frames} frames)...")
        
        start_time = time.time()
        for _ in range(frames):
            window.on_update(1.0 / 60.0)
            window.on_draw()
        duration = time.time() - start_time

        print(f"[Mesh][Perf] Run complete in {duration:.2f}s.")

        # Collect stats
        snapshot = window.perf_stats.snapshot()
    finally:
        # Always close window to prevent subprocess hang
        try:
            if hasattr(window, "close") and callable(window.close):
                window.close()
        except Exception as close_exc:
            print(f"[Mesh][Perf] Warning: failed to close window: {close_exc}")

    if snapshot is None:
        print("[Mesh][Perf] Failed to collect performance stats.")
        return 1
    
    # Report to stdout
    print("\nPerformance Summary:")
    metrics = snapshot.metrics
    for key in ["frame_total_ms", "update_ms", "draw_ms"]:
        if key in metrics:
            stats = metrics[key]
            print(f"  {key:<15} mean: {stats.mean:>6.2f}ms  p95: {stats.p95:>6.2f}ms  max: {stats.max:>6.2f}ms")
        else:
            print(f"  {key:<15} (no data)")

    thresholds: dict[str, float] = {}
    if args.fail_p95_frame_ms is not None:
        thresholds["fail_p95_frame_ms"] = float(args.fail_p95_frame_ms)
    if args.fail_p95_update_ms is not None:
        thresholds["fail_p95_update_ms"] = float(args.fail_p95_update_ms)
    if args.fail_p95_draw_ms is not None:
        thresholds["fail_p95_draw_ms"] = float(args.fail_p95_draw_ms)
    if args.fail_max_frame_ms is not None:
        thresholds["fail_max_frame_ms"] = float(args.fail_max_frame_ms)

    failed_checks: list[dict[str, float | str]] = []
    if thresholds:
        frame_stats = metrics.get("frame_total_ms")
        update_stats = metrics.get("update_ms")
        draw_stats = metrics.get("draw_ms")

        def _check(metric: str, value: float | None, limit: float) -> None:
            if value is None:
                failed_checks.append({"metric": metric, "value": "missing", "threshold": limit})
                return
            if float(value) > float(limit):
                failed_checks.append({"metric": metric, "value": float(value), "threshold": float(limit)})

        if "fail_p95_frame_ms" in thresholds:
            _check("p95_frame_ms", getattr(frame_stats, "p95", None), thresholds["fail_p95_frame_ms"])
        if "fail_p95_update_ms" in thresholds:
            _check("p95_update_ms", getattr(update_stats, "p95", None), thresholds["fail_p95_update_ms"])
        if "fail_p95_draw_ms" in thresholds:
            _check("p95_draw_ms", getattr(draw_stats, "p95", None), thresholds["fail_p95_draw_ms"])
        if "fail_max_frame_ms" in thresholds:
            _check("max_frame_ms", getattr(frame_stats, "max", None), thresholds["fail_max_frame_ms"])

    evaluation = {"ok": not failed_checks, "failed": failed_checks}

    # Output JSON
    if args.out:
        out_path = Path(args.out)
        
        output_data = asdict(snapshot)
        output_data["meta"] = {
            "replay": str(replay_path),
            "frames": frames,
            "warmup": args.warmup,
            "duration_sec": duration,
            "schema_version": PERF_RUN_SCHEMA_VERSION,
            "engine_git_sha": _get_engine_git_sha(),
            "thresholds": thresholds,
            "evaluation": evaluation,
        }
        
        json_io.write_json_atomic(out_path, output_data)
        print(f"\n[Mesh][Perf] Report written to {out_path}")

    if failed_checks:
        print("\n[Mesh][Perf] Threshold failures:")
        for failure in failed_checks:
            metric = failure.get("metric")
            value = failure.get("value")
            limit = failure.get("threshold")
            print(f"  {metric}: {value} > {limit}")
        return 2

    return 0


def add_perf_run_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("perf-run", help="Run a replay script and measure performance")
    parser.add_argument("--replay", help="Path to replay JSON script")
    parser.add_argument(
        "--scenes",
        help="Path to deterministic perf scene set JSON (scene-counter mode)",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=120,
        help="Tick multiplier for deterministic scene-counter metrics (default: 120)",
    )
    parser.add_argument("--frames", type=int, default=300, help="Number of frames to measure")
    parser.add_argument("--warmup", type=int, default=60, help="Number of warmup frames to ignore")
    parser.add_argument("--out", help="Path to write JSON performance report")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (if supported)")
    parser.add_argument(
        "--perf-baseline",
        help="Optional baseline JSON for deterministic scene-counter comparison",
    )
    parser.add_argument(
        "--compare-out",
        help="Optional path to write deterministic perf compare JSON report",
    )
    parser.add_argument("--fail-p95-frame-ms", type=float, help="Fail if p95 frame time exceeds threshold (ms)")
    parser.add_argument("--fail-p95-update-ms", type=float, help="Fail if p95 update time exceeds threshold (ms)")
    parser.add_argument("--fail-p95-draw-ms", type=float, help="Fail if p95 draw time exceeds threshold (ms)")
    parser.add_argument("--fail-max-frame-ms", type=float, help="Fail if max frame time exceeds threshold (ms)")
    parser.set_defaults(func=handle_perf_run)

    compare_parser = subparsers.add_parser(
        "perf-compare",
        help="Compare deterministic perf scene-counter run against baseline JSON",
    )
    compare_parser.add_argument("--run", required=True, help="Perf run JSON from perf-run --scenes")
    compare_parser.add_argument("--baseline", required=True, help="Perf baseline JSON")
    compare_parser.add_argument("--out", required=True, help="Path to write compare JSON")
    compare_parser.set_defaults(func=handle_perf_compare)

    bench_parser = subparsers.add_parser(
        "perf-stage-bench",
        help="Run a headless synthetic frame-stage benchmark",
    )
    bench_parser.add_argument("--sprites", type=int, default=500, help="Synthetic sprite count")
    bench_parser.add_argument("--behaviours", type=int, default=2, help="Behaviours per sprite")
    bench_parser.add_argument("--events", type=int, default=3, help="Synthetic event count")
    bench_parser.set_defaults(func=handle_perf_stage_bench)


def handle_perf_stage_bench(args: argparse.Namespace) -> int:
    from engine.tooling.frame_stage_benchmark import (
        format_benchmark_result,
        run_frame_stage_benchmark,
    )

    result = run_frame_stage_benchmark(
        sprite_count=max(0, int(getattr(args, "sprites", 500))),
        behaviours_per_sprite=max(0, int(getattr(args, "behaviours", 2))),
        event_count=max(0, int(getattr(args, "events", 3))),
    )
    print(format_benchmark_result(result))
    return 0


def handle_perf_compare(args: argparse.Namespace) -> int:
    from engine.persistence_io import write_json_atomic
    from engine.tooling.perf_baselines import compare_perf_run_to_baseline
    from engine.tooling.perf_baselines import load_perf_baseline

    run_path = Path(str(getattr(args, "run", "") or "").strip())
    baseline_path = Path(str(getattr(args, "baseline", "") or "").strip())
    out_path = Path(str(getattr(args, "out", "") or "").strip())
    if not run_path.exists():
        print(f"Perf run artifact not found: {run_path}")
        return 1
    if not baseline_path.exists():
        print(f"Perf baseline artifact not found: {baseline_path}")
        return 1
    run_payload = json.loads(run_path.read_text(encoding="utf-8"))
    if not isinstance(run_payload, dict):
        print(f"Perf run artifact invalid (expected object): {run_path}")
        return 1
    baseline_payload = load_perf_baseline(baseline_path)
    compare_payload = compare_perf_run_to_baseline(
        run_payload=run_payload,
        baseline_payload=baseline_payload,
    )
    compare_payload["schema_version"] = PERF_COMPARE_SCHEMA_VERSION
    write_json_atomic(out_path, compare_payload, indent=2, sort_keys=True, trailing_newline=True)
    return 0 if bool(compare_payload.get("ok")) else 2
