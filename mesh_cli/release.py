"""Release utilities for Mesh CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from engine.persistence_io import write_json_atomic, write_text_atomic


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


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "release_command", None)
    if command == "check":
        return _handle_check(args)
    print("[Mesh][Release] Error: missing release subcommand")
    return 2


def _handle_check(args: argparse.Namespace) -> int:
    repo_root = Path(str(getattr(args, "repo_root", ".") or ".")).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
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
    verify_summary_path = artifacts_dir / "verify_all_summary.json"

    report: dict[str, Any] = {
        "schema_version": 1,
        "repo_root": repo_root.as_posix(),
        "artifacts_dir": artifacts_dir.as_posix(),
        "artifacts": {
            "verify_all_summary": verify_summary_path.as_posix(),
            "asset_audit_json": asset_audit_path.as_posix(),
            "bundle_dir": export_dir.as_posix(),
            "debug_bundle_json": debug_bundle_path.as_posix(),
            "release_report_json": report_path.as_posix(),
            "release_report_txt": summary_path.as_posix(),
        },
        "steps": [],
        "summary": {"ok": False, "failed_step": None, "skipped_steps": []},
    }

    steps = [
        ("verify-all", lambda: _run_verify_all(repo_root, verify_artifacts_dir)),
        ("asset-audit", lambda: _run_assets_audit(repo_root, asset_audit_path)),
        ("export-build", lambda: _run_export_build(repo_root, export_dir)),
        ("debug-bundle", lambda: _run_debug_bundle(repo_root, debug_bundle_path)),
    ]

    exit_code = 0
    failed_step: str | None = None
    skipped: list[str] = []

    for idx, (name, runner) in enumerate(steps):
        step_exit, outputs, error = _run_step(runner)
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
        print("[Mesh][Release] OK")
        return 0
    print(f"[Mesh][Release] FAILED at {failed_step} (exit={exit_code})")
    print(f"[Mesh][Release] Report: {report_path.as_posix()}")
    return exit_code or 1


def _run_step(runner) -> tuple[int, dict[str, Any], str | None]:
    try:
        exit_code, outputs = runner()
        return int(exit_code), dict(outputs or {}), None
    except Exception as exc:  # noqa: BLE001
        return 1, {}, f"{type(exc).__name__}: {exc}"


def _run_verify_all(repo_root: Path, artifacts_dir: Path | None) -> tuple[int, dict[str, Any]]:
    args = argparse.Namespace(
        command="verify-all",
        out_dir=None,
        artifacts=str(artifacts_dir) if artifacts_dir is not None else None,
        no_index=False,
        pytest_args=[],
    )

    payload, exit_code = _run_verify_all_payload(repo_root, args)
    outputs = {
        "verify_all_ok": bool(payload.get("summary", {}).get("ok")) if isinstance(payload, dict) else False,
        "verify_all_summary": (Path(artifacts_dir) / "verify_all_summary.json").as_posix()
        if artifacts_dir is not None
        else None,
    }
    return int(exit_code), outputs


def _run_verify_all_payload(repo_root: Path, args: argparse.Namespace) -> tuple[dict, int]:
    from mesh_cli.verify import _build_verify_all_payload

    cwd = Path.cwd()
    try:
        os_chdir(repo_root)
        payload, exit_code = _build_verify_all_payload(args)
        return payload, int(exit_code)
    finally:
        os_chdir(cwd)


def _run_assets_audit(repo_root: Path, out_path: Path) -> tuple[int, dict[str, Any]]:
    from engine.tooling.assets_audit import run_asset_audit

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=out_path,
        pack_id=None,
        strict=False,
        with_orphans=False,
        with_duplicates=False,
        with_ownership=True,
        warn_duplicates=True,
        fail_missing=True,
        fail_orphans=False,
        fail_duplicates=False,
        write_report=True,
    )
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    outputs = {
        "asset_audit_json": out_path.as_posix(),
        "errors": summary.get("error_count"),
        "warnings": summary.get("warning_count"),
        "orphans": summary.get("orphan_count"),
        "duplicate_groups": summary.get("duplicate_groups"),
    }
    return int(exit_code), outputs


def _run_export_build(repo_root: Path, out_dir: Path) -> tuple[int, dict[str, Any]]:
    from tooling.export_bundle import build_bundle

    exit_code, manifest = build_bundle(repo_root, out_dir, include_unused=False, fail_on_missing=True)
    outputs: dict[str, Any] = {"bundle_dir": out_dir.as_posix()}
    if manifest is not None:
        outputs["file_count"] = int(getattr(manifest, "file_count", 0) or 0)
        outputs["total_size"] = int(getattr(manifest, "total_size", 0) or 0)
    return int(exit_code), outputs


def _run_debug_bundle(repo_root: Path, out_path: Path) -> tuple[int, dict[str, Any]]:
    from engine.config import load_config
    from engine.editor.debug_bundle import build_debug_bundle
    from engine.game import GameWindow
    from engine.logging_tools import suppress_stdout

    config = load_config()
    window = GameWindow(
        width=config.width,
        height=config.height,
        title=config.title,
        fullscreen=config.fullscreen,
        vsync=config.vsync,
        config=config,
        config_path="config.json",
    )

    try:
        with suppress_stdout():
            window.load_scene(config.start_scene)
            bundle = build_debug_bundle(window, None, deterministic=True)
        payload = bundle.to_dict(deterministic=True)
        write_json_atomic(out_path, payload, indent=2, sort_keys=True, trailing_newline=True)
        return 0, {"debug_bundle_json": out_path.as_posix()}
    except Exception:  # noqa: BLE001
        return 1, {"debug_bundle_json": out_path.as_posix()}
    finally:
        try:
            window.close()
        except Exception:
            pass


def _step_record(
    name: str,
    exit_code: int,
    *,
    outputs: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "ok": exit_code == 0,
        "exit_code": int(exit_code),
    }
    if outputs:
        record["outputs"] = dict(outputs)
    if error:
        record["error"] = error
    return record


def _write_report(path: Path, report: dict[str, Any]) -> None:
    write_json_atomic(path, report, indent=2, sort_keys=True, trailing_newline=True)


def _write_summary(path: Path, report: dict[str, Any], *, failed_step: str | None, exit_code: int) -> None:
    artifacts = report.get("artifacts", {})
    lines = [
        "Mesh Release Check",
        f"Repo: {report.get('repo_root', '')}",
        f"Artifacts: {report.get('artifacts_dir', '')}",
        "Steps:",
    ]
    for step in report.get("steps", []):
        name = step.get("name", "")
        status = "OK" if step.get("ok") else "FAILED"
        code = step.get("exit_code", 1)
        lines.append(f"- {name}: {status} (exit={code})")

    if failed_step is None:
        lines.append("Result: OK")
    else:
        lines.append(f"Result: FAILED at {failed_step} (exit={exit_code})")

    if isinstance(artifacts, dict):
        lines.append("Artifacts:")
        for key in sorted(artifacts.keys()):
            value = artifacts.get(key)
            lines.append(f"- {key}: {value}")

    text = "\n".join(lines) + "\n"
    write_text_atomic(path, text, encoding="utf-8")


def _resolve_path(value: object, repo_root: Path, default: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        return default
    path = Path(raw)
    if not path.is_absolute():
        return repo_root / path
    return path


def os_chdir(path: Path) -> None:
    import os

    os.chdir(path)
