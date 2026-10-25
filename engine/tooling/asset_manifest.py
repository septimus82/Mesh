"""Asset manifest generation and dependency auditing.

This module provides deterministic asset manifest generation and dependency
graph extraction for the Mesh engine. It scans asset roots and builds a
manifest with hashes, then parses scenes/prefabs to extract references
and detect missing dependencies.

Usage:
    python -m tooling.asset_manifest build --repo-root . --out artifacts/asset_manifest.json
    python -m tooling.asset_manifest audit --repo-root . --out artifacts/asset_deps.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Asset Types
# --------------------------------------------------------------------------- #

ASSET_TYPE_MAP: dict[str, str] = {
    # Images
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".gif": "image",
    ".tga": "image",
    ".webp": "image",
    # Audio
    ".wav": "audio",
    ".ogg": "audio",
    ".mp3": "audio",
    ".flac": "audio",
    # Fonts
    ".ttf": "font",
    ".otf": "font",
    ".fnt": "font",
    # Data
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    # Shaders
    ".glsl": "shader",
    ".vert": "shader",
    ".frag": "shader",
    # Tilemaps
    ".tmx": "tilemap",
    ".tsx": "tileset",
    # Other
    ".txt": "text",
    ".md": "markdown",
}


def get_asset_type(path: Path) -> str:
    """Get asset type from file extension."""
    ext = path.suffix.lower()
    return ASSET_TYPE_MAP.get(ext, "other")


# --------------------------------------------------------------------------- #
# Manifest Entry
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """A single asset in the manifest."""

    asset_id: str  # Logical ID (relative path from repo root)
    asset_type: str  # image/audio/font/json/etc.
    sha256: str  # Content hash
    size: int  # File size in bytes
    mtime: float  # Modification time (Unix timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.asset_id,
            "type": self.asset_type,
            "sha256": self.sha256,
            "size": self.size,
            "mtime": self.mtime,
        }


# --------------------------------------------------------------------------- #
# Manifest Builder
# --------------------------------------------------------------------------- #

def compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_asset_roots(
    repo_root: Path,
    *,
    asset_dirs: tuple[str, ...] = ("assets",),
    skip_patterns: tuple[str, ...] = (".git", "__pycache__", ".mesh"),
) -> list[ManifestEntry]:
    """Scan asset directories and build manifest entries.

    Returns entries sorted by asset_id for determinism.
    """
    entries: list[ManifestEntry] = []

    for asset_dir_name in asset_dirs:
        asset_dir = repo_root / asset_dir_name
        if not asset_dir.exists():
            continue

        # Walk deterministically (sorted)
        for root, dirs, files in os.walk(asset_dir, topdown=True):
            # Sort and filter directories in-place for determinism
            dirs[:] = sorted(
                d for d in dirs
                if d not in skip_patterns and not d.startswith(".")
            )
            # Sort files for determinism
            for filename in sorted(files):
                if filename.startswith("."):
                    continue

                file_path = Path(root) / filename
                if not file_path.is_file():
                    continue

                try:
                    rel_path = file_path.relative_to(repo_root).as_posix()
                    stat = file_path.stat()
                    sha256 = compute_sha256(file_path)

                    entries.append(ManifestEntry(
                        asset_id=rel_path,
                        asset_type=get_asset_type(file_path),
                        sha256=sha256,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                    ))
                except (OSError, ValueError):
                    # Skip files we can't read or aren't under repo root
                    continue

    # Sort by asset_id for determinism
    entries.sort(key=lambda e: e.asset_id)
    return entries


def build_manifest(
    repo_root: Path,
    *,
    asset_dirs: tuple[str, ...] = ("assets",),
) -> dict[str, Any]:
    """Build a complete asset manifest.

    Returns a dict suitable for JSON serialization.
    """
    entries = scan_asset_roots(repo_root, asset_dirs=asset_dirs)

    return {
        "version": 1,
        "repo_root": repo_root.resolve().as_posix(),
        "asset_count": len(entries),
        "assets": [e.to_dict() for e in entries],
    }


# --------------------------------------------------------------------------- #
# Dependency Extraction
# --------------------------------------------------------------------------- #

@dataclass
class AssetReference:
    """A reference to an asset from a scene or prefab."""

    asset_id: str  # The referenced asset path
    source_file: str  # The file containing the reference
    source_type: str  # "scene" or "prefab"
    entity_name: str | None  # Entity name if applicable
    field_path: str  # JSON path to the reference (e.g., "entities[0].sprite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_file": self.source_file,
            "source_type": self.source_type,
            "entity_name": self.entity_name,
            "field_path": self.field_path,
        }


@dataclass
class MissingDependency:
    """A missing asset dependency with blame chain."""

    asset_id: str  # The missing asset
    references: list[AssetReference]  # Where it's referenced from
    hint: str  # Suggested fix

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "references": [r.to_dict() for r in self.references],
            "hint": self.hint,
        }


@dataclass
class DependencyReport:
    """Report of asset dependencies and issues."""

    references: list[AssetReference] = field(default_factory=list)
    missing: list[MissingDependency] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.missing) == 0 and len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reference_count": len(self.references),
            "missing_count": len(self.missing),
            "error_count": len(self.errors),
            "references": [r.to_dict() for r in self.references],
            "missing": [m.to_dict() for m in self.missing],
            "errors": self.errors,
        }


def _extract_refs_from_entity(
    entity: dict[str, Any],
    index: int,
    source_file: str,
    source_type: str,
) -> list[AssetReference]:
    """Extract asset references from an entity dict."""
    refs: list[AssetReference] = []
    entity_name = entity.get("name") or entity.get("mesh_name") or f"entity_{index}"

    # Direct sprite reference
    sprite = entity.get("sprite")
    if isinstance(sprite, str) and sprite:
        refs.append(AssetReference(
            asset_id=sprite,
            source_file=source_file,
            source_type=source_type,
            entity_name=entity_name,
            field_path=f"entities[{index}].sprite",
        ))

    # Sprite sheet path
    sprite_sheet = entity.get("sprite_sheet")
    if isinstance(sprite_sheet, dict):
        ss_path = sprite_sheet.get("path")
        if isinstance(ss_path, str) and ss_path:
            refs.append(AssetReference(
                asset_id=ss_path,
                source_file=source_file,
                source_type=source_type,
                entity_name=entity_name,
                field_path=f"entities[{index}].sprite_sheet.path",
            ))

    # Animation sprite paths (if any have explicit paths)
    animations = entity.get("animations")
    if isinstance(animations, dict):
        for anim_name, anim_data in animations.items():
            if isinstance(anim_data, dict):
                anim_sprite = anim_data.get("sprite")
                if isinstance(anim_sprite, str) and anim_sprite:
                    refs.append(AssetReference(
                        asset_id=anim_sprite,
                        source_file=source_file,
                        source_type=source_type,
                        entity_name=entity_name,
                        field_path=f"entities[{index}].animations.{anim_name}.sprite",
                    ))

    return refs


def _extract_refs_from_scene(
    scene_data: dict[str, Any],
    source_file: str,
) -> list[AssetReference]:
    """Extract asset references from a scene dict."""
    refs: list[AssetReference] = []

    # Scene-level settings
    settings = scene_data.get("settings") or {}
    music = settings.get("music") or scene_data.get("music")
    if isinstance(music, str) and music:
        refs.append(AssetReference(
            asset_id=music,
            source_file=source_file,
            source_type="scene",
            entity_name=None,
            field_path="settings.music",
        ))

    # Background layers
    background_layers = scene_data.get("background_layers") or []
    for i, layer in enumerate(background_layers):
        if isinstance(layer, dict):
            layer_sprite = layer.get("sprite")
            if isinstance(layer_sprite, str) and layer_sprite:
                refs.append(AssetReference(
                    asset_id=layer_sprite,
                    source_file=source_file,
                    source_type="scene",
                    entity_name=None,
                    field_path=f"background_layers[{i}].sprite",
                ))

    # Tilemap references
    tilemap = scene_data.get("tilemap")
    if isinstance(tilemap, dict):
        tileset = tilemap.get("tileset")
        if isinstance(tileset, str) and tileset:
            refs.append(AssetReference(
                asset_id=tileset,
                source_file=source_file,
                source_type="scene",
                entity_name=None,
                field_path="tilemap.tileset",
            ))

    # Entities
    entities = scene_data.get("entities") or []
    for i, entity in enumerate(entities):
        if isinstance(entity, dict):
            refs.extend(_extract_refs_from_entity(entity, i, source_file, "scene"))

    return refs


def _extract_refs_from_prefab(
    prefab_data: dict[str, Any],
    source_file: str,
) -> list[AssetReference]:
    """Extract asset references from a prefab dict."""
    refs: list[AssetReference] = []
    prefab_id = prefab_data.get("id") or "<unknown>"

    entity = prefab_data.get("entity") or {}
    if isinstance(entity, dict):
        # Direct sprite
        sprite = entity.get("sprite")
        if isinstance(sprite, str) and sprite:
            refs.append(AssetReference(
                asset_id=sprite,
                source_file=source_file,
                source_type="prefab",
                entity_name=prefab_id,
                field_path=f"prefab[{prefab_id}].entity.sprite",
            ))

        # Sprite sheet
        sprite_sheet = entity.get("sprite_sheet")
        if isinstance(sprite_sheet, dict):
            ss_path = sprite_sheet.get("path")
            if isinstance(ss_path, str) and ss_path:
                refs.append(AssetReference(
                    asset_id=ss_path,
                    source_file=source_file,
                    source_type="prefab",
                    entity_name=prefab_id,
                    field_path=f"prefab[{prefab_id}].entity.sprite_sheet.path",
                ))

        # Animations
        animations = entity.get("animations")
        if isinstance(animations, dict):
            for anim_name, anim_data in animations.items():
                if isinstance(anim_data, dict):
                    anim_sprite = anim_data.get("sprite")
                    if isinstance(anim_sprite, str) and anim_sprite:
                        refs.append(AssetReference(
                            asset_id=anim_sprite,
                            source_file=source_file,
                            source_type="prefab",
                            entity_name=prefab_id,
                            field_path=f"prefab[{prefab_id}].entity.animations.{anim_name}.sprite",
                        ))

    return refs


def scan_scenes(repo_root: Path) -> list[tuple[str, dict[str, Any]]]:
    """Scan and load all scene files.

    Returns list of (rel_path, scene_data) tuples, sorted by path.
    """
    scenes: list[tuple[str, dict[str, Any]]] = []
    scenes_dir = repo_root / "scenes"

    if not scenes_dir.exists():
        return scenes

    for scene_file in sorted(scenes_dir.glob("*.json")):
        try:
            rel_path = scene_file.relative_to(repo_root).as_posix()
            with scene_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            scenes.append((rel_path, data))
        except (OSError, json.JSONDecodeError):
            continue

    return scenes


def scan_prefabs(repo_root: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    """Scan and load all prefab files.

    Returns list of (rel_path, prefab_list) tuples, sorted by path.
    """
    prefabs: list[tuple[str, list[dict[str, Any]]]] = []

    # Main prefabs.json
    main_prefabs = repo_root / "assets" / "prefabs.json"
    if main_prefabs.exists():
        try:
            rel_path = main_prefabs.relative_to(repo_root).as_posix()
            with main_prefabs.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                prefabs.append((rel_path, data))
        except (OSError, json.JSONDecodeError):
            pass

    # Pack prefabs
    packs_dir = repo_root / "packs"
    if packs_dir.exists():
        for pack_prefabs in sorted(packs_dir.glob("*/prefabs.json")):
            try:
                rel_path = pack_prefabs.relative_to(repo_root).as_posix()
                with pack_prefabs.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    prefabs.append((rel_path, data))
            except (OSError, json.JSONDecodeError):
                continue

    return prefabs


def extract_dependencies(repo_root: Path) -> DependencyReport:
    """Extract all asset dependencies from scenes and prefabs."""
    report = DependencyReport()

    # Collect all references
    for scene_path, scene_data in scan_scenes(repo_root):
        try:
            refs = _extract_refs_from_scene(scene_data, scene_path)
            report.references.extend(refs)
        except Exception as e:
            report.errors.append(f"Error parsing scene {scene_path}: {e}")

    for prefab_path, prefab_list in scan_prefabs(repo_root):
        for prefab in prefab_list:
            try:
                refs = _extract_refs_from_prefab(prefab, prefab_path)
                report.references.extend(refs)
            except Exception as e:
                prefab_id = prefab.get("id", "<unknown>")
                report.errors.append(f"Error parsing prefab {prefab_id} in {prefab_path}: {e}")

    # Sort references for determinism
    report.references.sort(key=lambda r: (r.source_file, r.field_path, r.asset_id))

    return report


def audit_dependencies(
    repo_root: Path,
    *,
    manifest: dict[str, Any] | None = None,
) -> DependencyReport:
    """Audit dependencies against the manifest.

    Returns a report with missing dependencies and blame chains.
    """
    # Build manifest if not provided
    if manifest is None:
        manifest = build_manifest(repo_root)

    # Get set of known assets
    known_assets: set[str] = {a["id"] for a in manifest.get("assets", [])}

    # Extract dependencies
    report = extract_dependencies(repo_root)

    # Group references by asset_id
    refs_by_asset: dict[str, list[AssetReference]] = {}
    for ref in report.references:
        refs_by_asset.setdefault(ref.asset_id, []).append(ref)

    # Check for missing assets
    missing_by_id: dict[str, MissingDependency] = {}
    for asset_id, refs in sorted(refs_by_asset.items()):
        if asset_id not in known_assets:
            # Generate hint based on asset type
            ext = Path(asset_id).suffix.lower()
            if ext in (".png", ".jpg", ".jpeg"):
                hint = f"Create image at '{asset_id}' or use 'assets/placeholder.png'"
            elif ext in (".wav", ".ogg", ".mp3"):
                hint = f"Create audio file at '{asset_id}' or remove the reference"
            else:
                hint = f"Create file at '{asset_id}' or update the reference"

            missing_by_id[asset_id] = MissingDependency(
                asset_id=asset_id,
                references=refs,
                hint=hint,
            )

    # Sort missing dependencies for determinism
    report.missing = [missing_by_id[k] for k in sorted(missing_by_id.keys())]

    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cmd_build(args: argparse.Namespace) -> int:
    """Build asset manifest."""
    repo_root = Path(args.repo_root).resolve()
    out_path = Path(args.out)

    if not out_path.is_absolute():
        out_path = repo_root / out_path

    print(f"[asset-manifest] scanning {repo_root}...")
    manifest = build_manifest(repo_root)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write with stable ordering
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"[asset-manifest] wrote {manifest['asset_count']} assets to {out_path}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    """Audit asset dependencies."""
    repo_root = Path(args.repo_root).resolve()
    out_path = Path(args.out)

    if not out_path.is_absolute():
        out_path = repo_root / out_path

    print(f"[asset-audit] scanning {repo_root}...")

    # Build manifest
    manifest = build_manifest(repo_root)

    # Audit dependencies
    report = audit_dependencies(repo_root, manifest=manifest)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write report
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, sort_keys=True)
        f.write("\n")

    # Print summary
    print(f"[asset-audit] found {len(report.references)} references")

    if report.missing:
        print(f"[asset-audit] FAILED - {len(report.missing)} missing dependencies:")
        for dep in report.missing:
            print(f"  - {dep.asset_id}")
            for ref in dep.references[:3]:  # Show first 3 references
                print(f"      referenced by: {ref.source_file} ({ref.field_path})")
            if len(dep.references) > 3:
                print(f"      ... and {len(dep.references) - 3} more")
            print(f"      hint: {dep.hint}")
        return 1

    if report.errors:
        print(f"[asset-audit] FAILED - {len(report.errors)} errors:")
        for err in report.errors:
            print(f"  - {err}")
        return 1

    print("[asset-audit] ok - all dependencies resolved")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    """List manifest contents."""
    manifest_path = Path(args.manifest)

    if not manifest_path.exists():
        print(f"[asset-manifest] ERROR: manifest not found: {manifest_path}")
        return 1

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    assets = manifest.get("assets", [])
    print(f"Asset Manifest ({len(assets)} assets):")
    print("=" * 60)

    type_filter = getattr(args, "type", None)
    for asset in assets:
        if type_filter and asset.get("type") != type_filter:
            continue
        print(f"  {asset['type']:8s} {asset['id']}")

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="asset_manifest",
        description="Asset manifest generation and dependency auditing",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build
    build_parser = subparsers.add_parser("build", help="Build asset manifest")
    build_parser.add_argument("--repo-root", default=".", help="Repository root")
    build_parser.add_argument("--out", default="artifacts/asset_manifest.json", help="Output path")
    build_parser.set_defaults(func=_cmd_build)

    # audit
    audit_parser = subparsers.add_parser("audit", help="Audit asset dependencies")
    audit_parser.add_argument("--repo-root", default=".", help="Repository root")
    audit_parser.add_argument("--out", default="artifacts/asset_deps.json", help="Output path")
    audit_parser.set_defaults(func=_cmd_audit)

    # list
    list_parser = subparsers.add_parser("list", help="List manifest contents")
    list_parser.add_argument("manifest", help="Manifest JSON path")
    list_parser.add_argument("--type", help="Filter by asset type")
    list_parser.set_defaults(func=_cmd_list)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
