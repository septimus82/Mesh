"""Command-line scene validator for Mesh Engine."""

from __future__ import annotations

import argparse
import sys

from ..scene_loader import SceneLoader, ValidationReport

PREFIX = "[Mesh][SceneValidate]"


def _print_report(report: ValidationReport, path: str) -> int:
    if report.ok:
        print(f"{PREFIX} OK: {path}")
    else:
        print(f"{PREFIX} FAILED: {path}")

    for message in report.errors:
        print(f"{PREFIX} ERROR: {message}")
    for message in report.warnings:
        print(f"{PREFIX} WARN: {message}")

    if report.behaviour_details:
        print(f"{PREFIX} Behaviour parameter report:")
        for entity, behaviours in report.behaviour_details.items():
            print(f"{PREFIX}   entity: {entity}")
            for behaviour, messages in behaviours.items():
                print(f"{PREFIX}     behaviour: {behaviour}")
                for detail in messages:
                    print(f"{PREFIX}       {detail}")

    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Mesh scene JSON file.")
    parser.add_argument("scene_path", help="Path to the scene JSON file to validate")
    args = parser.parse_args(argv)

    loader = SceneLoader()
    report = loader.validate_scene_file(args.scene_path)
    return _print_report(report, args.scene_path)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
