"""Deterministic export bundle builder.

This module produces shippable bundles using the asset manifest and dependency
graph. It copies only required assets + runtime code/config and writes a
bundle_manifest.json with hashes of shipped files.

Given a creator's project (``config.json`` and ``packs/``, no ``engine/`` of its own), the bundle is a standalone
game: the project's ``main.py``, ``config.json``, ``packs/``, ``locales/*.json`` and every file in its ``assets/``
(Mesh plays some of them by name, such as the interface sounds), with the installed Mesh engine package as its
runtime and the engine's interface text (``share/mesh-engine/locales``). It runs with
``python main.py`` wherever Mesh's dependencies (arcade, pillow, jsonschema) are installed, without Mesh itself.

Replacing an earlier export (F4, #422): the new bundle is built and checked in ``.<name>~new`` beside the output
folder, and only then handed over: the earlier bundle is renamed to ``.<name>~old``, the new one to ``<name>``, and the
old one deleted. If the second rename fails, the first is undone; if that fails too, both folders are kept and named.
The two renames are not atomic together: an export stopped between them (killed, power cut) leaves ``<name>`` absent
and ``.<name>~old`` holding the previous bundle, which the next export to that folder puts back before anything else
(``_recover``). A ``.<name>~new`` left behind is an unfinished or unpublished build and is removed. Only an empty folder
or one holding exactly an earlier bundle (its manifest's files, plus the bytecode Python writes beside them when the
game runs) is ever replaced: other files there (an older game's saves, anything of the user's) stop the export, as
does a link or junction anywhere in it. One export at a time per output folder.

Usage:
    python -m engine.tooling.export_bundle build --repo-root . --out dist/bundle
    python -m engine.tooling.export_bundle plan --repo-root .
    python -m engine.tooling.export_bundle diff --bundle-a dist/bundle1 --bundle-b dist/bundle2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.tooling.asset_manifest import (
    audit_dependencies,
    build_manifest,
    compute_sha256,
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
PROJECT_CONTENT_DIRS: tuple[str, ...] = ("packs",)  # a creator's project keeps its rooms and worlds here


def is_project(root: Path) -> bool:
    """A creator's Mesh project (its content in ``packs/``, run by an installed Mesh), not the engine's source tree."""
    return (root / "config.json").is_file() and (root / "packs").is_dir() and not (root / "engine").is_dir()


def _runtime_dirs(repo_root: Path) -> list[tuple[str, Path]]:
    """(name in the bundle, folder): the engine's own runtime folders, or for a project the installed engine package."""
    if is_project(repo_root):
        import engine  # noqa: PLC0415

        return [("engine", Path(engine.__file__).resolve().parent)]
    return [(name, repo_root / name) for name in RUNTIME_DIRS]


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
    provenance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "version": self.version,
            "created_at": self.created_at,
            "repo_root": self.repo_root,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "files": self.files,
        }
        if self.provenance:
            d["provenance"] = self.provenance
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BundleManifest":
        return cls(
            version=data.get("version", 1),
            created_at=data.get("created_at", ""),
            repo_root=data.get("repo_root", ""),
            file_count=data.get("file_count", 0),
            total_size=data.get("total_size", 0),
            files=data.get("files", []),
            provenance=data.get("provenance"),
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
    project = is_project(repo_root)
    for dir_name, dir_path in _runtime_dirs(repo_root):
        if not dir_path.is_dir():
            continue

        for root, dirs, filenames in os.walk(dir_path, topdown=True):
            # Filter directories in-place
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".mypy_cache"))

            for filename in sorted(filenames):
                file_path = Path(root) / filename
                rel_path = f"{dir_name}/{file_path.relative_to(dir_path).as_posix()}"

                # The installed engine package goes whole (minus caches): it holds no tests, and modules such as
                # engine/self_test.py are part of it.
                cache = "__pycache__" in rel_path or filename.endswith((".pyc", ".pyo"))
                if cache if project else _should_exclude_runtime(rel_path, filename):
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

    if project:
        files += _project_locale_files(repo_root)
    return files


def _project_locale_files(repo_root: Path) -> list[ExportFile]:
    """A project's interface text (H9.2): the engine's own ``locales/*.json`` from the running Mesh (an install's
    ``share/mesh-engine``, the wheel's allow-list) at the same place in the bundle, and the project's own
    ``locales/*.json``, which ``engine.i18n`` lays over them, at ``locales/``. Before, exports had neither and
    their players saw keys such as ``UI_SETTINGS_SAVED``."""
    from engine.repo_root import BUNDLED_SHARE, bundled_dir  # noqa: PLC0415

    files: list[ExportFile] = []
    for folder, dest, category in ((bundled_dir("locales"), "/".join((*BUNDLED_SHARE, "locales")), "runtime"),
                                   (repo_root / "locales", "locales", "content")):
        for src in sorted(folder.glob("*.json")) if folder.is_dir() else ():
            if src.is_file():
                files.append(ExportFile(rel_path=f"{dest}/{src.name}", src_path=str(src.resolve()),
                                        sha256=compute_sha256(src), size=src.stat().st_size, category=category))
    return files


def _collect_content_files(repo_root: Path) -> list[ExportFile]:
    """Collect content files (scenes, worlds)."""
    files: list[ExportFile] = []

    for dir_name in CONTENT_DIRS + (PROJECT_CONTENT_DIRS if is_project(repo_root) else ()):
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
    include_unused = include_unused or is_project(repo_root)  # a project ships all of its own assets

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
# Replacing an earlier export safely (F4)
# --------------------------------------------------------------------------- #

MANIFEST_NAME = "bundle_manifest.json"
RENAME_RETRIES = (0.05, 0.1, 0.2, 0.4, 0.8)  # (Windows: an indexer or antivirus may hold a just-written file a moment)
_BYTECODE = re.compile(r"^(?P<dir>(?:.+/)?)__pycache__/(?P<stem>[^/]+?)\.[^/.]+(?:\.opt-\d)?\.pyc$")


class ExportError(Exception):
    """An export that stopped before it could finish (the message says why and where everything is)."""


class ExportKept(ExportError):
    """The new bundle could not be put in place nor the earlier one back: both are kept, where the message says."""


def _staging_paths(output_dir: Path) -> tuple[Path, Path]:
    """Where the replacement is built (``.<name>~new``) and the earlier bundle waits (``.<name>~old``)."""
    return output_dir.with_name(f".{output_dir.name}~new"), output_dir.with_name(f".{output_dir.name}~old")


def _is_link(path: Path) -> bool:
    """A symbolic link, or on Windows any reparse point (a junction, a mount point): never followed or emptied."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)  # REPARSE_POINT


def _bundle_problems(folder: Path, *, empty_ok: bool = True) -> list[str]:
    """Why ``folder`` isn't an empty folder (when ``empty_ok``) or an earlier bundle as this exporter wrote it ([] when
    it is one)."""
    if _is_link(folder):
        return [f"{folder} is a link or junction"]
    if not folder.is_dir():
        return [f"{folder} is not a folder"]
    if not any(folder.iterdir()):
        return [] if empty_ok else [f"{folder} is empty"]
    try:
        data = json.loads((folder / MANIFEST_NAME).read_text(encoding="utf-8"))
        listed = {str(entry["path"]) for entry in data["files"]}
        if not isinstance(data.get("version"), int):
            raise TypeError("no version")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"it has no readable {MANIFEST_NAME} ({type(exc).__name__})"]
    if any(p.startswith(("/", "\\")) or ":" in p or ".." in p.replace("\\", "/").split("/") for p in listed):
        return [f"its {MANIFEST_NAME} lists paths outside the folder"]
    problems: list[str] = []
    for root, dirs, files in os.walk(folder):
        here = Path(root)
        for name in sorted(dirs + files):
            path = here / name
            rel = path.relative_to(folder).as_posix()
            if _is_link(path):
                problems.append(f"{rel} is a link or junction")
            elif name in files and rel != MANIFEST_NAME and rel not in listed:
                byte = _BYTECODE.match(rel)
                if not (byte and f"{byte['dir']}{byte['stem']}.py" in listed):
                    problems.append(rel)
        dirs[:] = [d for d in dirs if not _is_link(here / d)]
    return problems


def _remove_tree(path: Path) -> None:
    """Delete a folder this export made or replaced; never a link or junction, nor anything one points to."""
    if _is_link(path):
        raise OSError(f"{path} is a link or junction; not removed")
    shutil.rmtree(path)  # (since Python 3.8 it removes junctions inside without entering them)


def _rename(src: Path, dst: Path) -> None:
    """``os.rename`` (never over an existing ``dst``), retried briefly when Windows says the folder is in use."""
    for delay in (*RENAME_RETRIES, None):
        if os.path.lexists(dst):
            raise FileExistsError(f"{dst} already exists")
        try:
            os.rename(src, dst)
            return
        except PermissionError:
            if delay is None or sys.platform != "win32":
                raise
            time.sleep(delay)


def _recover(output_dir: Path) -> None:
    """Finish what an export stopped part way left beside ``output_dir`` (see the module's docstring)."""
    staging, backup = _staging_paths(output_dir)
    if os.path.lexists(backup):
        if _is_link(backup) or not backup.is_dir():
            raise ExportError(f"{backup} is in the way and is not an earlier export; move it and export again")
        if not os.path.lexists(output_dir):
            _rename(backup, output_dir)
            print(f"[export-bundle] restored the previous export to {output_dir} (an earlier export stopped part way)")
        elif not _bundle_problems(output_dir, empty_ok=False) and not _bundle_problems(backup):
            _remove_tree(backup)  # (the export after it finished: it is a superseded copy)
        else:
            raise ExportError(f"{backup} holds a previous export and {output_dir} is not a complete one; keep the one "
                              "you want and move the other away, then export again")
    if os.path.lexists(staging):
        if _is_link(staging) or not staging.is_dir():
            raise ExportError(f"{staging} is in the way and is not an unfinished export; move it and export again")
        _remove_tree(staging)  # (an unfinished or unpublished build: never the only copy of anything)


def _write_manifest(path: Path, manifest: BundleManifest) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2, sort_keys=True)
        f.write("\n")


def _copy_checked(export_file: ExportFile, dest: Path) -> None:
    """Copy one file (contents, then times and mode as ``shutil.copy2``), hashing what is written as it goes: it must
    be what the plan hashed, so a file changed since (a creator saving mid-export) stops the export."""
    digest = hashlib.sha256()
    with open(export_file.src_path, "rb") as src, open(dest, "wb") as out:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            digest.update(chunk)
            out.write(chunk)
    shutil.copystat(export_file.src_path, dest)
    if digest.hexdigest() != export_file.sha256:
        raise ExportError(f"{export_file.rel_path} changed while it was exported; export again")


def _validate_staged(staging: Path, manifest: BundleManifest) -> None:
    """The staged bundle is exactly what its manifest says: every file there at its size (each was hashed as it was
    copied), nothing else, and the manifest reads back as written."""
    written = load_bundle_manifest(staging)
    if written is None or written.to_dict() != manifest.to_dict():
        raise ExportError(f"the new {MANIFEST_NAME} could not be read back as written")
    for entry in manifest.files:
        path = staging / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise ExportError(f"{entry['path']} is missing from the new bundle or has the wrong size")
    found = sum(len(files) for _root, _dirs, files in os.walk(staging))
    if found != len(manifest.files) + 1:
        raise ExportError(f"the new bundle holds {found} files, its manifest {len(manifest.files) + 1}")


def _publish(staging: Path, output_dir: Path) -> None:
    """Hand the checked bundle over: the earlier one aside, the new one in, the earlier one deleted. Raises
    ExportError (the earlier bundle back in place, or both kept and named) when it can't."""
    _, backup = _staging_paths(output_dir)
    replacing = os.path.lexists(output_dir)
    if replacing:
        try:
            _rename(output_dir, backup)
        except OSError as exc:
            raise ExportError(f"could not move the earlier export aside ({exc}); is the game running from "
                              f"{output_dir}? It is unchanged") from exc
    try:
        _rename(staging, output_dir)
    except BaseException as exc:  # (an interrupt here too: put the earlier bundle back before going)
        if replacing:
            try:
                _rename(backup, output_dir)
            except OSError as again:
                raise ExportKept(f"could not put the new export in place ({exc}) nor the earlier one back ({again}): "
                                 f"the earlier export is in {backup}, the new one in {staging}") from again
        if not isinstance(exc, Exception):
            raise
        raise ExportError(f"could not put the new export in place ({exc}); "
                          + (f"the earlier export is back in {output_dir}" if replacing else "nothing was changed")) from exc
    if replacing:
        try:
            _remove_tree(backup)
        except OSError as exc:
            print(f"[export-bundle] WARNING: the new export is in place, but the earlier one could not be deleted "
                  f"({exc}); it is in {backup}")


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #

def build_bundle(
    repo_root: Path,
    output_dir: Path,
    *,
    include_unused: bool = False,
    fail_on_missing: bool = True,
    deterministic: bool = False,
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

    # The output folder: only ever an empty one or an earlier bundle, replaced once the new one is complete (F4)
    staging, _ = _staging_paths(output_dir)
    try:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        _recover(output_dir)
        if os.path.lexists(output_dir):
            problems = _bundle_problems(output_dir)
            if problems:
                print(f"[export-bundle] ERROR: {output_dir} is not empty and is not an earlier bundle "
                      f"({len(problems)} other file(s), e.g. {', '.join(problems[:3])}); nothing was changed. Choose "
                      "another folder, or move those files out")
                return 1, None
        staging.mkdir()
    except (OSError, ExportError) as exc:
        print(f"[export-bundle] ERROR: {exc}")
        return 1, None
    try:
        manifest = _stage(plan, repo_root, staging, deterministic=deterministic)
        _publish(staging, output_dir)
    except ExportKept as exc:
        print(f"[export-bundle] ERROR: {exc}")
        return 1, None
    except (OSError, ExportError) as exc:
        print(f"[export-bundle] ERROR: {exc}")
        try:
            if os.path.lexists(staging):
                _remove_tree(staging)
        except OSError as again:
            print(f"[export-bundle] WARNING: the unfinished export in {staging} could not be deleted ({again}); the "
                  "next export to this folder removes it")
        return 1, None
    except BaseException:  # (interrupted: the unfinished build goes; the next export recovers anything else)
        if os.path.lexists(staging) and not _is_link(staging):
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return 0, manifest


def _stage(plan: ExportPlan, repo_root: Path, staging: Path, *, deterministic: bool) -> BundleManifest:
    """Build the whole bundle in ``staging``: copy, write the manifest, check it. Raises OSError or ExportError."""
    # Copy files
    copied_files: list[dict[str, Any]] = []
    for export_file in plan.files:
        dest_path = staging / export_file.rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            _copy_checked(export_file, dest_path)
            copied_files.append(export_file.to_dict())
        except OSError as e:
            raise ExportError(f"Failed to copy {export_file.rel_path}: {e}") from e

    # Create bundle manifest
    from engine.provenance import get_provenance, provenance_to_dict

    if deterministic:
        created_at = "1980-01-01T00:00:00Z"
        repo_root_field = "."
        provenance = provenance_to_dict(get_provenance(deterministic=True))
    else:
        created_at = datetime.now(timezone.utc).isoformat()
        repo_root_field = "." if is_project(repo_root) else repo_root.resolve().as_posix()  # no path of the maker's
        provenance = provenance_to_dict(get_provenance())

    manifest = BundleManifest(
        version=BUNDLE_MANIFEST_VERSION,
        created_at=created_at,
        repo_root=repo_root_field,
        file_count=len(copied_files),
        total_size=sum(f.size for f in plan.files),
        files=copied_files,
        provenance=provenance,
    )

    # Write manifest, then check the whole bundle before it replaces anything
    _write_manifest(staging / MANIFEST_NAME, manifest)
    _validate_staged(staging, manifest)
    return manifest


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
