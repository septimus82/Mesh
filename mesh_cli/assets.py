"""Asset and content management commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engine.logging_tools import is_json_mode, suppress_stdout
from engine.persistence_io import dumps_json_deterministic, write_json_atomic
from engine.paths import reset_path_caches, set_content_roots
from engine.repo_root import get_repo_root
from engine.tooling import (
    doctor_command,
    migrate_command,
    polish,
    project_index,
    schema_fix_ids,
)
from engine.sprite_sheet_math import (
    SpriteSheetSliceSpec,
    iter_sprite_sheet_frame_boxes,
    parse_anim_spec,
)


def _single_line_error(text: str) -> str:
    raw = str(text or "")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = " ".join(raw.split())
    return raw


def _parse_bool(value: object, *, default: bool | None = None) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_path_for_json(path: Path | str, *, repo_root: Path | None = None) -> str:
    p = Path(path) if not isinstance(path, Path) else path
    if repo_root is not None and not p.is_absolute():
        p = Path(repo_root) / p
    try:
        p = p.resolve()
    except Exception:
        pass

    root = repo_root
    if root is not None:
        try:
            root = Path(root).resolve()
        except Exception:
            root = Path(root)
        try:
            return p.relative_to(root).as_posix()
        except Exception:
            pass
    return p.as_posix()


def handle(args: argparse.Namespace) -> int:
    if args.command == "assets":
        if getattr(args, "assets_command", None) == "import-sprites":
            return _handle_assets_import_sprites(args)
        if getattr(args, "assets_command", None) == "reload":
            return _handle_assets_reload(args)
        if getattr(args, "assets_command", None) == "audit":
            return _handle_assets_audit(args)
        if getattr(args, "assets_command", None) == "fix-missing":
            return _handle_assets_fix_missing(args)
        if getattr(args, "assets_command", None) == "build-manifest":
            return _handle_assets_build_manifest(args)
        if getattr(args, "assets_command", None) == "audit-deps":
            return _handle_assets_audit_deps(args)
        print("[Mesh][CLI] Error: missing assets subcommand")
        return 2
    if args.command == "index":
        return _handle_index(args)
    if args.command == "doctor-assets":
        return _handle_doctor_assets(args)
    if args.command == "schema-fix-ids":
        return _handle_schema_fix_ids(args)
    if args.command == "migrate":
        return migrate_command.handle_migrate(args)
    if args.command == "polish":
        return _handle_polish(args)
    if args.command == "sprite":
        if getattr(args, "sprite_command", None) == "import-sheet":
            return _handle_sprite_import_sheet(args)
        if getattr(args, "sprite_command", None) == "import-aseprite":
            return _handle_sprite_import_aseprite(args)
        print("[Mesh][CLI] Error: missing sprite subcommand")
        return 2
    return 1


def register(subparsers: argparse._SubParsersAction) -> None:
    # Index
    subparsers.add_parser("index", help="Rebuild project index", description="Rebuild project index")

    # Asset doctor (deterministic JSON report, no engine load)
    doctor_assets_parser = subparsers.add_parser(
        "doctor-assets",
        help="Inventory content/assets deterministically and optionally apply safe fixes (no engine load)",
        description="Inventory content/assets deterministically and optionally apply safe fixes (no engine load)",
    )
    doctor_assets_parser.add_argument("--out", help="Optional path to write JSON output")
    doctor_assets_parser.add_argument("--fix", action="store_true", help="Apply safe auto-fixes in-place")
    doctor_assets_parser.add_argument("--strict", action="store_true", help="Treat warnings as errors where applicable")
    doctor_assets_parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    doctor_assets_parser.add_argument("--pack", action="append", help="Limit prefab checks to a pack id")

    # Schema Fix IDs
    schema_fix_ids_parser = subparsers.add_parser(
        "schema-fix-ids",
        help="Deterministically add missing entity ids (and TriggerZone.zone_id) to scene JSON",
        description="Deterministically add missing entity ids (and TriggerZone.zone_id) to scene JSON",
    )
    schema_fix_ids_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change but do not write files",
    )
    schema_fix_ids_parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Glob(s) or file path(s) to scenes. Default targets shipped scenes.",
    )

    # Polish
    polish_parser = subparsers.add_parser("polish", help="Polish content", description="Polish content")
    polish_parser.add_argument("path", help="Path to content")
    polish_parser.add_argument("--compact-scenes", action="store_true", help="Compact scene files")
    polish_parser.add_argument("--export-graph", action="store_true", help="Export world graph")
    polish_parser.add_argument("--update-lock-audit", action="store_true", help="Update lock audit")

    # Migrate
    migrate_parser = subparsers.add_parser("migrate", help="Migrate content to latest version", description="Migrate content to latest version")
    migrate_parser.add_argument("path", help="Path to content")
    migrate_parser.add_argument("--write", action="store_true", help="Write changes to file")

    # Sprite utilities
    sprite_parser = subparsers.add_parser("sprite", help="Sprite authoring utilities", description="Sprite authoring utilities")
    sprite_subparsers = sprite_parser.add_subparsers(dest="sprite_command", help="Sprite subcommand")
    sprite_import = sprite_subparsers.add_parser(
        "import-sheet",
        help="Import a spritesheet and generate/update a sprite-sheet prefab",
        description="Import a spritesheet and generate/update a sprite-sheet prefab",
    )
    sprite_import.add_argument("image_path", help="Path to spritesheet image")
    sprite_import.add_argument("--prefab-id", required=True, dest="prefab_id", help="Prefab id to create/update")
    sprite_import.add_argument("--frame-w", required=True, dest="frame_w", type=int, help="Frame width in pixels")
    sprite_import.add_argument("--frame-h", required=True, dest="frame_h", type=int, help="Frame height in pixels")
    sprite_import.add_argument("--margin", type=int, default=0, help="Optional margin (pixels)")
    sprite_import.add_argument("--spacing", type=int, default=0, help="Optional spacing (pixels)")
    sprite_import.add_argument("--anchor", help="Optional anchor formatted as x,y")
    sprite_import.add_argument("--hitbox", help="Optional hitbox formatted as x,y,w,h")
    sprite_import.add_argument("--anim", action="append", required=True, help="Animation spec: name:start-end:fps")
    sprite_import.add_argument("--out", required=True, help="Prefab JSON output path (e.g. assets/prefabs.json)")

    sprite_import_aseprite = sprite_subparsers.add_parser(
        "import-aseprite",
        help="Import Aseprite JSON and generate/update a sprite-sheet prefab",
        description="Import Aseprite JSON and generate/update a sprite-sheet prefab",
    )
    sprite_import_aseprite.add_argument("json_path", help="Path to Aseprite JSON export")
    sprite_import_aseprite.add_argument("--prefab-id", required=True, dest="prefab_id", help="Prefab id to create/update")
    sprite_import_aseprite.add_argument("--image", help="Optional override for spritesheet image path")
    sprite_import_aseprite.add_argument("--anchor", help="Optional anchor formatted as x,y")
    sprite_import_aseprite.add_argument("--hitbox", help="Optional hitbox formatted as x,y,w,h")
    sprite_import_aseprite.add_argument("--out", required=True, help="Prefab JSON output path (e.g. assets/prefabs.json)")

    # Asset utilities (grouped under `mesh assets ...`)
    assets_parser = subparsers.add_parser("assets", help="Asset utilities", description="Asset utilities")
    assets_subparsers = assets_parser.add_subparsers(dest="assets_command", help="Asset subcommand")
    import_sprites_parser = assets_subparsers.add_parser(
        "import-sprites",
        help="Scan assets/sprites and append new prefab entries",
        description="Scan assets/sprites and append new prefab entries",
    )
    import_sprites_parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    import_sprites_parser.add_argument(
        "--default-solid",
        default="false",
        help="Default solid flag for new entities (true/false)",
    )
    import_sprites_parser.add_argument(
        "--default-layer",
        default="entities",
        help="Default layer for new entities",
    )
    import_sprites_parser.add_argument(
        "--out",
        default="assets/prefabs.json",
        help="Prefab JSON output path",
    )

    audit_parser = assets_subparsers.add_parser(
        "audit",
        help="Scan asset references deterministically",
        description="Scan asset references deterministically (headless-safe)",
    )
    audit_parser.add_argument("--repo-root", default=".", help="Repo root for pack/content discovery")
    audit_parser.add_argument("--out", default="artifacts/asset_audit.json", help="JSON report output path")
    audit_parser.add_argument("--pack", help="Optional pack id filter")
    audit_parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    audit_parser.add_argument("--with-orphans", action="store_true", help="Detect orphaned assets")
    audit_parser.add_argument("--with-duplicates", action="store_true", help="Detect duplicate assets")
    audit_parser.add_argument("--with-ownership", default=True, type=_parse_bool, help="Enforce pack ownership")
    audit_parser.add_argument("--warn-duplicates", default=True, type=_parse_bool, help="Warn on duplicates")
    audit_parser.add_argument("--fail-missing", default=True, type=_parse_bool, help="Fail on missing assets")
    audit_parser.add_argument("--fail-orphans", default=False, type=_parse_bool, help="Fail on orphaned assets")
    audit_parser.add_argument("--fail-duplicates", default=False, type=_parse_bool, help="Fail on duplicate assets")
    import_sprites_parser.add_argument(
        "--sprites-dir",
        default="assets/sprites",
        help="Sprites directory to scan",
    )
    fix_missing_parser = assets_subparsers.add_parser(
        "fix-missing",
        help="Create stub files for missing sprite references",
        description="Create stub files for missing sprite references based on asset audit output",
    )
    fix_missing_parser.add_argument("--repo-root", default=".", help="Repo root for content discovery")
    fix_missing_parser.add_argument(
        "--audit",
        default="artifacts/asset_audit.json",
        help="Asset audit JSON path to read",
    )
    fix_missing_parser.add_argument(
        "--out",
        default="artifacts/asset_audit_fix.json",
        help="JSON report output path",
    )
    fix_missing_parser.add_argument(
        "--mode",
        choices=["stub", "rewrite"],
        default="stub",
        help="Fix mode: create stub files (stub) or rewrite references (rewrite)",
    )
    fix_missing_parser.add_argument(
        "--placeholder",
        default="assets/placeholder.png",
        help="Placeholder image path for stub/rewrite mode",
    )
    import_sprites_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Repeatable tag for new prefabs",
    )

    assets_reload_parser = assets_subparsers.add_parser(
        "reload",
        help="Reload asset metadata caches (headless)",
        description="Reload lightweight asset metadata caches (headless)",
    )
    assets_reload_parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root for pack/content discovery",
    )

    # Build manifest (deterministic asset inventory with hashes)
    build_manifest_parser = assets_subparsers.add_parser(
        "build-manifest",
        help="Build deterministic asset manifest with hashes",
        description="Scan asset roots and generate a manifest with asset IDs, types, SHA256 hashes, sizes, and mtimes",
    )
    build_manifest_parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root for asset discovery",
    )
    build_manifest_parser.add_argument(
        "--out",
        default="artifacts/asset_manifest.json",
        help="Output manifest path",
    )

    # Audit dependencies (check for missing asset references)
    audit_deps_parser = assets_subparsers.add_parser(
        "audit-deps",
        help="Audit asset dependencies for missing references",
        description="Parse scenes and prefabs to extract asset references and detect missing dependencies with blame chain",
    )
    audit_deps_parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root for content discovery",
    )
    audit_deps_parser.add_argument(
        "--out",
        default="artifacts/asset_deps.json",
        help="Output dependency report path",
    )
    audit_deps_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any missing dependencies",
    )


def _handle_assets_reload(args: argparse.Namespace) -> int:
    repo_root = Path(str(getattr(args, "repo_root", ".") or ".")).resolve()
    set_content_roots([repo_root])
    try:
        from engine.fx_presets import collect_presets_and_errors
        from engine.tooling_runtime.pack_manifest import load_all_manifests, resolve_pack_order
        from engine.tooling_runtime.pack_registry import build_asset_registry

        manifests, manifest_errors = load_all_manifests()
        if manifest_errors:
            for manifest_error in manifest_errors:
                print(f"[Mesh][Assets] ERROR {manifest_error}")
            return 1

        order, order_errors = resolve_pack_order(manifests)
        if order_errors:
            for order_error in order_errors:
                print(f"[Mesh][Assets] ERROR {order_error}")
            return 1

        pack_roots = [m.root for m in order]
        preset_records, preset_errors = collect_presets_and_errors(pack_roots, order)
        if preset_errors:
            for preset_error in preset_errors:
                print(
                    f"[Mesh][Assets] ERROR {preset_error.pack_id}:{preset_error.preset_name} "
                    f"({preset_error.file_path}): {preset_error.message}"
                )
            return 1

        registry = build_asset_registry(order, include_unused=False)
        assets_count = len(registry.get("assets", [])) if isinstance(registry, dict) else 0

        print(
            "[Mesh][Assets] OK "
            f"(packs={len(order)} presets={len(preset_records)} assets={assets_count})"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Assets] ERROR reload failed: {exc}")
        return 1
    finally:
        reset_path_caches()


def _handle_assets_audit(args: argparse.Namespace) -> int:
    repo_root_raw = str(getattr(args, "repo_root", ".") or ".").strip() or "."
    repo_root = Path(repo_root_raw).resolve()
    out_raw = str(getattr(args, "out", "") or "").strip() or "artifacts/asset_audit.json"
    out_path = Path(out_raw)
    if not out_path.is_absolute():
        out_path = repo_root / out_path
    pack_id = str(getattr(args, "pack", "") or "").strip() or None
    strict = bool(getattr(args, "strict", False))
    with_orphans = bool(getattr(args, "with_orphans", False))
    with_duplicates = bool(getattr(args, "with_duplicates", False))
    with_ownership = _parse_bool(getattr(args, "with_ownership", True), default=True)
    warn_duplicates = _parse_bool(getattr(args, "warn_duplicates", True), default=True)
    fail_missing = _parse_bool(getattr(args, "fail_missing", True), default=True)
    fail_orphans = _parse_bool(getattr(args, "fail_orphans", False), default=False)
    fail_duplicates = _parse_bool(getattr(args, "fail_duplicates", False), default=False)

    from engine.tooling.assets_audit import run_asset_audit

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=out_path,
        pack_id=pack_id,
        strict=strict,
        with_orphans=with_orphans,
        with_duplicates=with_duplicates,
        with_ownership=bool(with_ownership),
        warn_duplicates=bool(warn_duplicates),
        fail_missing=bool(fail_missing),
        fail_orphans=bool(fail_orphans),
        fail_duplicates=bool(fail_duplicates),
        write_report=True,
    )
    files_scanned = report.get("files_scanned", 0)
    error_count = report.get("summary", {}).get("error_count", 0)
    warning_count = report.get("summary", {}).get("warning_count", 0)
    orphan_count = report.get("summary", {}).get("orphan_count", 0)
    dup_groups = report.get("summary", {}).get("duplicate_groups", 0)
    if report.get("summary", {}).get("ok") is True:
        print(
            "[Mesh][Assets] OK "
            f"(files={files_scanned}, errors={error_count}, warnings={warning_count}, "
            f"orphans={orphan_count}, dup_groups={dup_groups})"
        )
    elif error_count == 0 and warning_count > 0:
        print(
            "[Mesh][Assets] WARN "
            f"(files={files_scanned}, errors={error_count}, warnings={warning_count}, "
            f"orphans={orphan_count}, dup_groups={dup_groups}) "
            f"wrote {out_path.as_posix()}"
        )
    else:
        print(
            "[Mesh][Assets] ERROR "
            f"(files={files_scanned}, errors={error_count}, warnings={warning_count}, "
            f"orphans={orphan_count}, dup_groups={dup_groups}) "
            f"wrote {out_path.as_posix()}"
        )
    return exit_code


def _handle_assets_fix_missing(args: argparse.Namespace) -> int:
    repo_root_raw = str(getattr(args, "repo_root", ".") or ".").strip() or "."
    repo_root = Path(repo_root_raw).resolve()
    audit_raw = str(getattr(args, "audit", "") or "").strip() or "artifacts/asset_audit.json"
    audit_path = Path(audit_raw)
    if not audit_path.is_absolute():
        audit_path = repo_root / audit_path
    out_raw = str(getattr(args, "out", "") or "").strip() or "artifacts/asset_audit_fix.json"
    out_path = Path(out_raw)
    if not out_path.is_absolute():
        out_path = repo_root / out_path
    mode = str(getattr(args, "mode", "stub") or "stub").strip().lower() or "stub"
    placeholder_raw = str(getattr(args, "placeholder", "") or "").strip() or "assets/placeholder.png"
    placeholder_path = Path(placeholder_raw)
    if not placeholder_path.is_absolute():
        placeholder_path = repo_root / placeholder_path

    from engine.tooling.assets_fix import fix_missing_assets_from_audit

    report = fix_missing_assets_from_audit(
        repo_root=repo_root,
        audit_path=audit_path,
        out_path=out_path,
        mode=mode,
        placeholder_path=placeholder_path,
    )

    created = len(report.get("created_files", []))
    skipped_existing = len(report.get("skipped_existing", []))
    skipped_unsupported = len(report.get("skipped_unsupported", []))
    failures = len(report.get("failures", []))
    rewritten = len(report.get("rewritten_files", [])) if mode == "rewrite" else 0

    if failures:
        print(
            "[Mesh][Assets] ERROR "
            f"(mode={mode}, created={created}, rewritten={rewritten}, "
            f"skipped_existing={skipped_existing}, skipped_unsupported={skipped_unsupported}, "
            f"failures={failures}) wrote {out_path.as_posix()}"
        )
        return 2
    print(
        "[Mesh][Assets] OK "
        f"(mode={mode}, created={created}, rewritten={rewritten}, "
        f"skipped_existing={skipped_existing}, skipped_unsupported={skipped_unsupported}) "
        f"wrote {out_path.as_posix()}"
    )
    return 0


def _handle_assets_build_manifest(args: argparse.Namespace) -> int:
    """Build deterministic asset manifest with hashes."""
    repo_root_raw = str(getattr(args, "repo_root", ".") or ".").strip() or "."
    repo_root = Path(repo_root_raw).resolve()
    out_raw = str(getattr(args, "out", "") or "").strip() or "artifacts/asset_manifest.json"
    out_path = Path(out_raw)
    if not out_path.is_absolute():
        out_path = repo_root / out_path

    from tooling.asset_manifest import build_manifest

    manifest = build_manifest(repo_root)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_path, manifest, indent=2, sort_keys=True, trailing_newline=True)

    asset_count = manifest.get("asset_count", 0)
    print(f"[Mesh][Assets] OK (manifest: {asset_count} assets) wrote {out_path.as_posix()}")
    return 0


def _handle_assets_audit_deps(args: argparse.Namespace) -> int:
    """Audit asset dependencies for missing references."""
    repo_root_raw = str(getattr(args, "repo_root", ".") or ".").strip() or "."
    repo_root = Path(repo_root_raw).resolve()
    out_raw = str(getattr(args, "out", "") or "").strip() or "artifacts/asset_deps.json"
    out_path = Path(out_raw)
    if not out_path.is_absolute():
        out_path = repo_root / out_path
    strict = bool(getattr(args, "strict", False))

    from tooling.asset_manifest import audit_dependencies, build_manifest

    manifest = build_manifest(repo_root)
    report = audit_dependencies(repo_root, manifest=manifest)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_path, report.to_dict(), indent=2, sort_keys=True, trailing_newline=True)

    ref_count = len(report.references)
    missing_count = len(report.missing)
    error_count = len(report.errors)

    if report.missing:
        print(f"[Mesh][Assets] FAILED ({ref_count} refs, {missing_count} missing, {error_count} errors)")
        for dep in report.missing[:5]:
            print(f"  - {dep.asset_id}")
            for ref in dep.references[:2]:
                print(f"      referenced by: {ref.source_file} ({ref.field_path})")
            if len(dep.references) > 2:
                print(f"      ... and {len(dep.references) - 2} more references")
        if len(report.missing) > 5:
            print(f"  ... and {len(report.missing) - 5} more missing")
        print(f"  wrote {out_path.as_posix()}")
        return 1 if strict else 0

    if report.errors:
        print(f"[Mesh][Assets] ERROR ({ref_count} refs, {error_count} errors)")
        for err in report.errors[:5]:
            print(f"  - {err}")
        print(f"  wrote {out_path.as_posix()}")
        return 1

    print(f"[Mesh][Assets] OK ({ref_count} refs, all dependencies resolved) wrote {out_path.as_posix()}")
    return 0


def _handle_index(args: argparse.Namespace) -> int:
    """Run the project indexer."""
    return project_index.main([])


def _handle_doctor_assets(args: argparse.Namespace) -> int:
    fix = bool(getattr(args, "fix", False))
    strict = bool(getattr(args, "strict", False))
    out_path = str(getattr(args, "out", "") or "").strip() or None
    explicit_json = bool(getattr(args, "json", False))
    json_mode = is_json_mode() or (len(sys.argv) > 1 and sys.argv[1] == "doctor-assets")
    raw_json = json_mode
    wrapper_json = explicit_json and not json_mode
    json_out = raw_json or wrapper_json
    packs_raw = list(getattr(args, "pack", None) or [])
    packs = [str(p).strip() for p in packs_raw if str(p).strip()]

    try:
        with suppress_stdout():
            repo_root = get_repo_root(start=Path.cwd(), strict=True)
            from engine.tooling.asset_doctor import doctor_assets

            payload = doctor_assets(repo_root=repo_root, fix=fix, strict=strict, packs=packs)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "ok": False,
            "errors": [
                {"code": "repo_root.invalid", "path": "", "message": _single_line_error(f"{type(exc).__name__}: {exc}")}
            ],
            "warnings": [],
            "fixes": [],
            "missing_prefab_assets": [],
            "missing_prefab_assets_warnings": [],
        }
        if out_path:
            with suppress_stdout():
                write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)
        if "cache" not in payload:
            payload["cache"] = {"hits": 0, "misses": 0, "entries": 0}
        if raw_json:
            text = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
            sys.stdout.write(text)
        elif wrapper_json:
            json_payload: dict[str, object] = {
                "cmd": "doctor_assets",
                "ok": False,
                "missing": [],
                "warnings": [],
                "cache": {"hits": 0, "misses": 0, "entries": 0},
            }
            if packs:
                json_payload["packs"] = packs
            sys.stdout.write(json.dumps(json_payload, separators=(",", ":")))
        else:
            sys.stdout.write(f"[Assets] doctor-assets failed: {payload['errors'][0]['message']}")
        return 2

    if out_path:
        with suppress_stdout():
            write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)

    missing = payload.get("missing_prefab_assets")
    missing = missing if isinstance(missing, list) else []
    warn_entries = payload.get("missing_prefab_assets_warnings")
    warn_entries = warn_entries if isinstance(warn_entries, list) else []
    if raw_json:
        text = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
        sys.stdout.write(text)
        if missing:
            return 2
        return 0 if payload.get("ok") is True else 1

    if wrapper_json:
        json_payload_out: dict[str, object] = {
            "cmd": "doctor_assets",
            "ok": payload.get("ok") is True,
            "missing": missing,
            "warnings": warn_entries,
        }
        cache_stats = payload.get("cache")
        if isinstance(cache_stats, dict):
            json_payload_out["cache"] = cache_stats
        else:
            json_payload_out["cache"] = {"hits": 0, "misses": 0, "entries": 0}
        if packs:
            json_payload_out["packs"] = packs
        sys.stdout.write(json.dumps(json_payload_out, separators=(",", ":")))
        if missing:
            return 2
        return 0 if payload.get("ok") is True else 1

    if warn_entries:
        for entry in warn_entries:
            if not isinstance(entry, dict):
                continue
            prefab_id = str(entry.get("prefab_id") or "")
            source = str(entry.get("source") or "unknown")
            field = str(entry.get("field") or "")
            path = str(entry.get("path") or "")
            warning = str(entry.get("warning") or "")
            warning_text = warning if warning else "invalid sprite sheet"
            field_text = f" field={field}" if field else ""
            print(
                f"[Assets][Warn] {warning_text}{field_text} prefab={prefab_id} source={source} path={path}"
            )

    if missing:
        for entry in missing:
            if not isinstance(entry, dict):
                continue
            prefab_id = str(entry.get("prefab_id") or "")
            source = str(entry.get("source") or "unknown")
            field = str(entry.get("field") or "")
            path = str(entry.get("path") or "")
            print(f"[Assets] missing {field} prefab={prefab_id} source={source} path={path}")
        print(f"[Assets] missing prefab asset refs: {len(missing)}")
        return 2

    print("[Assets] missing prefab asset refs: 0")
    return 0 if payload.get("ok") is True else 1


def _handle_schema_fix_ids(args: argparse.Namespace) -> int:
    argv2: list[str] = []
    if getattr(args, "dry_run", False):
        argv2.append("--dry-run")
    schema_fix_paths = getattr(args, "paths", None)
    if schema_fix_paths:
        argv2.append("--paths")
        argv2.extend(list(schema_fix_paths))
    return schema_fix_ids.main(argv2)


def _handle_polish(args: argparse.Namespace) -> int:
    """Run the polish command."""
    return polish.main(args.path, args.compact_scenes, args.export_graph, args.update_lock_audit)


def _handle_assets_import_sprites(args: argparse.Namespace) -> int:
    dry_run = bool(getattr(args, "dry_run", False))
    default_solid_raw = getattr(args, "default_solid", None)
    default_solid = _parse_bool(default_solid_raw, default=None)
    if default_solid is None:
        print("[Mesh][Sprite] ERROR: --default-solid must be true/false")
        return 1

    default_layer = str(getattr(args, "default_layer", "") or "entities").strip() or "entities"
    tags_raw = list(getattr(args, "tag", None) or [])
    tags: list[str] = []
    for raw in tags_raw:
        tag = str(raw or "").strip()
        if tag and tag not in tags:
            tags.append(tag)

    repo_root = None
    try:
        repo_root = get_repo_root(start=Path.cwd(), strict=False)
    except Exception:
        repo_root = None
    base_dir = repo_root or Path.cwd()
    sprites_dir_raw = str(getattr(args, "sprites_dir", "") or "assets/sprites").strip() or "assets/sprites"
    sprites_dir = base_dir / Path(sprites_dir_raw)
    if not sprites_dir.exists():
        print(f"[Mesh][Sprite] No sprites directory: {sprites_dir}")
        return 0

    allowed_exts = {".png", ".jpg", ".jpeg"}
    files = [
        p
        for p in sprites_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in allowed_exts
    ]
    files = sorted(files, key=lambda p: p.as_posix())
    if not files:
        print("[Mesh][Sprite] No sprites found.")
        return 0

    from engine.paths import resolve_path

    out_path_raw = str(getattr(args, "out", "") or "assets/prefabs.json").strip() or "assets/prefabs.json"
    prefabs_path = resolve_path(out_path_raw)
    try:
        existing = json.loads(prefabs_path.read_text(encoding="utf-8")) if prefabs_path.exists() else []
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Sprite] ERROR: failed to read '{prefabs_path}': {exc}")
        return 1

    if not isinstance(existing, list):
        print(f"[Mesh][Sprite] ERROR: '{prefabs_path}' must contain a JSON list of prefabs")
        return 1

    existing_ids: set[str] = set()
    existing_sprites: set[str] = set()
    for entry in existing:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("id") or "").strip()
        if pid:
            existing_ids.add(pid)
        entity_payload = entry.get("entity")
        if isinstance(entity_payload, dict):
            sprite_path = entity_payload.get("sprite")
            if isinstance(sprite_path, str) and sprite_path.strip():
                existing_sprites.add(sprite_path.replace("\\", "/"))

    new_entries: list[dict[str, object]] = []
    new_ids: set[str] = set()
    new_sprites: set[str] = set()

    for file_path in files:
        sprite_path = _normalize_path_for_json(file_path, repo_root=repo_root)
        sprite_key = sprite_path.replace("\\", "/")
        if sprite_key in existing_sprites or sprite_key in new_sprites:
            continue

        name_stem = file_path.stem
        clean_id = "".join(c for c in name_stem if c.isalnum() or c == "_").lower()
        if not clean_id:
            clean_id = "sprite"
        candidate = clean_id
        counter = 1
        while candidate in existing_ids or candidate in new_ids:
            candidate = f"{clean_id}_{counter}"
            counter += 1

        display_name = name_stem.replace("_", " ").title()
        entity: dict[str, object] = {
            "name": display_name,
            "sprite": sprite_path,
            "solid": bool(default_solid),
            "layer": default_layer,
            "behaviours": [],
        }
        wrapper: dict[str, object] = {
            "id": candidate,
            "display_name": display_name,
            "tags": list(tags),
            "metadata": {"tool": "import-sprites", "source": sprite_path},
            "entity": entity,
        }
        new_entries.append(wrapper)
        new_ids.add(candidate)
        new_sprites.add(sprite_key)

    if not new_entries:
        print("[Mesh][Sprite] No new sprites found.")
        return 0

    new_entries = sorted(new_entries, key=lambda e: str(e.get("id") or ""))
    if dry_run:
        text = dumps_json_deterministic(new_entries, indent=2, sort_keys=False, trailing_newline=True)
        sys.stdout.write(text)
        return 0

    updated = list(existing) + new_entries
    updated = sorted(updated, key=lambda e: str(e.get("id") or ""))

    write_json_atomic(prefabs_path, updated, indent=2, sort_keys=False, trailing_newline=True)
    print(f"[Mesh][Sprite] Added {len(new_entries)} prefab(s) to {prefabs_path}")
    return 0


def _upsert_sprite_prefab(
    out_path_raw: str,
    prefab_id: str,
    entity: dict[str, object],
    *,
    author: str,
) -> int:
    out_path = Path(out_path_raw)
    try:
        existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Sprite] ERROR: failed to read '{out_path_raw}': {exc}")
        return 1

    if not isinstance(existing, list):
        print(f"[Mesh][Sprite] ERROR: '{out_path_raw}' must contain a JSON list of prefabs")
        return 1

    updated = list(existing)
    target_index = None
    for idx, entry in enumerate(updated):
        if isinstance(entry, dict) and entry.get("id") == prefab_id:
            target_index = idx
            break

    if target_index is None:
        wrapper: dict[str, object] = {
            "id": prefab_id,
            "tags": [],
            "metadata": {"author": author},
            "display_name": prefab_id,
            "entity": entity,
        }
        updated.append(wrapper)
    else:
        wrapper = updated[target_index]
        if not isinstance(wrapper, dict):
            print(f"[Mesh][Sprite] ERROR: prefab '{prefab_id}' must be an object")
            return 1
        prev_entity = wrapper.get("entity")
        if not isinstance(prev_entity, dict):
            print(f"[Mesh][Sprite] ERROR: prefab '{prefab_id}' missing entity object")
            return 1
        if "sprite_sheet" not in prev_entity and "animations" not in prev_entity:
            print(f"[Mesh][Sprite] ERROR: prefab '{prefab_id}' exists but is not sprite-sheet based")
            return 1
        wrapper["entity"] = entity
        updated[target_index] = wrapper

    if existing == updated:
        return 0

    write_json_atomic(out_path, updated, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_sprite_import_sheet(args: argparse.Namespace) -> int:
    image_path_raw = str(getattr(args, "image_path", "") or "").strip()
    if not image_path_raw:
        print("[Mesh][CLI] Error: missing image_path")
        return 2

    out_path_raw = str(getattr(args, "out", "") or "").strip()
    if not out_path_raw:
        print("[Mesh][CLI] Error: missing --out")
        return 2

    prefab_id = str(getattr(args, "prefab_id", "") or "").strip()
    if not prefab_id:
        print("[Mesh][CLI] Error: missing --prefab-id")
        return 2

    frame_w = int(getattr(args, "frame_w"))
    frame_h = int(getattr(args, "frame_h"))
    if frame_w <= 0 or frame_h <= 0:
        print("[Mesh][Sprite] ERROR: --frame-w/--frame-h must be > 0")
        return 1

    margin = max(0, int(getattr(args, "margin", 0) or 0))
    spacing = max(0, int(getattr(args, "spacing", 0) or 0))

    from engine.paths import resolve_path

    image_path = resolve_path(image_path_raw)
    if not image_path.exists():
        print(f"[Mesh][Sprite] ERROR: image not found: {image_path_raw}")
        return 1

    try:
        from PIL import Image

        with Image.open(image_path) as img:
            sheet_w = int(img.width)
            sheet_h = int(img.height)
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Sprite] ERROR: failed to read image '{image_path_raw}': {exc}")
        return 1

    spec = SpriteSheetSliceSpec(
        sheet_width=sheet_w,
        sheet_height=sheet_h,
        frame_width=frame_w,
        frame_height=frame_h,
        margin=margin,
        spacing=spacing,
    )
    boxes = iter_sprite_sheet_frame_boxes(spec)
    frame_count = len(boxes)
    if frame_count <= 0:
        print("[Mesh][Sprite] ERROR: computed frame count is 0 (check dimensions/margin/spacing)")
        return 1

    anim_args = list(getattr(args, "anim", None) or [])
    if not anim_args:
        print("[Mesh][Sprite] ERROR: at least one --anim is required")
        return 1

    animations: dict[str, dict[str, object]] = {}
    for raw in anim_args:
        parsed = parse_anim_spec(raw)
        if parsed is None:
            print(f"[Mesh][Sprite] ERROR: invalid --anim spec: {raw!r} (expected name:start-end:fps)")
            return 1
        name, start, end, fps = parsed
        if fps <= 0:
            print(f"[Mesh][Sprite] ERROR: anim '{name}' fps must be > 0")
            return 1
        if start < 0 or end < 0 or end < start:
            print(f"[Mesh][Sprite] ERROR: anim '{name}' has invalid range {start}-{end}")
            return 1
        if end >= frame_count:
            print(
                f"[Mesh][Sprite] ERROR: anim '{name}' out of bounds: {start}-{end} (frame_count={frame_count})",
            )
            return 1
        animations[name] = {
            "frames": list(range(int(start), int(end) + 1)),
            "fps": float(fps),
            "loop": True,
        }

    repo_root = None
    try:
        repo_root = get_repo_root(start=Path.cwd(), strict=False)
    except Exception:
        repo_root = None

    sprite_path_for_json = _normalize_path_for_json(image_path_raw, repo_root=repo_root)

    entity: dict[str, object] = {}
    entity["sprite"] = sprite_path_for_json
    entity["sprite_sheet"] = {
        "path": sprite_path_for_json,
        "frame_width": int(frame_w),
        "frame_height": int(frame_h),
        "margin": int(margin),
        "spacing": int(spacing),
    }
    entity["animations"] = {k: animations[k] for k in sorted(animations)}

    anchor_raw = getattr(args, "anchor", None)
    if anchor_raw:
        try:
            x_str, y_str = str(anchor_raw).split(",", 1)
            entity["anchor"] = [float(x_str), float(y_str)]
        except Exception:
            print("[Mesh][Sprite] ERROR: --anchor must be formatted as x,y")
            return 1

    hitbox_raw = getattr(args, "hitbox", None)
    if hitbox_raw:
        try:
            x_str, y_str, w_str, h_str = str(hitbox_raw).split(",", 3)
            entity["hitbox"] = {
                "x": float(x_str),
                "y": float(y_str),
                "w": float(w_str),
                "h": float(h_str),
            }
        except Exception:
            print("[Mesh][Sprite] ERROR: --hitbox must be formatted as x,y,w,h")
            return 1

    return _upsert_sprite_prefab(
        out_path_raw,
        prefab_id,
        entity,
        author="sprite_import_sheet",
    )


def _handle_sprite_import_aseprite(args: argparse.Namespace) -> int:
    json_path_raw = str(getattr(args, "json_path", "") or "").strip()
    if not json_path_raw:
        print("[Mesh][CLI] Error: missing json_path")
        return 2

    out_path_raw = str(getattr(args, "out", "") or "").strip()
    if not out_path_raw:
        print("[Mesh][CLI] Error: missing --out")
        return 2

    prefab_id = str(getattr(args, "prefab_id", "") or "").strip()
    if not prefab_id:
        print("[Mesh][CLI] Error: missing --prefab-id")
        return 2

    from engine.paths import resolve_path

    json_path = resolve_path(json_path_raw)
    if not json_path.exists():
        print(f"[Mesh][Sprite] ERROR: JSON not found: {json_path_raw}")
        return 1

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Sprite] ERROR: failed to read JSON '{json_path_raw}': {exc}")
        return 1

    frames_raw = data.get("frames")
    if isinstance(frames_raw, dict):
        frames_list = list(frames_raw.values())
        frame_keys = list(frames_raw.keys())
    elif isinstance(frames_raw, list):
        frames_list = frames_raw
        frame_keys = [str(i) for i in range(len(frames_list))]
    else:
        print("[Mesh][Sprite] ERROR: Aseprite JSON must use array or hash frame format")
        return 1

    if not frames_list:
        print("[Mesh][Sprite] ERROR: Aseprite JSON contains no frames")
        return 1

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    meta_image = meta.get("image") if isinstance(meta, dict) else None
    image_path_raw = str(getattr(args, "image", "") or meta_image or "").strip()
    if not image_path_raw:
        print("[Mesh][Sprite] ERROR: missing spritesheet image (use --image or meta.image)")
        return 1

    image_path = Path(image_path_raw)
    if not image_path.is_absolute():
        image_path = json_path.parent / image_path
    if not image_path.exists():
        image_path = resolve_path(image_path_raw)
    if not image_path.exists():
        print(f"[Mesh][Sprite] ERROR: image not found: {image_path_raw}")
        return 1

    sheet_w = None
    sheet_h = None
    if isinstance(meta, dict):
        size = meta.get("size") if isinstance(meta.get("size"), dict) else None
        if isinstance(size, dict):
            try:
                sheet_w = int(size.get("w", 0) or 0)
                sheet_h = int(size.get("h", 0) or 0)
            except (TypeError, ValueError):
                sheet_w = None
                sheet_h = None

    if sheet_w is None or sheet_h is None:
        try:
            from PIL import Image

            with Image.open(image_path) as img:
                sheet_w = int(img.width)
                sheet_h = int(img.height)
        except Exception as exc:  # noqa: BLE001
            print(f"[Mesh][Sprite] ERROR: failed to read image '{image_path}': {exc}")
            return 1

    frames: list[dict[str, Any]] = []
    durations: list[int] = []
    for idx, frame_entry in enumerate(frames_list):
        if not isinstance(frame_entry, dict):
            print(f"[Mesh][Sprite] ERROR: frame[{frame_keys[idx]}] must be an object")
            return 1
        frame_rect = frame_entry.get("frame")
        if not isinstance(frame_rect, dict):
            print(f"[Mesh][Sprite] ERROR: frame[{frame_keys[idx]}] missing frame rectangle")
            return 1
        try:
            x = int(frame_rect.get("x", 0) or 0)
            y = int(frame_rect.get("y", 0) or 0)
            w = int(frame_rect.get("w", 0) or 0)
            h = int(frame_rect.get("h", 0) or 0)
        except (TypeError, ValueError):
            print(f"[Mesh][Sprite] ERROR: frame[{frame_keys[idx]}] has invalid rectangle")
            return 1
        if w <= 0 or h <= 0:
            print(f"[Mesh][Sprite] ERROR: frame[{frame_keys[idx]}] has invalid size")
            return 1
        if frame_entry.get("trimmed") is True:
            print("[Mesh][Sprite] ERROR: trimmed frames are not supported (export with Trim disabled)")
            return 1
        sprite_source = frame_entry.get("spriteSourceSize")
        if isinstance(sprite_source, dict):
            if int(sprite_source.get("x", 0) or 0) != 0 or int(sprite_source.get("y", 0) or 0) != 0:
                print("[Mesh][Sprite] ERROR: trimmed/offset frames are not supported")
                return 1
        frames.append({"x": x, "y": y, "w": w, "h": h})
        dur = frame_entry.get("duration", 0)
        try:
            durations.append(int(dur or 0))
        except (TypeError, ValueError):
            durations.append(100)

    frame_w = frames[0]["w"]
    frame_h = frames[0]["h"]
    if any(f["w"] != frame_w or f["h"] != frame_h for f in frames):
        print("[Mesh][Sprite] ERROR: frame sizes are not uniform (export without trimming)")
        return 1

    xs = sorted({f["x"] for f in frames})
    ys = sorted({f["y"] for f in frames})
    if not xs or not ys:
        print("[Mesh][Sprite] ERROR: failed to derive grid positions from frames")
        return 1

    if sheet_w is None or sheet_h is None:
        print("[Mesh][Sprite] ERROR: failed to resolve spritesheet dimensions")
        return 1
    sheet_w = int(sheet_w)
    sheet_h = int(sheet_h)
    margin_left = int(min(xs))
    margin_top = int(min(ys))
    max_x = int(max(xs))
    max_y = int(max(ys))
    frame_w = int(frame_w)
    frame_h = int(frame_h)
    margin_right = sheet_w - max_x - frame_w
    margin_bottom = sheet_h - max_y - frame_h
    if margin_left < 0 or margin_top < 0 or margin_right < 0 or margin_bottom < 0:
        print("[Mesh][Sprite] ERROR: frame rectangles exceed sheet dimensions")
        return 1
    if margin_left != margin_top or margin_left != margin_right or margin_left != margin_bottom:
        print("[Mesh][Sprite] ERROR: non-uniform sheet margins are not supported")
        return 1

    spacing_x = None
    for a, b in zip(xs, xs[1:]):
        delta = int(b) - int(a) - int(frame_w)
        if delta < 0:
            print("[Mesh][Sprite] ERROR: frames overlap horizontally (invalid grid)")
            return 1
        if spacing_x is None:
            spacing_x = delta
        elif spacing_x != delta:
            print("[Mesh][Sprite] ERROR: inconsistent horizontal spacing between frames")
            return 1
    spacing_y = None
    for a, b in zip(ys, ys[1:]):
        delta = int(b) - int(a) - int(frame_h)
        if delta < 0:
            print("[Mesh][Sprite] ERROR: frames overlap vertically (invalid grid)")
            return 1
        if spacing_y is None:
            spacing_y = delta
        elif spacing_y != delta:
            print("[Mesh][Sprite] ERROR: inconsistent vertical spacing between frames")
            return 1
    spacing_x = 0 if spacing_x is None else spacing_x
    spacing_y = 0 if spacing_y is None else spacing_y
    if spacing_x != spacing_y:
        print("[Mesh][Sprite] ERROR: non-uniform spacing is not supported")
        return 1

    columns = len(xs)
    rows = len(ys)
    if columns <= 0 or rows <= 0:
        print("[Mesh][Sprite] ERROR: computed grid is empty")
        return 1

    grid_index_by_frame: list[int] = []
    for idx, frame in enumerate(frames):
        x = int(frame["x"])
        y = int(frame["y"])
        if (x - margin_left) % (frame_w + spacing_x) != 0:
            print(f"[Mesh][Sprite] ERROR: frame[{frame_keys[idx]}] does not align to grid (x)")
            return 1
        if (y - margin_top) % (frame_h + spacing_y) != 0:
            print(f"[Mesh][Sprite] ERROR: frame[{frame_keys[idx]}] does not align to grid (y)")
            return 1
        col = xs.index(x)
        row_from_top = ys.index(y)
        row_from_bottom = (rows - 1) - row_from_top
        grid_index_by_frame.append(int(row_from_bottom * columns + col))
    if len(set(grid_index_by_frame)) != len(grid_index_by_frame):
        print("[Mesh][Sprite] ERROR: duplicate frame positions detected in grid")
        return 1

    tags = meta.get("frameTags") if isinstance(meta, dict) else None
    if not isinstance(tags, list) or not tags:
        print("[Mesh][Sprite] ERROR: no frameTags found (define tags in Aseprite)")
        return 1

    animations: dict[str, dict[str, object]] = {}
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        name = str(tag.get("name") or "").strip()
        if not name:
            continue
        try:
            start = int(tag.get("from", 0) or 0)
            end = int(tag.get("to", 0) or 0)
        except (TypeError, ValueError):
            print(f"[Mesh][Sprite] ERROR: tag '{name}' has invalid range")
            return 1
        if start < 0 or end < start or end >= len(frames):
            print(f"[Mesh][Sprite] ERROR: tag '{name}' out of bounds: {start}-{end}")
            return 1
        direction = str(tag.get("direction") or "forward").strip().lower()
        base_seq = list(range(start, end + 1))
        if direction == "reverse":
            seq = list(reversed(base_seq))
        elif direction == "pingpong":
            if len(base_seq) <= 1:
                seq = base_seq
            else:
                seq = base_seq + list(reversed(base_seq[1:-1]))
        elif direction == "forward":
            seq = base_seq
        else:
            print(f"[Mesh][Sprite] ERROR: tag '{name}' has unsupported direction '{direction}'")
            return 1

        mapped = [grid_index_by_frame[i] for i in seq]
        if not mapped:
            continue

        dur_values = [durations[i] for i in base_seq if i < len(durations)]
        avg_ms = sum(dur_values) / max(1, len(dur_values))
        if avg_ms <= 0:
            print(f"[Mesh][Sprite] ERROR: tag '{name}' has invalid frame durations")
            return 1
        fps = float(1000.0 / avg_ms)

        animations[name] = {
            "frames": mapped,
            "fps": fps,
            "loop": True,
        }

    if not animations:
        print("[Mesh][Sprite] ERROR: no valid animations created from frameTags")
        return 1

    repo_root = None
    try:
        repo_root = get_repo_root(start=Path.cwd(), strict=False)
    except Exception:
        repo_root = None

    sprite_path_for_json = _normalize_path_for_json(image_path, repo_root=repo_root)

    entity: dict[str, object] = {}
    entity["sprite"] = sprite_path_for_json
    entity["sprite_sheet"] = {
        "path": sprite_path_for_json,
        "frame_width": int(frame_w),
        "frame_height": int(frame_h),
        "margin": int(margin_left),
        "spacing": int(spacing_x),
        "columns": int(columns),
        "rows": int(rows),
    }
    entity["animations"] = {k: animations[k] for k in sorted(animations)}

    anchor_raw = getattr(args, "anchor", None)
    if anchor_raw:
        try:
            x_str, y_str = str(anchor_raw).split(",", 1)
            entity["anchor"] = [float(x_str), float(y_str)]
        except Exception:
            print("[Mesh][Sprite] ERROR: --anchor must be formatted as x,y")
            return 1

    hitbox_raw = getattr(args, "hitbox", None)
    if hitbox_raw:
        try:
            x_str, y_str, w_str, h_str = str(hitbox_raw).split(",", 3)
            entity["hitbox"] = {
                "x": float(x_str),
                "y": float(y_str),
                "w": float(w_str),
                "h": float(h_str),
            }
        except Exception:
            print("[Mesh][Sprite] ERROR: --hitbox must be formatted as x,y,w,h")
            return 1

    return _upsert_sprite_prefab(
        out_path_raw,
        prefab_id,
        entity,
        author="sprite_import_aseprite",
    )
