from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from engine.persistence_io import write_json_atomic, write_text_atomic
from engine.provenance import get_provenance, provenance_to_dict
from engine.swallowed_exceptions import _log_swallow


def _run_step(runner) -> tuple[int, dict[str, Any], str | None]:
    try:
        exit_code, outputs = runner()
        return int(exit_code), dict(outputs or {}), None
    except Exception as exc:  # noqa: BLE001  # REASON: release check pipeline should collapse unexpected step failures into a deterministic failed step result
        return 1, {}, f"{type(exc).__name__}: {exc}"


def _run_verify_all(
    repo_root: Path,
    artifacts_dir: Path | None,
    *,
    deterministic: bool = False,
) -> tuple[int, dict[str, Any]]:
    args = argparse.Namespace(
        command="verify-all",
        out_dir=None,
        artifacts=str(artifacts_dir) if artifacts_dir is not None else None,
        no_index=False,
        pytest_args=[],
    )

    payload, exit_code = _run_verify_all_payload(repo_root, args)
    if deterministic and artifacts_dir is not None and isinstance(payload, dict):
        normalized_payload = dict(payload)
        pytest_fast = normalized_payload.get("pytest_fast")
        if isinstance(pytest_fast, dict):
            pytest_fast_norm = dict(pytest_fast)
            if "total" in pytest_fast_norm:
                pytest_fast_norm["total"] = 0.0
            if "top10" in pytest_fast_norm:
                pytest_fast_norm["top10"] = 0.0
            normalized_payload["pytest_fast"] = pytest_fast_norm
        payload = normalized_payload
        write_json_atomic(
            artifacts_dir / "verify_all_summary.json",
            normalized_payload,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )
    outputs = {
        "verify_all_ok": bool(payload.get("summary", {}).get("ok")) if isinstance(payload, dict) else False,
        "verify_all_summary": (artifacts_dir / "verify_all_summary.json").as_posix()
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


def _run_export_build(repo_root: Path, out_dir: Path, *, deterministic: bool = False) -> tuple[int, dict[str, Any]]:
    from tooling.export_bundle import build_bundle

    exit_code, manifest = build_bundle(
        repo_root,
        out_dir,
        include_unused=False,
        fail_on_missing=True,
        deterministic=deterministic,
    )
    outputs: dict[str, Any] = {"bundle_dir": out_dir.as_posix()}
    if manifest is not None:
        outputs["file_count"] = int(getattr(manifest, "file_count", 0) or 0)
        outputs["total_size"] = int(getattr(manifest, "total_size", 0) or 0)
    return int(exit_code), outputs


def _run_debug_bundle(repo_root: Path, out_path: Path, *, deterministic: bool = True) -> tuple[int, dict[str, Any]]:
    from engine.config import load_config
    from engine.game import GameWindow
    from engine.logging_tools import suppress_stdout
    from engine.services import build_replay_service

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
        replay_service = build_replay_service()
        with suppress_stdout():
            window.load_scene(config.start_scene)
        payload = replay_service.build_debug_bundle_payload(
            window=window,
            editor=None,
            deterministic=bool(deterministic),
        )
        write_json_atomic(out_path, payload, indent=2, sort_keys=True, trailing_newline=True)
        return 0, {"debug_bundle_json": out_path.as_posix()}
    except Exception:  # noqa: BLE001  # REASON: debug bundle generation should degrade to a failed step result without masking the expected artifact path
        return 1, {"debug_bundle_json": out_path.as_posix()}
    finally:
        try:
            window.close()
        except Exception:  # noqa: BLE001  # REASON: release debug bundle teardown
            _log_swallow("RELE-001", "mesh_cli/release_check_pipeline.py pass-only blanket swallow")


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


def _normalize_report_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.name


def _normalize_outputs(outputs: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in outputs.items():
        if isinstance(value, str):
            text = value.strip()
            if text:
                candidate = Path(text)
                if candidate.is_absolute():
                    normalized[key] = _normalize_report_path(candidate, repo_root)
                    continue
        normalized[key] = value
    return normalized


def _write_report(path: Path, report: dict[str, Any]) -> None:
    write_json_atomic(path, report, indent=2, sort_keys=True, trailing_newline=True)


def _write_summary(path: Path, report: dict[str, Any], *, failed_step: str | None, exit_code: int) -> None:
    artifacts = report.get("artifacts", {})
    lines = [
        "Mesh Release Check",
        f"Repo: {report.get('repo_root', '')}",
        f"Artifacts: {report.get('artifacts_dir', '')}",
    ]
    prov_data = report.get("provenance")
    if prov_data and isinstance(prov_data, dict):
        from engine.provenance import Provenance
        from engine.provenance import format_provenance_text as _fmt

        lines.append("")
        lines.append(_fmt(Provenance(**prov_data)))
        lines.append("")
    lines.append("Steps:")
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
            lines.append(f"- {key}: {artifacts.get(key)}")

    write_text_atomic(path, "\n".join(lines) + "\n", encoding="utf-8")


def _resolve_path(value: object, repo_root: Path, default: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        return default
    path = Path(raw)
    if not path.is_absolute():
        return repo_root / path
    return path


def build_release_check_report(
    *,
    repo_root: Path,
    artifacts_dir: Path,
    report_path: Path,
    summary_path: Path,
    deterministic: bool,
) -> dict[str, Any]:
    provenance = provenance_to_dict(get_provenance(deterministic=deterministic))
    repo_root_field = "." if deterministic else repo_root.as_posix()
    artifacts_dir_field = _normalize_report_path(artifacts_dir, repo_root) if deterministic else artifacts_dir.as_posix()
    return {
        "schema_version": 1,
        "repo_root": repo_root_field,
        "artifacts_dir": artifacts_dir_field,
        "provenance": provenance,
        "artifacts": {
            "verify_all_summary": _normalize_report_path(artifacts_dir / "verify_all_summary.json", repo_root)
            if deterministic
            else (artifacts_dir / "verify_all_summary.json").as_posix(),
            "asset_audit_json": _normalize_report_path(artifacts_dir / "asset_audit.json", repo_root)
            if deterministic
            else (artifacts_dir / "asset_audit.json").as_posix(),
            "bundle_dir": _normalize_report_path(artifacts_dir / "bundle", repo_root)
            if deterministic
            else (artifacts_dir / "bundle").as_posix(),
            "debug_bundle_json": _normalize_report_path(artifacts_dir / "debug_bundle.json", repo_root)
            if deterministic
            else (artifacts_dir / "debug_bundle.json").as_posix(),
            "release_report_json": _normalize_report_path(report_path, repo_root)
            if deterministic
            else report_path.as_posix(),
            "release_report_txt": _normalize_report_path(summary_path, repo_root)
            if deterministic
            else summary_path.as_posix(),
        },
        "steps": [],
        "summary": {"ok": False, "failed_step": None, "skipped_steps": []},
    }


def os_chdir(path: Path) -> None:
    import os

    os.chdir(path)
