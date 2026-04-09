from __future__ import annotations

from pathlib import Path
from typing import Any


def _build_ship_report(
    *,
    schema_version: int,
    out_dir: Path,
    seed: int,
    bump_kind: str | None,
    do_tag: bool,
    since: str | None,
    quiet: bool,
    json_stdout: bool,
    dry_run: bool,
    provenance: dict[str, Any],
    rc_zip: Path,
    final_zip: Path,
) -> dict[str, Any]:
    from . import release as release_mod

    rc_report_json, rc_report_txt = release_mod._rc_report_paths(rc_zip)
    promote_report_json, promote_report_txt = release_mod._promote_report_paths(final_zip)
    ship_report_json, ship_report_txt = release_mod._ship_report_paths(out_dir)
    return {
        "schema_version": schema_version,
        "ok": False,
        "dry_run": dry_run,
        "out_dir": out_dir.name,
        "seed": seed,
        "bump": bump_kind,
        "tag": do_tag,
        "since": since,
        "args": {
            "out_dir": out_dir.name,
            "seed": seed,
            "bump": bump_kind,
            "tag": do_tag,
            "since": since,
            "quiet": quiet,
            "json": json_stdout,
            "dry_run": dry_run,
        },
        "provenance": provenance,
        "artifacts": {
            "content_audit_report_json": "content_audit_report.json",
            "content_audit_report_txt": "content_audit_report.txt",
            "rc_zip": rc_zip.name,
            "rc_report_json": rc_report_json.name,
            "rc_report_txt": rc_report_txt.name,
            "final_zip": final_zip.name,
            "promote_report_json": promote_report_json.name,
            "promote_report_txt": promote_report_txt.name,
            "ship_report_json": ship_report_json.name,
            "ship_report_txt": ship_report_txt.name,
        },
        "verify": {
            "rc": {
                "ok": False,
                "verified_count": 0,
                "verifiable_files": 0,
                "manifest_files": 0,
                "sealed_manifest_verified": False,
                "errors": [],
            },
            "final": {
                "ok": False,
                "verified_count": 0,
                "verifiable_files": 0,
                "manifest_files": 0,
                "sealed_manifest_verified": False,
                "errors": [],
            },
        },
        "steps": [],
    }


def _set_ship_verify_summary(
    report: dict[str, Any],
    *,
    key: str,
    verify_report: dict[str, Any],
) -> None:
    if key not in {"rc", "final"}:
        raise ValueError(f"unsupported ship verify summary key: {key}")
    from . import release as release_mod

    verify = report.get("verify")
    if not isinstance(verify, dict):
        verify = {}
        report["verify"] = verify
    verify[key] = release_mod._summarize_verify_report(verify_report)


def _set_ship_child_report_projection(
    report: dict[str, Any],
    *,
    rc_payload: dict[str, Any] | None,
    promote_payload: dict[str, Any] | None,
) -> None:
    if isinstance(promote_payload, dict):
        report["tag_result"] = dict(promote_payload.get("tag", {}))
        if "version" in promote_payload:
            report["version"] = promote_payload["version"]
    elif isinstance(rc_payload, dict):
        report["tag_result"] = dict(rc_payload.get("tag", {}))
        if "version" in rc_payload:
            report["version"] = rc_payload["version"]
