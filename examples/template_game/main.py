from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.public_api import run_game


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run template game using engine.public_api.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root containing config.json (default: current working directory).",
    )
    parser.add_argument(
        "--scene",
        default="scenes/cellar.json",
        help="Initial scene path (default: scenes/cellar.json, relative to project root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parsed = parse_args(sys.argv[1:] if argv is None else argv)
    project_root = Path(str(parsed.project_root)).resolve()
    scene = Path(str(parsed.scene))
    run_game(scene, project_root=project_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
