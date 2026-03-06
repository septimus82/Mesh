from __future__ import annotations

import argparse
import sys
import warnings

# Suppress arcade draw_text PerformanceWarning
warnings.filterwarnings("ignore", message=".*draw_text is an extremely slow function.*")


def create_parser() -> argparse.ArgumentParser:
    # Canonical parser wiring now lives in legacy.dispatch/registry.
    from .legacy.dispatch import create_parser as dispatch_create_parser

    return dispatch_create_parser()


def _maybe_dispatch_runtime_only(argv: list[str] | None) -> int | None:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if not args or args[0] != "play-runtime":
        return None
    from .runtime_only_cli import run_play_runtime_argv

    return int(run_play_runtime_argv(args[1:]))


def main(argv: list[str] | None = None) -> int:
    runtime_only_code = _maybe_dispatch_runtime_only(argv)
    if runtime_only_code is not None:
        return int(runtime_only_code)

    # Keep behavior unchanged while removing one indirection layer.
    from .legacy.dispatch import main as dispatch_main

    return int(dispatch_main(argv))
