from __future__ import annotations

import argparse
import warnings

# Suppress arcade draw_text PerformanceWarning
warnings.filterwarnings("ignore", message=".*draw_text is an extremely slow function.*")


def create_parser() -> argparse.ArgumentParser:
    # Keep behavior identical while we refactor by delegating to the legacy implementation.
    from .legacy import create_parser as legacy_create_parser

    return legacy_create_parser()


def main(argv: list[str] | None = None) -> int:
    # Keep behavior identical while we refactor by delegating to the legacy implementation.
    from .legacy import main as legacy_main

    return int(legacy_main(argv))

