from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from engine.config import EngineConfig
from engine.tooling.replay_script import load_replay_script, run_replay_script_with_window

if TYPE_CHECKING:  # pragma: no cover - typing only
    from engine.game import GameWindow

PERF_RUN_SCHEMA_VERSION = 1


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
    replay_path = Path(args.replay)
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

    # Warmup
    if args.warmup > 0:
        print(f"[Mesh][Perf] Warming up ({args.warmup} frames)...")
        for _ in range(args.warmup):
            window.on_update(1.0 / 60.0)
            window.on_draw()

    # Measurement
    frames = args.frames
    print(f"[Mesh][Perf] Measuring ({frames} frames)...")
    
    start_time = time.time()
    for _ in range(frames):
        window.on_update(1.0 / 60.0)
        window.on_draw()
    duration = time.time() - start_time

    print(f"[Mesh][Perf] Run complete in {duration:.2f}s.")

    # Collect stats
    snapshot = window.perf_stats.snapshot()
    
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
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
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
        
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        print(f"\n[Mesh][Perf] Report written to {out_path}")

    if failed_checks:
        print("\n[Mesh][Perf] Threshold failures:")
        for failure in failed_checks:
            metric = failure.get("metric")
            value = failure.get("value")
            limit = failure.get("threshold")
            print(f"  {metric}: {value} > {limit}")
        return 2

    # Explicitly close to avoid hanging in headless?
    # window.close() # Arcade window close likely needed if we are bypassing app.run()
    
    return 0


def add_perf_run_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("perf-run", help="Run a replay script and measure performance")
    parser.add_argument("--replay", required=True, help="Path to replay JSON script")
    parser.add_argument("--frames", type=int, default=300, help="Number of frames to measure")
    parser.add_argument("--warmup", type=int, default=60, help="Number of warmup frames to ignore")
    parser.add_argument("--out", help="Path to write JSON performance report")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (if supported)")
    parser.add_argument("--fail-p95-frame-ms", type=float, help="Fail if p95 frame time exceeds threshold (ms)")
    parser.add_argument("--fail-p95-update-ms", type=float, help="Fail if p95 update time exceeds threshold (ms)")
    parser.add_argument("--fail-p95-draw-ms", type=float, help="Fail if p95 draw time exceeds threshold (ms)")
    parser.add_argument("--fail-max-frame-ms", type=float, help="Fail if max frame time exceeds threshold (ms)")
    parser.set_defaults(func=handle_perf_run)
