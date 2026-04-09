from __future__ import annotations

from pathlib import Path
from typing import Any


def _build_rc_report(
    *,
    schema_version: int,
    version: str,
    seed: int,
    campaign: str,
    dry_run: bool,
    zip_path: Path,
    bump_kind: str | None,
    since: str | None,
    quiet: bool,
    json_stdout: bool,
    do_tag: bool,
    no_write_version: bool,
    no_rollback: bool,
    provenance: dict[str, Any],
    tag_name: str,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "ok": False,
        "version": version,
        "seed": seed,
        "campaign": campaign,
        "dry_run": dry_run,
        "args": {
            "out": zip_path.name,
            "seed": seed,
            "version": version,
            "bump": bump_kind,
            "since": since,
            "quiet": quiet,
            "json": json_stdout,
            "dry_run": dry_run,
            "tag": do_tag,
            "no_write_version": no_write_version,
            "no_rollback": no_rollback,
        },
        "provenance": {
            **provenance,
            "rc_version": version,
        },
        "steps": [],
        "tag": {"name": tag_name, "status": "pending", "reason": None},
        "bundle": {
            "zip": zip_path.name,
            "file_count": None,
            "size_bytes": None,
            "verified_count": None,
            "verifiable_files": None,
            "sealed_manifest_verified": None,
        },
        "reports": {
            "json": f"{zip_path.name}.rc_report.json",
            "txt": f"{zip_path.name}.rc_report.txt",
        },
    }


def _set_rc_version_bump(
    report: dict[str, Any],
    *,
    bump_kind: str | None,
    old_version: str,
    new_version: str,
    file_path: str,
    wrote: bool,
    no_write_version: bool,
) -> None:
    report["version_bump"] = {
        "kind": bump_kind,
        "old": old_version,
        "new": new_version,
        "file": file_path,
        "wrote": wrote,
        "rolled_back": False,
        "no_write_version": no_write_version,
    }


def _set_rc_version_bump_rolled_back(report: dict[str, Any], rolled_back: bool) -> None:
    if isinstance(report.get("version_bump"), dict):
        report["version_bump"]["rolled_back"] = bool(rolled_back)


def _update_rc_bundle_report(
    report: dict[str, Any],
    *,
    manifest_file_count: int | None,
    zip_path: Path,
    verify_report: dict[str, Any],
) -> None:
    counts = verify_report.get("counts", {})
    report["bundle"].update(
        {
            "file_count": manifest_file_count,
            "size_bytes": zip_path.stat().st_size if zip_path.exists() else None,
            "verified_count": int(counts.get("verified_files", 0)),
            "verifiable_files": int(counts.get("verifiable_files", 0)),
            "sealed_manifest_verified": bool(verify_report.get("sealed_manifest_verified", False)),
        }
    )
