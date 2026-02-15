"""
CLI command: ``mesh_cli version``

Displays engine version and provenance metadata.
"""
from __future__ import annotations

import argparse
import sys
from typing import cast

from engine.provenance import (
    format_provenance_text,
    get_provenance,
    provenance_to_dict,
)
from mesh_cli.version_bump import BumpKind, bump_version_file


def register(subparsers: argparse._SubParsersAction) -> None:
    version_parser = subparsers.add_parser(
        "version",
        help="Show engine version and provenance info",
        description="Print Mesh Engine version, Python, platform, and git info",
    )
    version_parser.add_argument(
        "--json",
        action="store_true",
        dest="version_json",
        help="Output provenance as JSON",
    )
    version_subparsers = version_parser.add_subparsers(dest="version_command", help="Version subcommand")
    bump_parser = version_subparsers.add_parser(
        "bump",
        help="Bump semantic version",
        description="Safely bump canonical semantic version in-place",
    )
    bump_parser.add_argument("kind", choices=["patch", "minor", "major"], help="Bump kind")
    bump_parser.add_argument("--dry-run", action="store_true", help="Preview bump without writing file")
    bump_parser.add_argument("--json", action="store_true", dest="bump_json", help="Output deterministic JSON")
    bump_parser.add_argument("--quiet", action="store_true", help="Suppress non-essential text output")


def handle(args: argparse.Namespace) -> int:
    """Print version + provenance and exit."""
    from engine.persistence_io import dumps_json_deterministic

    if getattr(args, "version_command", None) == "bump":
        try:
            kind = cast(BumpKind, str(getattr(args, "kind", "patch")))
            payload = bump_version_file(
                kind=kind,
                dry_run=bool(getattr(args, "dry_run", False)),
            )
        except ValueError as exc:
            print(f"[Mesh][Version] ERROR: {exc}")
            return 1

        if getattr(args, "bump_json", False):
            sys.stdout.write(dumps_json_deterministic(payload))
            sys.stdout.write("\n")
            return 0

        if not getattr(args, "quiet", False):
            action = "Would bump" if bool(getattr(args, "dry_run", False)) else "Bumped"
            print(
                f"[Mesh][Version] {action} {payload['old']} -> {payload['new']} "
                f"({payload['file']})"
            )
        return 0

    prov = get_provenance()

    if getattr(args, "version_json", False):
        sys.stdout.write(dumps_json_deterministic(provenance_to_dict(prov)))
        sys.stdout.write("\n")
    else:
        print(format_provenance_text(prov))

    return 0
