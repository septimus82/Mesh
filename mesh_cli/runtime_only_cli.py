from __future__ import annotations

import argparse


def build_play_runtime_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mesh_cli play-runtime",
        description="Runtime-only scene bootstrap (no editor wiring).",
    )
    parser.add_argument("scene_path", nargs="?", help="Optional start scene")
    parser.add_argument(
        "--headless-smoke",
        action="store_true",
        help="Run deterministic runtime smoke mode and exit",
    )
    parser.add_argument(
        "--smoke-scene",
        help="Optional scene path override for --headless-smoke",
    )
    parser.add_argument(
        "--smoke-ticks",
        type=int,
        default=3,
        help="Tick count for --headless-smoke (default: 3)",
    )
    parser.add_argument(
        "--smoke-artifact",
        help="Optional JSON artifact path for --headless-smoke",
    )
    parser.add_argument(
        "--diagnostics-artifact",
        help="Optional JSON artifact path for deterministic diagnostics snapshot on exit",
    )
    parser.add_argument(
        "--print-diagnostics-on-exit",
        action="store_true",
        help="Print a deterministic diagnostics summary at shutdown",
    )
    return parser


def run_play_runtime_argv(argv: list[str] | None = None) -> int:
    parser = build_play_runtime_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse --help / parse errors
        code = exc.code
        return int(code) if isinstance(code, int) else 2

    from engine.runtime_only import run_runtime_scene

    return int(
        run_runtime_scene(
            scene_path=getattr(args, "scene_path", None),
            headless_smoke=bool(getattr(args, "headless_smoke", False)),
            smoke_scene=getattr(args, "smoke_scene", None),
            smoke_ticks=int(getattr(args, "smoke_ticks", 3)),
            smoke_artifact=getattr(args, "smoke_artifact", None),
            diagnostics_artifact=getattr(args, "diagnostics_artifact", None),
            print_diagnostics_on_exit=bool(getattr(args, "print_diagnostics_on_exit", False)),
        )
    )


__all__ = ["build_play_runtime_parser", "run_play_runtime_argv"]
