from __future__ import annotations

import argparse


def create_parser() -> argparse.ArgumentParser:
    # Thin compatibility layer: legacy CLI implementation lives in `mesh_cli.legacy_impl`.
    from ..legacy_impl import create_parser as legacy_create_parser

    return legacy_create_parser()


def main(argv: list[str] | None = None) -> int:
    from ..legacy_impl import main as legacy_main

    return int(legacy_main(argv))


__all__ = ("create_parser", "main")
