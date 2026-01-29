from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

from engine import json_io
from engine.paths import reset_path_caches, set_content_roots
from engine.tooling.content_commands import content_contract_command
from mesh_cli import pack as pack_commands


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


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("release-contract", help="Run deterministic release contract checks")
    parser.add_argument("--artifacts", help="Optional artifacts directory for logs/outputs")
    parser.add_argument("--repo-root", help="Repo root for pack/content discovery (default: cwd)")
    parser.add_argument("--report", help="Optional JSON report path")
    parser.add_argument("--with-asset-audit", default=True, type=_parse_bool, help="Enable asset audit step")
    parser.add_argument("--asset-audit-orphans", action="store_true", help="Enable orphan detection")
    parser.add_argument("--asset-audit-duplicates", default=True, type=_parse_bool, help="Enable duplicate detection")
    parser.add_argument(
        "--asset-audit-warn-duplicates",
        default=True,
        type=_parse_bool,
        help="Treat duplicates as warnings",
    )
    parser.add_argument("--asset-audit-strict", action="store_true", help="Treat asset audit warnings as errors")
    parser.add_argument("--strict", action="store_true", help="Enable strict release gates")
    parser.set_defaults(func=release_contract_command)


def release_contract_command(args: argparse.Namespace) -> int:
    artifacts_raw = str(getattr(args, "artifacts", "") or "").strip()
    artifacts_dir = Path(artifacts_raw) if artifacts_raw else None
    repo_root_raw = str(getattr(args, "repo_root", "") or "").strip()
    repo_root = Path(repo_root_raw) if repo_root_raw else None
    report_raw = str(getattr(args, "report", "") or "").strip()
    report_path = Path(report_raw) if report_raw else None
    strict = bool(getattr(args, "strict", False))
    with_asset_audit = _parse_bool(getattr(args, "with_asset_audit", True), default=True)
    asset_audit_orphans = bool(getattr(args, "asset_audit_orphans", False))
    asset_audit_duplicates = _parse_bool(getattr(args, "asset_audit_duplicates", True), default=True)
    asset_audit_warn_dups = _parse_bool(getattr(args, "asset_audit_warn_duplicates", True), default=True)
    asset_audit_strict = bool(getattr(args, "asset_audit_strict", False)) or strict
    return run_release_contract(
        artifacts_dir=artifacts_dir,
        repo_root=repo_root,
        report_path=report_path,
        with_asset_audit=bool(with_asset_audit),
        asset_audit_orphans=asset_audit_orphans,
        asset_audit_duplicates=bool(asset_audit_duplicates),
        asset_audit_warn_duplicates=bool(asset_audit_warn_dups),
        asset_audit_strict=asset_audit_strict,
        strict=strict,
    )


def run_release_contract(
    *,
    artifacts_dir: Path | None = None,
    repo_root: Path | None = None,
    report_path: Path | None = None,
    quiet: bool = False,
    with_asset_audit: bool = True,
    asset_audit_orphans: bool = False,
    asset_audit_duplicates: bool = True,
    asset_audit_warn_duplicates: bool = True,
    asset_audit_strict: bool = False,
    strict: bool = False,
) -> int:
    resolved_root = _resolve_repo_root(repo_root)
    if resolved_root is None:
        return 2

    artifacts_dir = _resolve_artifacts_dir(artifacts_dir, resolved_root)
    report_path = _resolve_report_path(report_path, resolved_root)
    if artifacts_dir is not None:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)

    report = _new_report(resolved_root, artifacts_dir)

    def _emit(text: str) -> None:
        if not quiet:
            print(text)

    _emit("[Mesh][Release] pack-validate ...")
    rc, pack_result = _run_pack_validate(resolved_root)
    pack_outputs = {"errors": pack_result.errors}
    if pack_result.presets_validated is not None:
        pack_outputs["presets_validated"] = pack_result.presets_validated
    if pack_result.fx_errors is not None:
        pack_outputs["fx_errors"] = pack_result.fx_errors
    report["steps"].append(
        _step_record(
            name="pack-validate",
            exit_code=rc,
            outputs=pack_outputs,
        )
    )
    report["counts"]["presets_validated"] = pack_result.presets_validated
    total_errors = pack_result.errors
    if rc != 0:
        report["counts"]["errors"] = total_errors
        return _finalize_report(report, report_path, failed_step="pack-validate", exit_code=rc)

    _emit("[Mesh][Release] asset-audit ...")
    audit_out = artifacts_dir / "asset_audit.json" if artifacts_dir is not None else None
    audit_with_orphans = asset_audit_orphans if with_asset_audit else False
    audit_with_duplicates = asset_audit_duplicates if with_asset_audit else False
    audit_warn_duplicates = asset_audit_warn_duplicates if with_asset_audit else False
    rc, audit_report = _run_asset_audit(
        resolved_root,
        out_path=audit_out,
        with_orphans=audit_with_orphans,
        with_duplicates=audit_with_duplicates,
        warn_duplicates=audit_warn_duplicates,
        strict=asset_audit_strict or strict,
        fail_missing=True,
        fail_orphans=False,
        fail_duplicates=False,
    )
    audit_outputs = {
        "errors": audit_report.get("summary", {}).get("error_count") if audit_report else None,
        "warnings": audit_report.get("summary", {}).get("warning_count") if audit_report else None,
        "orphans": audit_report.get("summary", {}).get("orphan_count") if audit_report else None,
        "duplicate_groups": audit_report.get("summary", {}).get("duplicate_groups") if audit_report else None,
        "asset_audit_json": audit_out.as_posix() if audit_out is not None else None,
    }
    report["steps"].append(
        _step_record(
            name="asset-audit",
            exit_code=rc,
            outputs=audit_outputs,
        )
    )
    if audit_report is not None:
        summary = audit_report.get("summary", {})
        report["counts"]["missing_files"] = summary.get("missing_files")
        report["counts"]["invalid_values"] = summary.get("invalid_values")
        report["counts"]["cross_pack_refs"] = summary.get("cross_pack_refs")
        report["counts"]["orphan_count"] = summary.get("orphan_count")
        report["counts"]["duplicate_groups"] = summary.get("duplicate_groups")
        report["counts"]["warning_count"] = summary.get("warning_count")
        report["counts"]["error_count"] = summary.get("error_count")
        total_errors += int(summary.get("error_count") or 0)
    if rc != 0:
        report["counts"]["errors"] = total_errors
        return _finalize_report(report, report_path, failed_step="asset-audit", exit_code=rc)

    _emit("[Mesh][Release] content-contract ...")
    log_path = artifacts_dir / "content_contract.log" if artifacts_dir is not None else None
    rc, content_result = _run_content_contract(resolved_root, log_path)
    content_outputs = {
        "files_checked": content_result.files_checked if content_result is not None else None,
        "errors": content_result.errors if content_result is not None else None,
    }
    report["steps"].append(
        _step_record(
            name="content-contract",
            exit_code=rc,
            log_path=log_path,
            outputs=content_outputs,
        )
    )
    if content_result is not None:
        report["counts"]["content_files_checked"] = content_result.files_checked
        total_errors += content_result.errors
    if rc != 0:
        report["counts"]["errors"] = total_errors
        return _finalize_report(report, report_path, failed_step="content-contract", exit_code=rc)

    if artifacts_dir is not None:
        rc = _run_pack_registry(resolved_root, artifacts_dir)
        registry_outputs = {
            "asset_registry_json": (artifacts_dir / "asset_registry.json").as_posix(),
            "errors": 0 if rc == 0 else 1,
        }
        report["steps"].append(
            _step_record(
                name="asset-registry",
                exit_code=rc,
                outputs=registry_outputs,
            )
        )
        if rc != 0:
            total_errors += 1
            report["counts"]["errors"] = total_errors
            return _finalize_report(report, report_path, failed_step="asset-registry", exit_code=rc)

    report["counts"]["errors"] = total_errors

    _emit("[Mesh][Release] DONE OK")
    return _finalize_report(report, report_path, failed_step=None, exit_code=0)


def _run_pack_validate(repo_root: Path) -> tuple[int, pack_commands.PackValidationResult]:
    set_content_roots([repo_root])
    try:
        result = pack_commands.run_pack_validate(with_fx=True, emit=True)
        return (0 if result.ok else 2), result
    finally:
        reset_path_caches()


def _run_content_contract(repo_root: Path, log_path: Path | None):
    args = argparse.Namespace(
        paths=None,
        repo_root=str(repo_root),
        with_prefabs=True,
        with_behaviours=True,
        log=str(log_path) if log_path is not None else None,
        _capture_result=True,
    )
    rc = int(content_contract_command(args))
    result = getattr(args, "_result", None)
    return rc, result


def _run_pack_registry(repo_root: Path, artifacts_dir: Path) -> int:
    out_path = artifacts_dir / "asset_registry.json"
    args = argparse.Namespace(
        pack_command="build-registry",
        out=str(out_path),
        include_unused=False,
        format="text",
    )
    set_content_roots([repo_root])
    try:
        return int(pack_commands.handle(args))
    finally:
        reset_path_caches()


def _run_asset_audit(
    repo_root: Path,
    *,
    out_path: Path | None,
    with_orphans: bool,
    with_duplicates: bool,
    warn_duplicates: bool,
    strict: bool,
    fail_missing: bool,
    fail_orphans: bool,
    fail_duplicates: bool,
) -> tuple[int, Mapping]:
    from engine.tooling.assets_audit import run_asset_audit

    rc, report = run_asset_audit(
        repo_root=repo_root,
        out_path=out_path,
        strict=strict,
        with_orphans=with_orphans,
        with_duplicates=with_duplicates,
        warn_duplicates=warn_duplicates,
        fail_missing=fail_missing,
        fail_orphans=fail_orphans,
        fail_duplicates=fail_duplicates,
        write_report=out_path is not None,
    )
    return rc, report


def _resolve_repo_root(repo_root: Path | None) -> Path | None:
    if repo_root is None:
        return Path.cwd().resolve()
    candidate = repo_root.expanduser()
    if not candidate.exists() or not candidate.is_dir():
        print(f"[Mesh][Release] ERROR invalid repo root: {candidate.as_posix()}")
        return None
    return candidate.resolve()


def _resolve_artifacts_dir(artifacts_dir: Path | None, repo_root: Path) -> Path | None:
    if artifacts_dir is None:
        return None
    if artifacts_dir.is_absolute():
        return artifacts_dir
    return repo_root / artifacts_dir


def _resolve_report_path(report_path: Path | None, repo_root: Path) -> Path | None:
    if report_path is None:
        return None
    if report_path.is_absolute():
        return report_path
    return repo_root / report_path


def _new_report(repo_root: Path, artifacts_dir: Path | None) -> dict:
    return {
        "schema_version": 1,
        "repo_root": repo_root.as_posix(),
        "artifacts_dir": artifacts_dir.as_posix() if artifacts_dir is not None else None,
        "steps": [],
        "summary": {"ok": False, "failed_step": None},
        "counts": {
            "presets_validated": None,
            "content_files_checked": None,
            "errors": None,
            "missing_files": None,
            "invalid_values": None,
            "cross_pack_refs": None,
            "orphan_count": None,
            "duplicate_groups": None,
            "warning_count": None,
            "error_count": None,
        },
    }


def _step_record(
    *,
    name: str,
    exit_code: int,
    log_path: Path | None = None,
    outputs: Mapping[str, object] | None = None,
) -> dict:
    record = {
        "name": name,
        "ok": exit_code == 0,
        "exit_code": int(exit_code),
        "log_path": log_path.as_posix() if log_path is not None else None,
    }
    if outputs:
        record["outputs"] = dict(outputs)
    return record


def _finalize_report(
    report: dict,
    report_path: Path | None,
    *,
    failed_step: str | None,
    exit_code: int,
) -> int:
    summary = report.get("summary")
    if isinstance(summary, dict):
        summary["ok"] = failed_step is None and exit_code == 0
        summary["failed_step"] = failed_step
    if report_path is not None:
        try:
            validate_release_report_v1(report)
        except Exception as exc:  # noqa: BLE001
            print(f"[Mesh][Release] ERROR invalid report: {exc}")
            return 1
        if not _write_report(report_path, report):
            if exit_code == 0:
                return 1
    return int(exit_code)


def _write_report(path: Path, report: dict) -> bool:
    try:
        json_io.write_json_atomic(path, report)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Release] ERROR failed to write report: {exc}")
        return False


def validate_release_report_v1(report: dict) -> None:
    if not isinstance(report, dict):
        raise ValueError("report must be a dict")

    _require_key(report, "schema_version", int, path="schema_version")
    if report["schema_version"] != 1:
        raise ValueError("schema_version must be 1")

    _require_key(report, "repo_root", str, path="repo_root")
    _require_optional(report, "artifacts_dir", str, path="artifacts_dir")
    _require_key(report, "steps", list, path="steps")
    _require_key(report, "summary", dict, path="summary")
    _require_key(report, "counts", dict, path="counts")

    summary = report["summary"]
    _require_key(summary, "ok", bool, path="summary.ok")
    _require_optional(summary, "failed_step", str, path="summary.failed_step")

    counts = report["counts"]
    _require_optional_int(counts, "presets_validated", path="counts.presets_validated")
    _require_optional_int(counts, "content_files_checked", path="counts.content_files_checked")
    _require_optional_int(counts, "errors", path="counts.errors")

    steps = report["steps"]
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{idx}] must be a dict")
        _require_key(step, "name", str, path=f"steps[{idx}].name")
        _require_key(step, "ok", bool, path=f"steps[{idx}].ok")
        _require_key(step, "exit_code", int, path=f"steps[{idx}].exit_code")
        _require_optional(step, "log_path", str, path=f"steps[{idx}].log_path")
        if "outputs" in step and step["outputs"] is not None:
            if not isinstance(step["outputs"], dict):
                raise ValueError(f"steps[{idx}].outputs must be a dict or null")
            _validate_json_value(step["outputs"], path=f"steps[{idx}].outputs")


def _require_key(obj: dict, key: str, expected_type: type, *, path: str) -> None:
    if key not in obj:
        raise ValueError(f"{path} is required")
    value = obj[key]
    if not isinstance(value, expected_type):
        raise ValueError(f"{path} must be {expected_type.__name__}, got {type(value).__name__}")


def _require_optional(obj: dict, key: str, expected_type: type, *, path: str) -> None:
    if key not in obj or obj[key] is None:
        return
    value = obj[key]
    if not isinstance(value, expected_type):
        raise ValueError(f"{path} must be {expected_type.__name__} or null, got {type(value).__name__}")


def _require_optional_int(obj: dict, key: str, *, path: str) -> None:
    if key not in obj or obj[key] is None:
        return
    value = obj[key]
    if not isinstance(value, int):
        raise ValueError(f"{path} must be int or null, got {type(value).__name__}")


def _validate_json_value(value: object, *, path: str) -> None:
    if value is None:
        return
    if isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be str, got {type(key).__name__}")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} must be JSON-serializable, got {type(value).__name__}")
