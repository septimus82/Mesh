"""Prefab management commands."""

from __future__ import annotations

import argparse

from engine.tooling import prefab_cli, scaffold


def handle(args: argparse.Namespace) -> int:
    if args.command == "new-prefab":
        return _handle_new_prefab(args)
    if args.command == "place-prefab":
        return _handle_place_prefab(args)
    if args.command == "prefab":
        return prefab_cli.main(args.prefab_args)
    return 1


def register(subparsers: argparse._SubParsersAction) -> None:
    # New Prefab
    new_prefab_parser = subparsers.add_parser("new-prefab", help="Extract prefab from scene", description="Extract prefab from scene")
    new_prefab_parser.add_argument("--prefab-id", required=True, help="ID for new prefab")
    new_prefab_parser.add_argument("--from-scene", required=True, help="Source scene")
    new_prefab_parser.add_argument("--entity-name", required=True, help="Entity to extract")
    new_prefab_parser.add_argument("--remove-source", action="store_true", help="Remove original entity")

    # Place Prefab
    place_prefab_parser = subparsers.add_parser("place-prefab", help="Place prefab in scene", description="Place prefab in scene")
    place_prefab_parser.add_argument("--prefab-id", help="Prefab ID")
    place_prefab_parser.add_argument("--into", required=True, help="Target scene")
    place_prefab_parser.add_argument("--x", type=int, default=0, help="X coordinate")
    place_prefab_parser.add_argument("--y", type=int, default=0, help="Y coordinate")
    place_prefab_parser.add_argument("--from-encounter-set", help="Pick random prefab from encounter set")
    place_prefab_parser.add_argument("--as-placeholder", action="store_true", help="Use placeholder sprite")

    # Prefab Management
    prefab_parser = subparsers.add_parser("prefab", help="Manage prefabs", description="Manage prefabs")
    prefab_parser.add_argument("prefab_args", nargs=argparse.REMAINDER, help="Arguments for prefab tool")


def _handle_new_prefab(args: argparse.Namespace) -> int:
    """Extract a prefab from a scene entity."""
    return 0 if scaffold.extract_prefab(args.prefab_id, args.from_scene, args.entity_name, args.remove_source) else 1


def _handle_place_prefab(args: argparse.Namespace) -> int:
    """Place a prefab into a scene."""
    return 0 if scaffold.place_prefab(
        args.prefab_id,
        args.into,
        args.x,
        args.y,
        from_encounter_set=args.from_encounter_set,
        as_placeholder=args.as_placeholder
    ) else 1
