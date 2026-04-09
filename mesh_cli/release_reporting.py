from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.persistence_io import write_json_atomic, write_text_atomic


def _rc_step(
    name: str,
    *,
    ok: bool,
    skipped: bool = False,
    reason: str | None = None,
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "skipped": bool(skipped),
        "reason": reason,
        "artifacts": dict(artifacts or {}),
    }


def _rc_report_paths(zip_path: Path) -> tuple[Path, Path]:
    return (
        zip_path.with_name(f"{zip_path.name}.rc_report.json"),
        zip_path.with_name(f"{zip_path.name}.rc_report.txt"),
    )


def _format_rc_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Mesh Release Candidate Report")
    lines.append(f"Result: {'OK' if report.get('ok') else 'FAILED'}")
    lines.append(f"Version: {report.get('version')}")
    lines.append(f"Seed: {report.get('seed')}")
    lines.append(f"Bundle: {report.get('bundle', {}).get('zip')}")
    lines.append("")
    lines.append("Steps:")
    for step in report.get("steps", []):
        name = str(step.get("name", ""))
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
    bundle = report.get("bundle", {})
    lines.append(
        "Verify: "
        f"verified={bundle.get('verified_count')} "
        f"verifiable={bundle.get('verifiable_files')} "
        f"sealed_manifest_verified={bundle.get('sealed_manifest_verified')}"
    )
    return "\n".join(lines) + "\n"


def _write_rc_reports(zip_path: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    json_path, txt_path = _rc_report_paths(zip_path)
    write_json_atomic(json_path, report, indent=2, sort_keys=True, trailing_newline=True)
    write_text_atomic(txt_path, _format_rc_report_text(report), encoding="utf-8")
    return json_path, txt_path


def _ship_report_paths(out_dir: Path) -> tuple[Path, Path]:
    return out_dir / "ship_report.json", out_dir / "ship_report.txt"


def _format_ship_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Mesh Release Ship Report")
    lines.append(f"Result: {'OK' if report.get('ok') else 'FAILED'}")
    lines.append(f"Out Dir: {report.get('out_dir')}")
    lines.append(f"RC ZIP: {report.get('artifacts', {}).get('rc_zip')}")
    lines.append(f"Final ZIP: {report.get('artifacts', {}).get('final_zip')}")
    lines.append("")
    rc_verify = report.get("verify", {}).get("rc", {})
    final_verify = report.get("verify", {}).get("final", {})
    lines.append(
        "RC Verify: "
        f"ok={rc_verify.get('ok')} "
        f"verified={rc_verify.get('verified_count')} "
        f"verifiable={rc_verify.get('verifiable_files')}"
    )
    lines.append(
        "Final Verify: "
        f"ok={final_verify.get('ok')} "
        f"verified={final_verify.get('verified_count')} "
        f"verifiable={final_verify.get('verifiable_files')}"
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
    return "\n".join(lines) + "\n"


def _write_ship_reports(out_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    json_path, txt_path = _ship_report_paths(out_dir)
    write_json_atomic(json_path, report, indent=2, sort_keys=True, trailing_newline=True)
    write_text_atomic(txt_path, _format_ship_report_text(report), encoding="utf-8")
    return json_path, txt_path
