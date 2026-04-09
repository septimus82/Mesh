"""Release utilities for Mesh CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, cast

from engine.persistence_io import (
    dumps_json_deterministic,
    write_json_atomic,
    write_text_atomic,
)
from engine.provenance import (
    get_provenance,
    provenance_to_dict,
)
from mesh_cli.release_check_pipeline import (
    _normalize_outputs,
    _resolve_path,
    _run_assets_audit,
    _run_debug_bundle,
    _run_export_build,
    _run_step,
    _run_verify_all,
    _step_record,
    _write_report,
    _write_summary,
    build_release_check_report,
)
from mesh_cli.release_notes import (
    format_release_notes_text,
    generate_release_notes,
    release_notes_to_dict,
)
from mesh_cli.version_bump import BumpKind, bump_semver, bump_version_file
from mesh_cli.version_info import get_tool_version
from . import release_promote_packaging as _release_promote_packaging
from . import release_promote_reporting as _release_promote_reporting
from . import release_rc_helpers as _release_rc_helpers
from . import release_rc_reporting as _release_rc_reporting
from . import release_reporting as _release_reporting
from . import release_ship_reporting as _release_ship_reporting

_format_promote_report_text = _release_promote_reporting._format_promote_report_text
_promote_report_paths = _release_promote_reporting._promote_report_paths
_rc_report_paths = _release_reporting._rc_report_paths
_rc_step = _release_reporting._rc_step
_ship_report_paths = _release_reporting._ship_report_paths
_summarize_verify_report = _release_promote_reporting._summarize_verify_report
_write_promote_reports = _release_promote_reporting._write_promote_reports
_write_rc_reports = _release_reporting._write_rc_reports
_write_ship_reports = _release_reporting._write_ship_reports
_read_manifest_from_zip = _release_promote_packaging._read_manifest_from_zip
_determine_version_from_rc_manifest = _release_promote_packaging._determine_version_from_rc_manifest
_extract_zip_to_work_dir = _release_promote_packaging._extract_zip_to_work_dir
_inspect_rc_bundle_notes_manifest = _release_promote_packaging._inspect_rc_bundle_notes_manifest
_prepare_packaging_work_dir = _release_promote_packaging._prepare_packaging_work_dir
_write_embedded_promote_reports = _release_promote_packaging._write_embedded_promote_reports
_rebuild_promoted_zip = _release_promote_packaging._rebuild_promoted_zip
_rebuild_promoted_zip_with_report = _release_promote_packaging._rebuild_promoted_zip_with_report
_build_promote_report = _release_promote_reporting._build_promote_report
_build_ship_report = _release_ship_reporting._build_ship_report
_set_promote_version = _release_promote_reporting._set_promote_version
_set_promote_verify_summary = _release_promote_reporting._set_promote_verify_summary
_set_ship_child_report_projection = _release_ship_reporting._set_ship_child_report_projection
_set_ship_verify_summary = _release_ship_reporting._set_ship_verify_summary
_git_run = _release_rc_helpers._git_run
_git_available = _release_rc_helpers._git_available
_git_tag_exists = _release_rc_helpers._git_tag_exists
_default_tag_message = _release_rc_helpers._default_tag_message
_create_local_tag = _release_rc_helpers._create_local_tag
_build_rc_report = _release_rc_reporting._build_rc_report
_set_rc_version_bump = _release_rc_reporting._set_rc_version_bump
_set_rc_version_bump_rolled_back = _release_rc_reporting._set_rc_version_bump_rolled_back
_update_rc_bundle_report = _release_rc_reporting._update_rc_bundle_report

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__ + "._swallow").debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def register(subparsers: argparse._SubParsersAction) -> None:
    release_parser = subparsers.add_parser(
        "release",
        help="Release utilities",
        description="Deterministic release checks and artifacts",
    )
    release_subparsers = release_parser.add_subparsers(dest="release_command", help="Release subcommand")

    check_parser = release_subparsers.add_parser(
        "check",
        help="Run the release check pipeline",
        description="Run verify-all, asset audit, export build, and debug bundle export",
    )
    check_parser.add_argument("--repo-root", default=".", help="Repository root")
    check_parser.add_argument(
        "--artifacts",
        default="artifacts/release",
        help="Artifacts directory (relative to repo root if not absolute)",
    )
    check_parser.add_argument("--report", help="Optional JSON report path")
    check_parser.add_argument("--summary", help="Optional summary text path")

    notes_parser = release_subparsers.add_parser(
        "notes",
        help="Generate release notes from git history",
        description="Generate deterministic or normal release notes from commit subjects",
    )
    notes_parser.add_argument("--since", help="Optional start git ref (tag/commit)")
    notes_parser.add_argument("--until", help="Optional end git ref (default: HEAD)")
    notes_parser.add_argument("--out", help="Optional output path (file or directory)")
    notes_parser.add_argument(
        "--json",
        action="store_true",
        dest="notes_json",
        help="Emit JSON instead of text",
    )
    notes_parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Generate deterministic notes (no volatile timestamps)",
    )

    tag_parser = release_subparsers.add_parser(
        "tag",
        help="Create a local annotated git tag",
        description="Create a local annotated release tag without pushing",
    )
    tag_name_group = tag_parser.add_mutually_exclusive_group(required=True)
    tag_name_group.add_argument("--name", help="Tag name (e.g., v0.4.0)")
    tag_name_group.add_argument(
        "--auto",
        action="store_true",
        help="Use v<tool_version> from canonical version source",
    )
    tag_parser.add_argument("--message", help="Optional tag message")
    tag_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without creating the tag",
    )

    rc_parser = release_subparsers.add_parser(
        "rc",
        help="Run release-candidate pipeline",
        description=(
            "Generate deterministic release notes, optionally create a local tag, "
            "build a release bundle, strictly verify it, and emit unified RC reports."
        ),
    )
    rc_parser.add_argument("--out", required=True, help="Output RC ZIP path")
    rc_parser.add_argument("--seed", type=int, default=123, help="Deterministic seed (default: 123)")
    version_group = rc_parser.add_mutually_exclusive_group()
    version_group.add_argument("--version", dest="rc_version", help="RC version override (default: tool version)")
    version_group.add_argument(
        "--bump",
        dest="rc_bump",
        choices=["patch", "minor", "major"],
        help="Bump semantic version before RC (mutually exclusive with --version)",
    )
    rc_parser.add_argument("--since", help="Release notes start ref (optional)")
    rc_parser.add_argument(
        "--no-write-version",
        action="store_true",
        help="Preview bump value without writing version file",
    )
    rc_parser.add_argument(
        "--no-rollback",
        action="store_true",
        help="Do not restore version file if RC fails after a write bump",
    )
    rc_parser.add_argument("--quiet", action="store_true", help="Suppress non-essential stdout")
    rc_parser.add_argument("--json", action="store_true", dest="rc_json", help="Print RC report JSON to stdout")
    rc_parser.add_argument("--dry-run", action="store_true", help="Plan-only mode; do not tag or build bundle")

    promote_parser = release_subparsers.add_parser(
        "promote",
        help="Promote a verified RC bundle to final release",
        description=(
            "Strictly verify an RC ZIP, optionally tag the version, rebuild a deterministic "
            "final ZIP with embedded promotion reports, and strictly verify the result."
        ),
    )
    promote_parser.add_argument("--rc", required=True, help="Input RC ZIP path")
    promote_parser.add_argument("--out", required=True, help="Output final release ZIP path")
    promote_parser.add_argument("--version", dest="promote_version", help="Target release version override")
    promote_parser.add_argument("--tag", action="store_true", help="Create local annotated tag v<version>")
    promote_parser.add_argument("--notes-since", help="Optional notes start ref used for tag message generation")
    promote_parser.add_argument("--quiet", action="store_true", help="Suppress non-essential stdout")
    promote_parser.add_argument(
        "--json",
        action="store_true",
        dest="promote_json",
        help="Print promote report JSON to stdout",
    )
    promote_parser.add_argument("--dry-run", action="store_true", help="Plan-only mode; do not tag or build ZIP")

    ship_parser = release_subparsers.add_parser(
        "ship",
        help="Run one-command release pipeline (RC -> promote)",
        description=(
            "Deterministically run RC build and promotion, verify both artifacts, and emit "
            "a unified ship report."
        ),
    )
    ship_parser.add_argument("--out-dir", required=True, help="Output directory for release ship artifacts")
    ship_parser.add_argument("--seed", type=int, default=123, help="Deterministic seed (default: 123)")
    ship_parser.add_argument(
        "--bump",
        choices=["patch", "minor", "major"],
        dest="ship_bump",
        help="Optional semantic version bump applied during RC",
    )
    ship_parser.add_argument("--tag", action="store_true", help="Create local annotated final tag v<version>")
    ship_parser.add_argument("--since", help="Release notes start ref (optional)")
    ship_parser.add_argument("--quiet", action="store_true", help="Suppress non-essential stdout")
    ship_parser.add_argument("--json", action="store_true", dest="ship_json", help="Print ship report JSON to stdout")
    ship_parser.add_argument("--dry-run", action="store_true", help="Plan-only mode; do not build artifacts")

    # Release bundle (packaging)
    from . import release_bundle
    release_bundle.register_subcommand(release_subparsers)


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "release_command", None)
    if command == "check":
        return _handle_check(args)
    if command == "notes":
        return _handle_notes(args)
    if command == "tag":
        return _handle_tag(args)
    if command == "rc":
        return _handle_rc(args)
    if command == "promote":
        return _handle_promote(args)
    if command == "ship":
        return _handle_ship(args)
    if command == "bundle":
        from . import release_bundle
        return release_bundle.handle(args)
    print("[Mesh][Release] Error: missing release subcommand")
    return 2


def _resolve_notes_output_path(raw_out: str | None, *, json_mode: bool) -> Path | None:
    raw = str(raw_out or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.exists() and candidate.is_dir():
        return candidate / ("release_notes.json" if json_mode else "release_notes.txt")
    if raw.endswith(("/", "\\")):
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate / ("release_notes.json" if json_mode else "release_notes.txt")
    if not candidate.suffix:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate / ("release_notes.json" if json_mode else "release_notes.txt")
    return candidate


def _handle_notes(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "notes_json", False))
    deterministic = bool(getattr(args, "deterministic", False))
    since = getattr(args, "since", None)
    until = getattr(args, "until", None)
    out_path = _resolve_notes_output_path(getattr(args, "out", None), json_mode=json_mode)

    notes = generate_release_notes(deterministic=deterministic, since=since, until=until)
    payload = release_notes_to_dict(notes)
    text = format_release_notes_text(notes)

    if out_path is None:
        if json_mode:
            sys.stdout.write(dumps_json_deterministic(payload))
            sys.stdout.write("\n")
        else:
            sys.stdout.write(text)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if json_mode:
        write_json_atomic(out_path, payload, indent=2, sort_keys=True, trailing_newline=True)
    else:
        write_text_atomic(out_path, text, encoding="utf-8")
    print(f"[Mesh][Release] Notes written: {out_path.as_posix()}")
    return 0


_RC_SCHEMA_VERSION = 1
_RC_DETERMINISTIC_TIMESTAMP = "1980-01-01T00:00:00Z"
_PROMOTE_SCHEMA_VERSION = 1
_PROMOTE_DETERMINISTIC_TIMESTAMP = "1980-01-01T00:00:00Z"
_PROMOTE_EMBED_JSON = _release_promote_packaging.PROMOTE_EMBED_JSON
_PROMOTE_EMBED_TXT = _release_promote_packaging.PROMOTE_EMBED_TXT
_SHIP_SCHEMA_VERSION = 1


def _handle_tag(args: argparse.Namespace) -> int:
    if not _git_available():
        print("[Mesh][Release] ERROR: git is unavailable; cannot create local tag")
        return 2

    requested_name = str(getattr(args, "name", "") or "").strip()
    if bool(getattr(args, "auto", False)):
        requested_name = f"v{get_tool_version()}"
    tag_name = requested_name.strip()
    if not tag_name:
        print("[Mesh][Release] ERROR: tag name is required (--name or --auto)")
        return 2

    message = str(getattr(args, "message", "") or "").strip()
    if not message:
        message = _default_tag_message(tag_name.removeprefix("v"))

    exists = _git_tag_exists(tag_name)
    if exists is None:
        print("[Mesh][Release] ERROR: git is unavailable; cannot create local tag")
        return 2
    if exists:
        print(f"[Mesh][Release] ERROR: tag already exists: {tag_name}")
        return 1

    dry_run = bool(getattr(args, "dry_run", False))
    command = ["git", "tag", "-a", tag_name, "-m", message]
    if dry_run:
        print(f"[Mesh][Release] Dry-run: {' '.join(command)}")
        return 0

    status, reason = _create_local_tag(tag_name=tag_name, message=message)
    if status == "created":
        print(f"[Mesh][Release] Created local tag: {tag_name}")
        return 0
    if status == "existing":
        print(f"[Mesh][Release] ERROR: {reason}")
        return 1
    if status == "skipped":
        print("[Mesh][Release] ERROR: git is unavailable; cannot create local tag")
        return 2
    print(f"[Mesh][Release] ERROR: failed to create tag '{tag_name}': {reason}")
    return 1


def _handle_rc(args: argparse.Namespace) -> int:
    from mesh_cli.bundle_verify import (
        DEFAULT_EXCLUDE_RULES,
        VerifyOptions,
        verify_zip,
    )

    from . import release_bundle

    zip_path = Path(str(getattr(args, "out", "") or "").strip()).resolve()
    seed = int(getattr(args, "seed", 123))
    requested_version = str(getattr(args, "rc_version", "") or "").strip() or None
    raw_bump_kind = str(getattr(args, "rc_bump", "") or "").strip() or None
    bump_kind = cast(BumpKind, raw_bump_kind) if raw_bump_kind is not None else None
    since = str(getattr(args, "since", "") or "").strip() or None
    quiet = bool(getattr(args, "quiet", False))
    json_stdout = bool(getattr(args, "rc_json", False))
    dry_run = bool(getattr(args, "dry_run", False))
    do_tag = bool(getattr(args, "tag", True))
    no_write_version = bool(getattr(args, "no_write_version", False))
    no_rollback = bool(getattr(args, "no_rollback", False))
    campaign = str(getattr(args, "campaign", release_bundle.DEFAULT_CAMPAIGN) or release_bundle.DEFAULT_CAMPAIGN)

    original_version = get_tool_version()
    version = requested_version or original_version
    bump_payload: dict[str, Any] | None = None
    version_snapshot_bytes: bytes | None = None
    version_file_path: Path | None = None
    version_written = False
    rollback_applied = False

    if bump_kind:
        try:
            bumped = bump_semver(original_version, bump_kind)  # validates semantic format too
        except ValueError as exc:
            print(f"[Mesh][Release-RC] ERROR: {exc}")
            return 1
        version = bumped
        if not dry_run and not no_write_version:
            from mesh_cli.version_info import get_version_file_path

            version_file_path = get_version_file_path()
            try:
                version_snapshot_bytes = version_file_path.read_bytes()
            except OSError as exc:
                print(f"[Mesh][Release-RC] ERROR: cannot snapshot version file: {exc}")
                return 1
            try:
                bump_payload = bump_version_file(kind=bump_kind, dry_run=False)
            except ValueError as exc:
                print(f"[Mesh][Release-RC] ERROR: {exc}")
                return 1
            version_written = True
            version = str(bump_payload["new"])
        else:
            bump_payload = {"old": original_version, "new": bumped, "file": "engine/version.py"}

    tag_name = f"v{version}"

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    rc_work_dir = zip_path.parent / f"_rc_work_{zip_path.stem}"
    _prepare_packaging_work_dir(rc_work_dir)

    report = _build_rc_report(
        schema_version=_RC_SCHEMA_VERSION,
        version=version,
        seed=seed,
        campaign=campaign,
        dry_run=dry_run,
        zip_path=zip_path,
        bump_kind=bump_kind,
        since=since,
        quiet=quiet,
        json_stdout=json_stdout,
        do_tag=do_tag,
        no_write_version=no_write_version,
        no_rollback=no_rollback,
        provenance=provenance_to_dict(get_provenance(deterministic=True)),
        tag_name=tag_name,
    )

    if bump_payload is not None:
        _set_rc_version_bump(
            report,
            bump_kind=bump_kind,
            old_version=str(bump_payload["old"]),
            new_version=str(bump_payload["new"]),
            file_path=str(bump_payload["file"]),
            wrote=bool(version_written),
            no_write_version=no_write_version,
        )
    elif bump_kind:
        _set_rc_version_bump(
            report,
            bump_kind=bump_kind,
            old_version=original_version,
            new_version=version,
            file_path="engine/version.py",
            wrote=False,
            no_write_version=no_write_version,
        )

    def _rollback_if_needed() -> None:
        nonlocal rollback_applied
        if not version_written:
            return
        if no_rollback:
            return
        if version_file_path is None or version_snapshot_bytes is None:
            return
        try:
            version_file_path.write_bytes(version_snapshot_bytes)
            rollback_applied = True
            _set_rc_version_bump_rolled_back(report, True)
        except OSError as exc:
            report["steps"].append(
                _rc_step(
                    "rollback-version",
                    ok=False,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )

    def _emit_and_return(exit_code: int) -> int:
        _write_rc_reports(zip_path, report)
        if json_stdout:
            sys.stdout.write(dumps_json_deterministic(report))
            sys.stdout.write("\n")
        return exit_code

    def _fail_with_step(step: dict[str, Any]) -> int:
        report["steps"].append(step)
        _rollback_if_needed()
        return _emit_and_return(1)

    notes_payload: dict[str, Any] | None = None
    notes_text: str | None = None

    # 1) Determine version
    report["steps"].append(
        _rc_step(
            "determine-version",
            ok=True,
            artifacts={"version": version, "source": "bump" if bump_kind else "explicit/default"},
        )
    )

    if bump_kind:
        report["steps"].append(
            _rc_step(
                "bump-version",
                ok=True,
                skipped=bool(dry_run or no_write_version),
                reason="dry-run" if dry_run else ("no-write-version" if no_write_version else None),
                artifacts={
                    "kind": bump_kind,
                    "old": original_version,
                    "new": version,
                    "wrote": bool(version_written),
                },
            )
        )

    # 2) Generate deterministic notes
    try:
        notes = generate_release_notes(deterministic=True, since=since, until="HEAD")
        notes_payload = release_notes_to_dict(notes)
        notes_text = format_release_notes_text(notes)
        notes_json_path = rc_work_dir / "release_notes.json"
        notes_txt_path = rc_work_dir / "release_notes.txt"
        write_json_atomic(notes_json_path, notes_payload, indent=2, sort_keys=True, trailing_newline=True)
        write_text_atomic(notes_txt_path, notes_text, encoding="utf-8")
        report["steps"].append(
            _rc_step(
                "generate-release-notes",
                ok=True,
                artifacts={"json": notes_json_path.name, "txt": notes_txt_path.name},
            )
        )
    except Exception as exc:  # noqa: BLE001  # REASON: release-rc notes generation step isolation
        report["steps"].append(
            _rc_step(
                "generate-release-notes",
                ok=False,
                reason=f"{type(exc).__name__}: {exc}",
            )
        )
        report["tag"]["status"] = "skipped"
        report["tag"]["reason"] = "pipeline failed before tag step"
        _rollback_if_needed()
        return _emit_and_return(1)

    # 3) Optional local tag
    if not do_tag:
        report["tag"]["status"] = "skipped"
        report["tag"]["reason"] = "disabled"
        report["steps"].append(_rc_step("local-tag", ok=True, skipped=True, reason="disabled"))
    elif dry_run:
        report["tag"]["status"] = "skipped"
        report["tag"]["reason"] = "dry-run"
        report["steps"].append(_rc_step("local-tag", ok=True, skipped=True, reason="dry-run"))
    elif not _git_available():
        report["tag"]["status"] = "skipped"
        report["tag"]["reason"] = "git unavailable"
        report["steps"].append(_rc_step("local-tag", ok=True, skipped=True, reason="git unavailable"))
    else:
        message = _default_tag_message(version, notes_text=notes_text)
        status, reason = _create_local_tag(tag_name=tag_name, message=message)
        report["tag"]["status"] = status
        report["tag"]["reason"] = reason
        if status != "created":
            return _fail_with_step(_rc_step("local-tag", ok=False, reason=reason or "tag failed"))
        report["steps"].append(
            _rc_step("local-tag", ok=True, artifacts={"name": tag_name})
        )

    # 4) Build release bundle
    if dry_run:
        report["steps"].append(_rc_step("build-release-bundle", ok=True, skipped=True, reason="dry-run"))
        report["steps"].append(_rc_step("bundle-verify-strict", ok=True, skipped=True, reason="dry-run"))
        report["ok"] = True
        if not json_stdout and not quiet:
            print(f"[Mesh][Release-RC] Dry-run OK ({zip_path.name})")
            print(f"[Mesh][Release-RC] Would create local tag: {tag_name}")
            print("[Mesh][Release-RC] Would build release bundle and run strict bundle verify")
        return _emit_and_return(0)

    bundle_args = argparse.Namespace(
        command="release",
        release_command="bundle",
        out=str(zip_path),
        seed=seed,
        campaign=campaign,
        report_format="text",
        quiet=quiet,
        notes_since=since,
        notes_until="HEAD",
        deterministic_timestamp=_RC_DETERMINISTIC_TIMESTAMP,
    )
    bundle_rc = release_bundle.handle(bundle_args)
    if bundle_rc != 0 or not zip_path.exists():
        return _fail_with_step(
            _rc_step(
                "build-release-bundle",
                ok=False,
                reason=f"release bundle failed (exit={bundle_rc})",
            )
        )

    manifest_file_count: int | None = None
    try:
        manifest_file_count = _inspect_rc_bundle_notes_manifest(
            zip_path,
            expected_notes_payload=notes_payload,
            expected_notes_text=notes_text,
        )
    except Exception as exc:  # noqa: BLE001  # REASON: release-rc manifest inspection step isolation
        if zip_path.exists():
            try:
                zip_path.unlink()
            except OSError:
                _log_swallow("RELS-002", "cleanup failed zip")
                pass
        return _fail_with_step(
            _rc_step("build-release-bundle", ok=False, reason=f"{type(exc).__name__}: {exc}")
        )

    report["steps"].append(
        _rc_step("build-release-bundle", ok=True, artifacts={"zip": zip_path.name})
    )

    # 5) Strict verify post-check
    verify_report = verify_zip(
        str(zip_path),
        options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
    )
    if not verify_report.get("ok"):
        if zip_path.exists():
            try:
                zip_path.unlink()
            except OSError:
                _log_swallow("RELS-003", "cleanup unverified zip")
                pass
        return _fail_with_step(
            _rc_step(
                "bundle-verify-strict",
                ok=False,
                reason=f"{len(verify_report.get('errors', []))} verification error(s)",
                artifacts={"errors": list(verify_report.get("errors", []))[:5]},
            )
        )

    _update_rc_bundle_report(
        report,
        manifest_file_count=manifest_file_count,
        zip_path=zip_path,
        verify_report=verify_report,
    )
    report["steps"].append(
        _rc_step(
            "bundle-verify-strict",
            ok=True,
            artifacts={
                "verified_count": report["bundle"]["verified_count"],
                "verifiable_files": report["bundle"]["verifiable_files"],
            },
        )
    )

    report["ok"] = True
    _set_rc_version_bump_rolled_back(report, rollback_applied)
    if not json_stdout and not quiet:
        print(f"[Mesh][Release-RC] OK: {zip_path.name}")
    return _emit_and_return(0)


def _handle_promote(args: argparse.Namespace) -> int:
    from mesh_cli.bundle_verify import (
        DEFAULT_EXCLUDE_RULES,
        VerifyOptions,
        verify_zip,
    )

    rc_zip_path = Path(str(getattr(args, "rc", "") or "").strip()).resolve()
    out_zip_path = Path(str(getattr(args, "out", "") or "").strip()).resolve()
    requested_version = str(getattr(args, "promote_version", "") or "").strip() or None
    do_tag = bool(getattr(args, "tag", False))
    notes_since = str(getattr(args, "notes_since", "") or "").strip() or None
    quiet = bool(getattr(args, "quiet", False))
    json_stdout = bool(getattr(args, "promote_json", False))
    dry_run = bool(getattr(args, "dry_run", False))

    if not dry_run and rc_zip_path == out_zip_path:
        print("[Mesh][Release-Promote] ERROR: --out must differ from --rc")
        return 2

    out_zip_path.parent.mkdir(parents=True, exist_ok=True)

    report = _build_promote_report(
        schema_version=_PROMOTE_SCHEMA_VERSION,
        rc_zip_path=rc_zip_path,
        out_zip_path=out_zip_path,
        requested_version=requested_version,
        do_tag=do_tag,
        notes_since=notes_since,
        quiet=quiet,
        json_stdout=json_stdout,
        dry_run=dry_run,
        provenance=provenance_to_dict(get_provenance(deterministic=True)),
        embedded_json_name=_PROMOTE_EMBED_JSON,
        embedded_txt_name=_PROMOTE_EMBED_TXT,
    )
    work_dir: Path | None = None
    output_touched = False

    def _emit_and_return(exit_code: int) -> int:
        _write_promote_reports(out_zip_path, report)
        if json_stdout:
            sys.stdout.write(dumps_json_deterministic(report))
            sys.stdout.write("\n")
        if work_dir is not None and work_dir.exists():
            try:
                shutil.rmtree(work_dir)
            except OSError:
                _log_swallow("RELS-004", "cleanup work dir")
                pass
        return exit_code

    def _fail_with_step(step: dict[str, Any]) -> int:
        nonlocal output_touched
        report["steps"].append(step)
        if output_touched and out_zip_path.exists():
            try:
                out_zip_path.unlink()
            except OSError:
                _log_swallow("RELS-005", "cleanup partial output")
                pass
        return _emit_and_return(1)

    # 1) Verify RC strictly
    rc_verify_report = verify_zip(
        str(rc_zip_path),
        options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
    )
    _set_promote_verify_summary(
        report,
        key="rc_verify",
        summary=_summarize_verify_report(rc_verify_report),
    )
    if not rc_verify_report.get("ok"):
        return _fail_with_step(
            _rc_step(
                "verify-rc-strict",
                ok=False,
                reason=f"{len(rc_verify_report.get('errors', []))} verification error(s)",
                artifacts={"errors": list(rc_verify_report.get("errors", []))[:5]},
            )
        )
    report["steps"].append(
        _rc_step(
            "verify-rc-strict",
            ok=True,
            artifacts={
                "verified_count": report["rc_verify"]["verified_count"],
                "verifiable_files": report["rc_verify"]["verifiable_files"],
            },
        )
    )

    try:
        rc_manifest = _read_manifest_from_zip(rc_zip_path)
    except Exception:
        _log_swallow("RELS-006", "RC manifest read")
        rc_manifest = {}

    # 2) Determine target version
    detected_version = _determine_version_from_rc_manifest(rc_manifest)
    version = requested_version or detected_version or get_tool_version()
    _set_promote_version(report, version=version)
    report["steps"].append(
        _rc_step(
            "determine-version",
            ok=True,
            artifacts={
                "version": version,
                "source": "explicit" if requested_version else ("rc-provenance" if detected_version else "tool-version"),
            },
        )
    )

    # 3) Optional local tag
    tag_name = f"v{version}"
    report["tag"]["name"] = tag_name
    if not do_tag:
        report["tag"]["status"] = "skipped"
        report["tag"]["reason"] = "disabled (--tag not set)"
        report["steps"].append(_rc_step("local-tag", ok=True, skipped=True, reason="disabled"))
    elif dry_run:
        report["tag"]["status"] = "skipped"
        report["tag"]["reason"] = "dry-run"
        report["steps"].append(_rc_step("local-tag", ok=True, skipped=True, reason="dry-run"))
    elif not _git_available():
        report["tag"]["status"] = "skipped"
        report["tag"]["reason"] = "git unavailable"
        report["steps"].append(_rc_step("local-tag", ok=True, skipped=True, reason="git unavailable"))
    else:
        notes_text = format_release_notes_text(
            generate_release_notes(deterministic=True, since=notes_since, until="HEAD")
        )
        message = _default_tag_message(version, notes_text=notes_text)
        status, reason = _create_local_tag(tag_name=tag_name, message=message)
        report["tag"]["status"] = status
        report["tag"]["reason"] = reason
        if status != "created":
            return _fail_with_step(_rc_step("local-tag", ok=False, reason=reason or "tag failed"))
        report["steps"].append(_rc_step("local-tag", ok=True, artifacts={"name": tag_name}))

    if dry_run:
        report["steps"].append(_rc_step("build-final-zip", ok=True, skipped=True, reason="dry-run"))
        report["steps"].append(_rc_step("verify-final-strict", ok=True, skipped=True, reason="dry-run"))
        report["ok"] = True
        if not quiet and not json_stdout:
            print(f"[Mesh][Release-Promote] Dry-run OK ({out_zip_path.name})")
            print("[Mesh][Release-Promote] Would rebuild final ZIP with embedded promote reports")
        return _emit_and_return(0)

    # 4) Rebuild final ZIP with embedded promote reports and refreshed manifest+seal
    work_dir = out_zip_path.parent / f"_promote_work_{out_zip_path.stem}"
    try:
        _prepare_packaging_work_dir(work_dir)
        _extract_zip_to_work_dir(rc_zip_path, work_dir)
        if out_zip_path.exists():
            out_zip_path.unlink()
            output_touched = True
        _rebuild_promoted_zip_with_report(
            work_dir=work_dir,
            out_zip_path=out_zip_path,
            report=report,
            rc_manifest=rc_manifest,
            timestamp=_PROMOTE_DETERMINISTIC_TIMESTAMP,
        )
        output_touched = True
    except Exception as exc:
        return _fail_with_step(
            _rc_step("build-final-zip", ok=False, reason=f"{type(exc).__name__}: {exc}")
        )

    report["steps"].append(
        _rc_step(
            "build-final-zip",
            ok=True,
            artifacts={"zip": out_zip_path.name},
        )
    )

    # 5) Strict verify final ZIP
    verify_report = verify_zip(
        str(out_zip_path),
        options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
    )
    _set_promote_verify_summary(
        report,
        key="final_verify",
        summary=_summarize_verify_report(verify_report),
    )
    if not verify_report.get("ok"):
        return _fail_with_step(
            _rc_step(
                "verify-final-strict",
                ok=False,
                reason=f"{len(verify_report.get('errors', []))} verification error(s)",
                artifacts={"errors": list(verify_report.get("errors", []))[:5]},
            )
        )

    # Re-embed reports so final verify summary is present inside the bundle.
    try:
        _rebuild_promoted_zip_with_report(
            work_dir=work_dir,
            out_zip_path=out_zip_path,
            report=report,
            rc_manifest=rc_manifest,
            timestamp=_PROMOTE_DETERMINISTIC_TIMESTAMP,
        )
    except Exception as exc:
        return _fail_with_step(
            _rc_step("build-final-zip", ok=False, reason=f"{type(exc).__name__}: {exc}")
        )

    final_verify_report = verify_zip(
        str(out_zip_path),
        options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
    )
    _set_promote_verify_summary(
        report,
        key="final_verify",
        summary=_summarize_verify_report(final_verify_report),
    )
    if not final_verify_report.get("ok"):
        return _fail_with_step(
            _rc_step(
                "verify-final-strict",
                ok=False,
                reason=f"{len(final_verify_report.get('errors', []))} verification error(s)",
                artifacts={"errors": list(final_verify_report.get("errors", []))[:5]},
            )
        )

    report["steps"].append(
        _rc_step(
            "verify-final-strict",
            ok=True,
            artifacts={
                "verified_count": report["final_verify"]["verified_count"],
                "verifiable_files": report["final_verify"]["verifiable_files"],
            },
        )
    )

    report["ok"] = True
    if not quiet and not json_stdout:
        print(f"[Mesh][Release-Promote] OK: {out_zip_path.name}")
    return _emit_and_return(0)


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _log_swallow("RELS-007", "manifest JSON load")
        return None
    if not isinstance(data, dict):
        return None
    return data


def _handle_ship(args: argparse.Namespace) -> int:
    from engine.repo_root import get_repo_root
    from mesh_cli.bundle_verify import (
        DEFAULT_EXCLUDE_RULES,
        VerifyOptions,
        verify_zip,
    )
    from mesh_cli.content_integrity import (
        format_content_audit_text,
        has_required_content_roots,
        run_content_audit,
    )
    from mesh_cli.version_info import get_version_file_path

    repo_root = get_repo_root(start=Path.cwd(), strict=False)
    out_dir = Path(str(getattr(args, "out_dir", "") or "").strip()).resolve()
    seed = int(getattr(args, "seed", 123))
    raw_bump = str(getattr(args, "ship_bump", "") or "").strip() or None
    bump_kind = cast(BumpKind, raw_bump) if raw_bump is not None else None
    do_tag = bool(getattr(args, "tag", False))
    since = str(getattr(args, "since", "") or "").strip() or None
    quiet = bool(getattr(args, "quiet", False))
    json_stdout = bool(getattr(args, "ship_json", False))
    dry_run = bool(getattr(args, "dry_run", False))

    rc_zip = out_dir / "rc_bundle.zip"
    final_zip = out_dir / "release_final.zip"
    rc_report_json, rc_report_txt = _rc_report_paths(rc_zip)
    promote_report_json, promote_report_txt = _promote_report_paths(final_zip)

    out_dir.mkdir(parents=True, exist_ok=True)

    report = _build_ship_report(
        schema_version=_SHIP_SCHEMA_VERSION,
        out_dir=out_dir,
        seed=seed,
        bump_kind=bump_kind,
        do_tag=do_tag,
        since=since,
        quiet=quiet,
        json_stdout=json_stdout,
        dry_run=dry_run,
        provenance=provenance_to_dict(get_provenance(deterministic=True)),
        rc_zip=rc_zip,
        final_zip=final_zip,
    )

    version_snapshot: bytes | None = None
    version_file_path: Path | None = None
    rollback_attempted = False

    if bump_kind is not None and not dry_run:
        version_file_path = get_version_file_path()
        try:
            version_snapshot = version_file_path.read_bytes()
        except OSError as exc:
            print(f"[Mesh][Release-Ship] ERROR: cannot snapshot version file: {exc}")
            return 1

    def _rollback_if_needed() -> None:
        nonlocal rollback_attempted
        if rollback_attempted or version_snapshot is None or version_file_path is None:
            return
        try:
            current = version_file_path.read_bytes()
        except OSError:
            _log_swallow("RELS-008", "version snapshot read")
            return
        if current == version_snapshot:
            return
        try:
            version_file_path.write_bytes(version_snapshot)
            rollback_attempted = True
            report["rollback_applied"] = True
        except OSError as exc:
            report["steps"].append(
                _rc_step("rollback-version", ok=False, reason=f"{type(exc).__name__}: {exc}")
            )

    def _emit_and_return(exit_code: int) -> int:
        _write_ship_reports(out_dir, report)
        if json_stdout:
            sys.stdout.write(dumps_json_deterministic(report))
            sys.stdout.write("\n")
        return exit_code

    def _fail_with_step(step: dict[str, Any]) -> int:
        report["steps"].append(step)
        if final_zip.exists():
            try:
                final_zip.unlink()
            except OSError:
                _log_swallow("RELS-009", "cleanup failed final")
                pass
        _rollback_if_needed()
        return _emit_and_return(1)

    content_audit_json_path = out_dir / "content_audit_report.json"
    content_audit_txt_path = out_dir / "content_audit_report.txt"

    if dry_run:
        step_reason = "dry-run"
        report["steps"].append(_rc_step("content-audit", ok=True, skipped=True, reason=step_reason))
        report["steps"].append(
            _rc_step(
                "prepare-version",
                ok=True,
                skipped=bump_kind is None,
                reason=None if bump_kind is not None else "no bump requested",
                artifacts={"bump": bump_kind},
            )
        )
        report["steps"].append(_rc_step("build-rc", ok=True, skipped=True, reason=step_reason))
        report["steps"].append(_rc_step("promote-final", ok=True, skipped=True, reason=step_reason))
        report["steps"].append(_rc_step("verify-artifacts-strict", ok=True, skipped=True, reason=step_reason))
        report["ok"] = True
        if not quiet and not json_stdout:
            print(f"[Mesh][Release-Ship] Dry-run OK ({out_dir.name})")
        return _emit_and_return(0)

    # Remove stale output artifacts for a clean run.
    for stale in (rc_zip, final_zip):
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                _log_swallow("RELS-010", "cleanup stale files")
                pass

    # Preflight content integrity to guard release artifacts from orphaned content refs.
    if has_required_content_roots(repo_root):
        content_audit = run_content_audit(repo_root)
        write_json_atomic(
            content_audit_json_path,
            content_audit.to_dict(),
            indent=2,
            sort_keys=True,
            trailing_newline=True,
            durable=True,
        )
        write_text_atomic(
            content_audit_txt_path,
            format_content_audit_text(content_audit),
            encoding="utf-8",
            durable=True,
        )
        if not content_audit.ok:
            return _fail_with_step(
                _rc_step(
                    "content-audit",
                    ok=False,
                    reason="content audit found errors",
                    artifacts={
                        "content_audit_report_json": content_audit_json_path.name,
                        "content_audit_report_txt": content_audit_txt_path.name,
                    },
                )
            )
        report["steps"].append(
            _rc_step(
                "content-audit",
                ok=True,
                artifacts={
                    "content_audit_report_json": content_audit_json_path.name,
                    "content_audit_report_txt": content_audit_txt_path.name,
                },
            )
        )
    else:
        report["steps"].append(
            _rc_step(
                "content-audit",
                ok=True,
                skipped=True,
                reason="content roots missing",
            )
        )

    report["steps"].append(
        _rc_step(
            "prepare-version",
            ok=True,
            skipped=bump_kind is None,
            reason=None if bump_kind is not None else "no bump requested",
            artifacts={"bump": bump_kind},
        )
    )

    # 1) Build RC (with optional bump). Disable RC tag; ship tag is owned by promote step.
    rc_args = argparse.Namespace(
        command="release",
        release_command="rc",
        out=str(rc_zip),
        seed=seed,
        rc_version=None,
        rc_bump=bump_kind,
        since=since,
        tag=False,
        no_write_version=False,
        no_rollback=True,
        quiet=True,
        rc_json=False,
        dry_run=False,
    )
    rc_code = _handle_rc(rc_args)
    rc_payload = _load_json_if_exists(rc_report_json)
    if rc_code != 0 or not rc_zip.exists():
        return _fail_with_step(
            _rc_step(
                "build-rc",
                ok=False,
                reason=f"release rc failed (exit={rc_code})",
                artifacts={"rc_report_json": rc_report_json.name},
            )
        )
    report["steps"].append(
        _rc_step(
            "build-rc",
            ok=True,
            artifacts={
                "rc_zip": rc_zip.name,
                "rc_report_json": rc_report_json.name,
                "rc_report_txt": rc_report_txt.name,
            },
        )
    )

    # 2) Promote RC -> Final
    promote_args = argparse.Namespace(
        command="release",
        release_command="promote",
        rc=str(rc_zip),
        out=str(final_zip),
        promote_version=None,
        tag=do_tag,
        notes_since=since,
        quiet=True,
        promote_json=False,
        dry_run=False,
    )
    promote_code = _handle_promote(promote_args)
    promote_payload = _load_json_if_exists(promote_report_json)
    if promote_code != 0 or not final_zip.exists():
        return _fail_with_step(
            _rc_step(
                "promote-final",
                ok=False,
                reason=f"release promote failed (exit={promote_code})",
                artifacts={"promote_report_json": promote_report_json.name},
            )
        )
    report["steps"].append(
        _rc_step(
            "promote-final",
            ok=True,
            artifacts={
                "final_zip": final_zip.name,
                "promote_report_json": promote_report_json.name,
                "promote_report_txt": promote_report_txt.name,
            },
        )
    )

    # 3) Strict verify both artifacts and record summaries.
    rc_verify_report = verify_zip(
        str(rc_zip),
        options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
    )
    final_verify_report = verify_zip(
        str(final_zip),
        options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
    )
    _set_ship_verify_summary(report, key="rc", verify_report=rc_verify_report)
    _set_ship_verify_summary(report, key="final", verify_report=final_verify_report)
    if not rc_verify_report.get("ok"):
        return _fail_with_step(
            _rc_step(
                "verify-artifacts-strict",
                ok=False,
                reason="rc strict verify failed",
                artifacts={"errors": list(rc_verify_report.get("errors", []))[:5]},
            )
        )
    if not final_verify_report.get("ok"):
        return _fail_with_step(
            _rc_step(
                "verify-artifacts-strict",
                ok=False,
                reason="final strict verify failed",
                artifacts={"errors": list(final_verify_report.get("errors", []))[:5]},
            )
        )

    report["steps"].append(
        _rc_step(
            "verify-artifacts-strict",
            ok=True,
            artifacts={
                "rc_verified_count": report["verify"]["rc"]["verified_count"],
                "rc_verifiable_files": report["verify"]["rc"]["verifiable_files"],
                "final_verified_count": report["verify"]["final"]["verified_count"],
                "final_verifiable_files": report["verify"]["final"]["verifiable_files"],
            },
        )
    )

    # Surface tag results from child reports.
    _set_ship_child_report_projection(
        report,
        rc_payload=rc_payload,
        promote_payload=promote_payload,
    )

    report["ok"] = True
    if not quiet and not json_stdout:
        print(f"[Mesh][Release-Ship] OK: {out_dir.name}")
    return _emit_and_return(0)


def _handle_check(args: argparse.Namespace) -> int:
    repo_root = Path(str(getattr(args, "repo_root", ".") or ".")).resolve()
    deterministic = bool(getattr(args, "deterministic", False))
    quiet = bool(getattr(args, "quiet", False))
    if not repo_root.exists() or not repo_root.is_dir():
        if not quiet:
            print(f"[Mesh][Release] ERROR invalid repo root: {repo_root.as_posix()}")
        return 2

    artifacts_raw = str(getattr(args, "artifacts", "") or "artifacts/release").strip()
    artifacts_dir = Path(artifacts_raw)
    if not artifacts_dir.is_absolute():
        artifacts_dir = repo_root / artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    report_path = _resolve_path(getattr(args, "report", None), repo_root, artifacts_dir / "release_report.json")
    summary_path = _resolve_path(getattr(args, "summary", None), repo_root, artifacts_dir / "release_report.txt")

    asset_audit_path = artifacts_dir / "asset_audit.json"
    export_dir = artifacts_dir / "bundle"
    debug_bundle_path = artifacts_dir / "debug_bundle.json"
    verify_artifacts_dir = artifacts_dir
    report = build_release_check_report(
        repo_root=repo_root,
        artifacts_dir=artifacts_dir,
        report_path=report_path,
        summary_path=summary_path,
        deterministic=deterministic,
    )

    def _run_verify_all_step() -> tuple[int, dict[str, Any]]:
        try:
            return _run_verify_all(repo_root, verify_artifacts_dir, deterministic=deterministic)
        except TypeError:
            return _run_verify_all(repo_root, verify_artifacts_dir)

    def _run_export_build_step() -> tuple[int, dict[str, Any]]:
        try:
            return _run_export_build(repo_root, export_dir, deterministic=deterministic)
        except TypeError:
            return _run_export_build(repo_root, export_dir)

    def _run_debug_bundle_step() -> tuple[int, dict[str, Any]]:
        try:
            return _run_debug_bundle(repo_root, debug_bundle_path, deterministic=True)
        except TypeError:
            return _run_debug_bundle(repo_root, debug_bundle_path)

    steps = [
        ("verify-all", _run_verify_all_step),
        ("asset-audit", lambda: _run_assets_audit(repo_root, asset_audit_path)),
        ("export-build", _run_export_build_step),
        ("debug-bundle", _run_debug_bundle_step),
    ]

    exit_code = 0
    failed_step: str | None = None
    skipped: list[str] = []

    for idx, (name, runner) in enumerate(steps):
        step_exit, outputs, error = _run_step(runner)
        if deterministic:
            outputs = _normalize_outputs(outputs, repo_root)
        report["steps"].append(_step_record(name, step_exit, outputs=outputs, error=error))
        if step_exit != 0:
            failed_step = name
            exit_code = int(step_exit)
            skipped = [sname for sname, _ in steps[idx + 1 :]]
            break

    summary = report.get("summary")
    if isinstance(summary, dict):
        summary["ok"] = failed_step is None
        summary["failed_step"] = failed_step
        summary["skipped_steps"] = skipped

    _write_report(report_path, report)
    _write_summary(
        summary_path,
        report,
        failed_step=failed_step,
        exit_code=exit_code,
    )

    if failed_step is None:
        if not quiet:
            print("[Mesh][Release] OK")
        return 0
    if not quiet:
        print(f"[Mesh][Release] FAILED at {failed_step} (exit={exit_code})")
        print(f"[Mesh][Release] Report: {report_path.as_posix()}")
    return exit_code or 1
