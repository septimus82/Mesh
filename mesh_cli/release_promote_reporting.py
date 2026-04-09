from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.persistence_io import write_json_atomic, write_text_atomic


def _build_promote_report(
    *,
    schema_version: int,
    rc_zip_path: Path,
    out_zip_path: Path,
    requested_version: str | None,
    do_tag: bool,
    notes_since: str | None,
    quiet: bool,
    json_stdout: bool,
    dry_run: bool,
    provenance: dict[str, Any],
    embedded_json_name: str,
    embedded_txt_name: str,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "ok": False,
        "dry_run": dry_run,
        "rc_zip": rc_zip_path.name,
        "final_zip": out_zip_path.name,
        "version": None,
        "args": {
            "rc": rc_zip_path.name,
            "out": out_zip_path.name,
            "version": requested_version,
            "tag": do_tag,
            "notes_since": notes_since,
            "quiet": quiet,
            "json": json_stdout,
            "dry_run": dry_run,
        },
        "provenance": provenance,
        "tag": {"name": None, "status": "pending", "reason": None},
        "rc_verify": {
            "ok": False,
            "verified_count": 0,
            "verifiable_files": 0,
            "manifest_files": 0,
            "sealed_manifest_verified": False,
            "errors": [],
        },
        "final_verify": {
            "ok": False,
            "verified_count": 0,
            "verifiable_files": 0,
            "manifest_files": 0,
            "sealed_manifest_verified": False,
            "errors": [],
        },
        "reports": {
            "json": f"{out_zip_path.name}.promote_report.json",
            "txt": f"{out_zip_path.name}.promote_report.txt",
            "embedded_json": embedded_json_name,
            "embedded_txt": embedded_txt_name,
        },
        "steps": [],
    }


def _set_promote_version(report: dict[str, Any], *, version: str) -> None:
    report["version"] = version
    provenance = report.get("provenance")
    if isinstance(provenance, dict):
        provenance["promote_version"] = version


def _set_promote_verify_summary(
    report: dict[str, Any],
    *,
    key: str,
    summary: dict[str, Any],
) -> None:
    if key not in {"rc_verify", "final_verify"}:
        raise ValueError(f"unsupported promote verify summary key: {key}")
    report[key] = dict(summary)


def _promote_report_paths(zip_path: Path) -> tuple[Path, Path]:
    return (
        zip_path.with_name(f"{zip_path.name}.promote_report.json"),
        zip_path.with_name(f"{zip_path.name}.promote_report.txt"),
    )


def _summarize_verify_report(report: dict[str, Any]) -> dict[str, Any]:
    counts = report.get("counts", {})
    return {
        "ok": bool(report.get("ok", False)),
        "verified_count": int(counts.get("verified_files", report.get("verified_count", 0))),
        "verifiable_files": int(counts.get("verifiable_files", report.get("file_count", 0))),
        "manifest_files": int(counts.get("manifest_files", 0)),
        "sealed_manifest_verified": bool(report.get("sealed_manifest_verified", False)),
        "errors": list(report.get("errors", []))[:5],
    }


def _format_promote_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Mesh Release Promote Report")
    lines.append(f"Result: {'OK' if report.get('ok') else 'FAILED'}")
    lines.append(f"Version: {report.get('version')}")
    lines.append(f"RC ZIP: {report.get('rc_zip')}")
    lines.append(f"Final ZIP: {report.get('final_zip')}")
    lines.append("")
    rc_verify = report.get("rc_verify", {})
    lines.append(
        "RC Verify: "
        f"ok={rc_verify.get('ok')} "
        f"verified={rc_verify.get('verified_count')} "
        f"verifiable={rc_verify.get('verifiable_files')} "
        f"sealed_manifest_verified={rc_verify.get('sealed_manifest_verified')}"
    )
    final_verify = report.get("final_verify", {})
    lines.append(
        "Final Verify: "
        f"ok={final_verify.get('ok')} "
        f"verified={final_verify.get('verified_count')} "
        f"verifiable={final_verify.get('verifiable_files')} "
        f"sealed_manifest_verified={final_verify.get('sealed_manifest_verified')}"
    )
    lines.append("")
    lines.append("Steps:")
    for step in report.get("steps", []):
        name = str(step.get("name", "") or "")
        if step.get("skipped"):
            lines.append(f"- {name}: SKIPPED ({step.get('reason')})")
        elif step.get("ok"):
            lines.append(f"- {name}: OK")
        else:
            lines.append(f"- {name}: FAILED ({step.get('reason')})")
    lines.append("")
    tag = report.get("tag", {})
    lines.append(f"Tag: {tag.get('status')} ({tag.get('name')})")
    if tag.get("reason"):
        lines.append(f"Tag Reason: {tag.get('reason')}")
    return "\n".join(lines) + "\n"


def _write_promote_reports(out_zip_path: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    from . import release as release_mod

    json_path, txt_path = release_mod._promote_report_paths(out_zip_path)
    write_json_atomic(json_path, report, indent=2, sort_keys=True, trailing_newline=True)
    write_text_atomic(txt_path, release_mod._format_promote_report_text(report), encoding="utf-8")
    return json_path, txt_path
