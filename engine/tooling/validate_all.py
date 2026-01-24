"""Unified validator for Mesh Engine content."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from engine.tooling_runtime.run import UnifiedValidatorCore
from engine.tooling_runtime.discovery import resolve_validation_targets
from engine.validators.prefab_validator import PrefabValidator
from engine.validators.transition_validator import TransitionValidator
from engine.validators.variant_validator import VariantValidator

from ..scene_loader import SceneLoader
from .event_validator import EventValidator

PREFIX = "[Mesh][ValidateAll]"


class UnifiedValidator(UnifiedValidatorCore):
    def __init__(
        self,
        root_path: Path,
        strict_compact: bool = False,
        check_events: bool = True,
        check_reachability: bool = False,
        check_orphans: bool = False,
        check_refs: bool = False,
        check_prefabs: bool = True,
        strict: bool = False,
        schema_strict: bool = False,
    ):
        super().__init__(
            root_path,
            strict_compact=strict_compact,
            check_events=check_events,
            check_reachability=check_reachability,
            check_orphans=check_orphans,
            check_refs=check_refs,
            check_prefabs=check_prefabs,
            strict=strict,
            schema_strict=schema_strict,
            prefix=PREFIX,
            scene_loader_cls=SceneLoader,
            event_validator_cls=EventValidator,
            prefab_validator_cls=PrefabValidator,
            variant_validator_cls=VariantValidator,
            transition_validator_cls=TransitionValidator,
        )


def main(argv: List[str] | None = None) -> int:
    from engine.behaviours import load_builtin_behaviours

    load_builtin_behaviours()
    parser = argparse.ArgumentParser(description="Unified validator for Mesh content.")
    parser.add_argument("path", nargs="?", default=".", help="Path to world or scene file, or directory to scan")
    parser.add_argument("--strict", action="store_true", help="Enforce strict validation (no unknown fields)")
    parser.add_argument(
        "--schema-strict",
        action="store_true",
        help="Enforce strict schema rules (IDs, zone_id, transition targets)",
    )
    parser.add_argument("--strict-compact", action="store_true", help="Fail on non-compact scenes")
    parser.add_argument("--check-reachability", action="store_true", help="Check for unreachable scenes")
    parser.add_argument("--check-orphans", action="store_true", help="Check for orphan scene files")
    parser.add_argument("--check-refs", action="store_true", help="Check for missing asset references")
    args = parser.parse_args(argv)

    repo_root = Path(".")
    targets = resolve_validation_targets(args.path, repo_root)

    if not targets:
        print(f"{PREFIX} No validation targets found for path: {args.path}")
        print(f"{PREFIX} Hint: Provide a world/scene JSON file, or ensure worlds/main_world.json exists.")
        return 1

    validator = UnifiedValidator(
        repo_root,
        strict_compact=args.strict_compact,
        strict=args.strict,
        schema_strict=args.schema_strict,
        check_reachability=args.check_reachability,
        check_orphans=args.check_orphans,
        check_refs=args.check_refs,
    )

    for target in targets:
        validator.validate_path(target)

    return validator.print_report()


if __name__ == "__main__":
    sys.exit(main())
