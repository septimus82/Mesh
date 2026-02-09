"""Deterministic export bundle builder.

This module produces shippable bundles using the asset manifest and dependency
graph. It copies only required assets + runtime code/config and writes a
bundle_manifest.json with hashes of shipped files.

Usage:
    python -m tooling.export_bundle build --repo-root . --out dist/bundle
    python -m tooling.export_bundle plan --repo-root .
    python -m tooling.export_bundle diff --bundle-a dist/bundle1 --bundle-b dist/bundle2
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tooling.asset_manifest import (
    DependencyReport,
    audit_dependencies,
    build_manifest,
    compute_sha256,
    extract_dependencies,
    get_asset_type,
)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

BUNDLE_MANIFEST_VERSION = 1

# Runtime files to always include (relative to repo root)
RUNTIME_INCLUDES: tuple[str, ...] = (
    "main.py",
    "config.json",
    "pyproject.toml",
)

# Runtime directories to include
RUNTIME_DIRS: tuple[str, ...] = (
    "engine",
    "locales",
)

# Patterns to exclude from runtime dirs
RUNTIME_EXCLUDES: tuple[str, ...] = (
    "__pycache__",
    ".pyc",
    ".pyo",
    "test_",
    "_test.py",
    ".mypy_cache",
    ".pytest_cache",
)

# Content directories (scenes, worlds, etc.)
CONTENT_DIRS: tuple[str, ...] = (
    "scenes",
    "worlds",
)


# --------------------------------------------------------------------------- #
# Export Plan
# --------------------------------------------------------------------------- #

@dataclass
class ExportFile:
    """A file to be included in the export bundle."""

    rel_path: str  # Relative path in bundle
    src_path: str  # Absolute source path
    sha256: str  # Content hash
    size: int  # File size
    category: str  # "asset", "runtime", "content", "config"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.rel_path,
            "sha256": self.sha256,
            "size": self.size,
            "category": self.category,
        }


@dataclass
class ExportPlan:
    """Plan for what to include in the export bundle."""

    files: list[ExportFile] = field(default_factory=list)
    excluded_assets: list[str] = field(default_factory=list)
    missing_deps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.missing_deps) == 0 and len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "file_count": len(self.files),
            "total_size": sum(f.size for f in self.files),
            "excluded_asset_count": len(self.excluded_assets),
            "missing_dep_count": len(self.missing_deps),
            "error_count": len(self.errors),
            "files": [f.to_dict() for f in self.files],
            "excluded_assets": self.excluded_assets,
            "missing_deps": self.missing_deps,
            "errors": self.errors,
        }

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = []
        lines.append(f"Export Plan: {'OK' if self.ok else 'FAILED'}")
        lines.append(f"  Files to include: {len(self.files)}")
        lines.append(f"  Total size: {sum(f.size for f in self.files):,} bytes")
        lines.append(f"  Excluded assets: {len(self.excluded_assets)}")

        if self.missing_deps:
            lines.append(f"  Missing dependencies: {len(self.missing_deps)}")
            for dep in self.missing_deps[:5]:
                lines.append(f"    - {dep}")
            if len(self.missing_deps) > 5:
                lines.append(f"    ... and {len(self.missing_deps) - 5} more")

        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
            for err in self.errors[:5]:
                lines.append(f"    - {err}")

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Bundle Manifest
# --------------------------------------------------------------------------- #

@dataclass
class BundleManifest:
    """Manifest for an exported bundle."""

    version: int
    created_at: str
    repo_root: str
    file_count: int
    total_size: int
    files: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "repo_root": self.repo_root,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BundleManifest":
        return cls(
            version=data.get("version", 1),
            created_at=data.get("created_at", ""),
            repo_root=data.get("repo_root", ""),
            file_count=data.get("file_count", 0),
            total_size=data.get("total_size", 0),
            files=data.get("files", []),
        )


# --------------------------------------------------------------------------- #
# Bundle Diff
# --------------------------------------------------------------------------- #

@dataclass
class BundleDiff:
    """Difference between two bundles."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_changes": self.has_changes,
            "added_count": len(self.added),
            "removed_count": len(self.removed),
            "changed_count": len(self.changed),
            "unchanged_count": len(self.unchanged),
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
        }

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = []
        if not self.has_changes:
            lines.append("Bundles are identical")
        else:
            lines.append("Bundle differences:")
            if self.added:
                lines.append(f"  Added: {len(self.added)}")
                for f in self.added[:5]:
                    lines.append(f"    + {f}")
                if len(self.added) > 5:
                    lines.append(f"    ... and {len(self.added) - 5} more")

            if self.removed:
                lines.append(f"  Removed: {len(self.removed)}")
                for f in self.removed[:5]:
                    lines.append(f"    - {f}")
                if len(self.removed) > 5:
                    lines.append(f"    ... and {len(self.removed) - 5} more")

            if self.changed:
                lines.append(f"  Changed: {len(self.changed)}")
                for f in self.changed[:5]:
                    lines.append(f"    * {f}")
                if len(self.changed) > 5:
                    lines.append(f"    ... and {len(self.changed) - 5} more")

        lines.append(f"  Unchanged: {len(self.unchanged)}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #

def _should_exclude_runtime(rel_path: str, filename: str) -> bool:
    """Check if a runtime file should be excluded."""
    for pattern in RUNTIME_EXCLUDES:
        if pattern in rel_path or filename.startswith(pattern) or filename.endswith(pattern):
            return True
    return False


def _collect_runtime_files(repo_root: Path) -> list[ExportFile]:
    """Collect runtime Python files and config."""
    files: list[ExportFile] = []

    # Single files
    for rel_name in RUNTIME_INCLUDES:
        src = repo_root / rel_name
        if src.is_file():
            try:
                files.append(ExportFile(
                    rel_path=rel_name,
                    src_path=str(src.resolve()),
                    sha256=compute_sha256(src),
                    size=src.stat().st_size,
                    category="config" if rel_name.endswith(".json") else "runtime",
                ))
            except OSError:
                continue

    # Runtime directories
    for dir_name in RUNTIME_DIRS:
        dir_path = repo_root / dir_name
        if not dir_path.is_dir():
            continue

        for root, dirs, filenames in os.walk(dir_path, topdown=True):
            # Filter directories in-place
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".mypy_cache"))

            for filename in sorted(filenames):
                file_path = Path(root) / filename
                rel_path = file_path.relative_to(repo_root).as_posix()

                if _should_exclude_runtime(rel_path, filename):
                    continue

                try:
                    files.append(ExportFile(
                        rel_path=rel_path,
                        src_path=str(file_path.resolve()),
                        sha256=compute_sha256(file_path),
                        size=file_path.stat().st_size,
                        category="runtime",
                    ))
                except OSError:
                    continue

    return files


def _collect_content_files(repo_root: Path) -> list[ExportFile]:
    """Collect content files (scenes, worlds)."""
    files: list[ExportFile] = []

    for dir_name in CONTENT_DIRS:
        dir_path = repo_root / dir_name
        if not dir_path.is_dir():
            continue

        for root, dirs, filenames in os.walk(dir_path, topdown=True):
            dirs[:] = sorted(dirs)

            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue

                file_path = Path(root) / filename
                rel_path = file_path.relative_to(repo_root).as_posix()

                try:
                    files.append(ExportFile(
                        rel_path=rel_path,
                        src_path=str(file_path.resolve()),
                        sha256=compute_sha256(file_path),
                        size=file_path.stat().st_size,
                        category="content",
                    ))
                except OSError:
                    continue

    return files


def compute_export_plan(
    repo_root: Path,
    *,
    include_unused: bool = False,
) -> ExportPlan:
    """Compute what files should be included in the export bundle.

    Args:
        repo_root: Repository root path
        include_unused: If True, include all assets; if False, only referenced assets

    Returns:
        ExportPlan with files to include and any issues
    """
    plan = ExportPlan()

    # Build manifest and dependency report
    manifest = build_manifest(repo_root)
    dep_report = audit_dependencies(repo_root, manifest=manifest)

    # Collect runtime files
    runtime_files = _collect_runtime_files(repo_root)
    plan.files.extend(runtime_files)

    # Collect content files
    content_files = _collect_content_files(repo_root)
    plan.files.extend(content_files)

    # Determine required assets from dependency graph
    required_assets: set[str] = set()
    for ref in dep_report.references:
        required_assets.add(ref.asset_id)

    # Always include prefabs.json if it exists
    if (repo_root / "assets" / "prefabs.json").exists():
        required_assets.add("assets/prefabs.json")

    # Collect asset files
    all_assets = {a["id"]: a for a in manifest.get("assets", [])}

    for asset_id, asset_info in sorted(all_assets.items()):
        src_path = repo_root / asset_id

        if include_unused or asset_id in required_assets:
            if src_path.is_file():
                try:
                    plan.files.append(ExportFile(
                        rel_path=asset_id,
                        src_path=str(src_path.resolve()),
                        sha256=asset_info["sha256"],
                        size=asset_info["size"],
                        category="asset",
                    ))
                except OSError as e:
                    plan.errors.append(f"Cannot read asset {asset_id}: {e}")
        else:
            plan.excluded_assets.append(asset_id)

    # Check for missing dependencies
    for dep in dep_report.missing:
        plan.missing_deps.append(dep.asset_id)

    # Propagate errors from dependency report
    plan.errors.extend(dep_report.errors)

    # Sort files for determinism
    plan.files.sort(key=lambda f: f.rel_path)
    plan.excluded_assets.sort()
    plan.missing_deps.sort()

    return plan


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #

def build_bundle(
    repo_root: Path,
    output_dir: Path,
    *,
    include_unused: bool = False,
    fail_on_missing: bool = True,
) -> tuple[int, BundleManifest | None]:
    """Build an export bundle.

    Args:
        repo_root: Repository root path
        output_dir: Output directory for the bundle
        include_unused: If True, include all assets
        fail_on_missing: If True, fail if there are missing dependencies

    Returns:
        Tuple of (exit_code, manifest or None)
    """
    # Compute plan
    plan = compute_export_plan(repo_root, include_unused=include_unused)

    # Check for issues
    if fail_on_missing and plan.missing_deps:
        print(f"[export-bundle] ERROR: {len(plan.missing_deps)} missing dependencies:")
        for dep in plan.missing_deps[:10]:
            print(f"  - {dep}")
        if len(plan.missing_deps) > 10:
            print(f"  ... and {len(plan.missing_deps) - 10} more")
        return 1, None

    if plan.errors:
        print(f"[export-bundle] ERROR: {len(plan.errors)} errors:")
        for err in plan.errors[:10]:
            print(f"  - {err}")
        return 1, None

    # Prepare output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Copy files
    copied_files: list[dict[str, Any]] = []
    for export_file in plan.files:
        dest_path = output_dir / export_file.rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(export_file.src_path, dest_path)
            copied_files.append(export_file.to_dict())
        except OSError as e:
            print(f"[export-bundle] ERROR: Failed to copy {export_file.rel_path}: {e}")
            return 1, None

    # Create bundle manifest
    manifest = BundleManifest(
        version=BUNDLE_MANIFEST_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
        repo_root=repo_root.resolve().as_posix(),
        file_count=len(copied_files),
        total_size=sum(f.size for f in plan.files),
        files=copied_files,
    )

    # Write manifest
    manifest_path = output_dir / "bundle_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2, sort_keys=True)
        f.write("\n")

    return 0, manifest


# --------------------------------------------------------------------------- #
# Diffing
# --------------------------------------------------------------------------- #

def load_bundle_manifest(bundle_dir: Path) -> BundleManifest | None:
    """Load a bundle manifest from a directory."""
    manifest_path = bundle_dir / "bundle_manifest.json"
    if not manifest_path.exists():
        return None

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return BundleManifest.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return None


def diff_bundles(bundle_a: Path, bundle_b: Path) -> BundleDiff:
    """Compare two bundles and return the differences.

    Args:
        bundle_a: Path to first bundle (baseline)
        bundle_b: Path to second bundle (comparison)

    Returns:
        BundleDiff with added, removed, and changed files
    """
    diff = BundleDiff()

    manifest_a = load_bundle_manifest(bundle_a)
    manifest_b = load_bundle_manifest(bundle_b)

    if manifest_a is None or manifest_b is None:
        # Fall back to direct file comparison
        files_a = _scan_bundle_files(bundle_a)
        files_b = _scan_bundle_files(bundle_b)
    else:
        files_a = {f["path"]: f["sha256"] for f in manifest_a.files}
        files_b = {f["path"]: f["sha256"] for f in manifest_b.files}

    all_paths = sorted(set(files_a.keys()) | set(files_b.keys()))

    for path in all_paths:
        in_a = path in files_a
        in_b = path in files_b

        if in_a and in_b:
            if files_a[path] == files_b[path]:
                diff.unchanged.append(path)
            else:
                diff.changed.append(path)
        elif in_a:
            diff.removed.append(path)
        else:
            diff.added.append(path)

    return diff


def _scan_bundle_files(bundle_dir: Path) -> dict[str, str]:
    """Scan a bundle directory and compute file hashes."""
    files: dict[str, str] = {}

    if not bundle_dir.is_dir():
        return files

    for root, dirs, filenames in os.walk(bundle_dir, topdown=True):
        dirs[:] = sorted(dirs)

        for filename in sorted(filenames):
            if filename == "bundle_manifest.json":
                continue

            file_path = Path(root) / filename
            rel_path = file_path.relative_to(bundle_dir).as_posix()

            try:
                files[rel_path] = compute_sha256(file_path)
            except OSError:
                continue

    return files


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cmd_build(args: argparse.Namespace) -> int:
    """Build an export bundle."""
    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.out)

    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    include_unused = getattr(args, "include_unused", False)
    fail_on_missing = not getattr(args, "allow_missing", False)

    print(f"[export-bundle] building bundle from {repo_root}...")

    exit_code, manifest = build_bundle(
        repo_root,
        output_dir,
        include_unused=include_unused,
        fail_on_missing=fail_on_missing,
    )

    if exit_code == 0 and manifest is not None:
        print(f"[export-bundle] OK - {manifest.file_count} files ({manifest.total_size:,} bytes)")
        print(f"[export-bundle] wrote bundle to {output_dir}")

    return exit_code


def _cmd_plan(args: argparse.Namespace) -> int:
    """Print export plan without building."""
    repo_root = Path(args.repo_root).resolve()
    include_unused = getattr(args, "include_unused", False)

    print(f"[export-bundle] computing plan for {repo_root}...")

    plan = compute_export_plan(repo_root, include_unused=include_unused)
    print(plan.summary())

    if getattr(args, "json", False):
        print("\nJSON output:")
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))

    if getattr(args, "list_files", False):
        print("\nFiles to include:")
        for f in plan.files:
            print(f"  {f.category:8s} {f.rel_path}")

    if plan.excluded_assets and getattr(args, "list_excluded", False):
        print("\nExcluded assets (unused):")
        for asset in plan.excluded_assets:
            print(f"  - {asset}")

    return 0 if plan.ok else 1


def _cmd_diff(args: argparse.Namespace) -> int:
    """Compare two bundles."""
    bundle_a = Path(args.bundle_a).resolve()
    bundle_b = Path(args.bundle_b).resolve()

    if not bundle_a.is_dir():
        print(f"[export-bundle] ERROR: bundle_a not found: {bundle_a}")
        return 1

    if not bundle_b.is_dir():
        print(f"[export-bundle] ERROR: bundle_b not found: {bundle_b}")
        return 1

    print(f"[export-bundle] comparing {bundle_a} vs {bundle_b}...")

    diff = diff_bundles(bundle_a, bundle_b)
    print(diff.summary())

    if getattr(args, "json", False):
        print("\nJSON output:")
        print(json.dumps(diff.to_dict(), indent=2, sort_keys=True))

    return 0 if not diff.has_changes else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="export_bundle",
        description="Deterministic export bundle builder",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build
    build_parser = subparsers.add_parser("build", help="Build export bundle")
    build_parser.add_argument("--repo-root", default=".", help="Repository root")
    build_parser.add_argument("--out", default="dist/bundle", help="Output directory")
    build_parser.add_argument("--include-unused", action="store_true", help="Include unused assets")
    build_parser.add_argument("--allow-missing", action="store_true", help="Don't fail on missing deps")
    build_parser.set_defaults(func=_cmd_build)

    # plan
    plan_parser = subparsers.add_parser("plan", help="Print export plan")
    plan_parser.add_argument("--repo-root", default=".", help="Repository root")
    plan_parser.add_argument("--include-unused", action="store_true", help="Include unused assets")
    plan_parser.add_argument("--json", action="store_true", help="Output JSON")
    plan_parser.add_argument("--list-files", action="store_true", help="List all files")
    plan_parser.add_argument("--list-excluded", action="store_true", help="List excluded assets")
    plan_parser.set_defaults(func=_cmd_plan)

    # diff
    diff_parser = subparsers.add_parser("diff", help="Compare two bundles")
    diff_parser.add_argument("--bundle-a", required=True, help="First bundle (baseline)")
    diff_parser.add_argument("--bundle-b", required=True, help="Second bundle (comparison)")
    diff_parser.add_argument("--json", action="store_true", help="Output JSON")
    diff_parser.set_defaults(func=_cmd_diff)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
