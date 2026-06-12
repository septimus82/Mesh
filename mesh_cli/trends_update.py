from __future__ import annotations

import argparse
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_TREND_FILE = "tooling/metrics/weekly_trends.json"
_MAX_ENTRIES = 26


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_path(repo_root: Path, raw: str) -> Path:
    path = Path(str(raw).strip())
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _safe_read_toml(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _as_bool_or_unknown(value: object) -> bool | str:
    if isinstance(value, bool):
        return value
    return "?"


def _as_int_or_unknown(value: object) -> int | str:
    if isinstance(value, bool):
        return "?"
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)
    return "?"


def _as_float_or_unknown(value: object) -> float | str:
    if isinstance(value, bool):
        return "?"
    if isinstance(value, (int, float)):
        return float(value)
    return "?"


def _as_str_or_unknown(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "?"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_package_version(repo_root: Path) -> str:
    payload = _safe_read_toml(repo_root / "pyproject.toml")
    if not isinstance(payload, dict):
        return "?"
    project = payload.get("project")
    if not isinstance(project, dict):
        return "?"
    return _as_str_or_unknown(project.get("version"))


def _read_public_api_semver(repo_root: Path) -> str:
    version_path = repo_root / "engine" / "public_api" / "version.py"
    if not version_path.exists() or not version_path.is_file():
        return "?"
    try:
        text = version_path.read_text(encoding="utf-8")
    except OSError:
        return "?"
    marker = "PUBLIC_API_SEMVER"
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith(marker):
            continue
        if "=" not in line:
            continue
        rhs = line.split("=", 1)[1].strip()
        if rhs.startswith('"') and '"' in rhs[1:]:
            return rhs.split('"', 2)[1].strip() or "?"
        if rhs.startswith("'") and "'" in rhs[1:]:
            return rhs.split("'", 2)[1].strip() or "?"
    return "?"


def _load_verify_report_from_index(artifacts_dir: Path, index_payload: dict[str, Any]) -> dict[str, Any] | None:
    written = index_payload.get("written")
    if not isinstance(written, dict):
        return None
    verify_rel = written.get("verify_report")
    if not isinstance(verify_rel, str) or not verify_rel.strip():
        return None
    candidate = verify_rel.replace("\\", "/").strip()
    if candidate.startswith("artifacts/"):
        candidate = candidate[len("artifacts/") :]
    return _safe_read_json(artifacts_dir / candidate)


def _load_verify_report(artifacts_dir: Path) -> dict[str, Any] | None:
    for index_name in ("artifact_index.json", "index.json"):
        idx = _safe_read_json(artifacts_dir / index_name)
        if idx is None:
            continue
        report = _load_verify_report_from_index(artifacts_dir, idx)
        if report is not None:
            return report
    return _safe_read_json(artifacts_dir / "verify_report.json")


def _extract_mypy_budget_ok(artifacts_dir: Path) -> bool | str:
    summary = _safe_read_json(artifacts_dir / "verify_all_summary.json")
    if not isinstance(summary, dict):
        return "?"
    steps = summary.get("steps")
    if not isinstance(steps, list):
        return "?"
    for row in steps:
        if not isinstance(row, dict):
            continue
        if str(row.get("name", "")).strip() != "mypy-gate":
            continue
        return _as_bool_or_unknown(row.get("ok"))
    return "?"


def _extract_exception_budget_ok(artifacts_dir: Path, verify_report: dict[str, Any] | None) -> bool | str:
    if isinstance(verify_report, dict):
        budgets = verify_report.get("budgets")
        if isinstance(budgets, dict):
            exception_budget = budgets.get("exception_budget")
            if isinstance(exception_budget, dict):
                value = _as_bool_or_unknown(exception_budget.get("ok"))
                if isinstance(value, bool):
                    return value
    exception_budget_payload = _safe_read_json(artifacts_dir / "exception_budget.json")
    if isinstance(exception_budget_payload, dict):
        return _as_bool_or_unknown(exception_budget_payload.get("ok"))
    return "?"


def _extract_swallowed_total(artifacts_dir: Path, verify_report: dict[str, Any] | None) -> int | str:
    if isinstance(verify_report, dict):
        runtime_diagnostics = verify_report.get("runtime_diagnostics")
        if isinstance(runtime_diagnostics, dict):
            swallowed = runtime_diagnostics.get("swallowed_exceptions")
            if isinstance(swallowed, dict):
                value = _as_int_or_unknown(swallowed.get("total"))
                if isinstance(value, int):
                    return value
    payload = _safe_read_json(artifacts_dir / "swallowed_exceptions.json")
    if isinstance(payload, dict):
        return _as_int_or_unknown(payload.get("total"))
    return "?"


def _extract_shadow_backend_selected(artifacts_dir: Path, verify_report: dict[str, Any] | None) -> str:
    if isinstance(verify_report, dict):
        runtime_diagnostics = verify_report.get("runtime_diagnostics")
        if isinstance(runtime_diagnostics, dict):
            shadow = runtime_diagnostics.get("shadow_backend")
            if isinstance(shadow, dict):
                value = _as_str_or_unknown(shadow.get("selected"))
                if value != "?":
                    return value
    payload = _safe_read_json(artifacts_dir / "shadow_backend.json")
    if isinstance(payload, dict):
        return _as_str_or_unknown(payload.get("selected"))
    return "?"


def _extract_verify_ok(artifacts_dir: Path, verify_report: dict[str, Any] | None) -> bool | str:
    if isinstance(verify_report, dict):
        verify_summary = verify_report.get("verify_summary")
        if isinstance(verify_summary, dict):
            value = _as_bool_or_unknown(verify_summary.get("ok"))
            if isinstance(value, bool):
                return value
    summary = _safe_read_json(artifacts_dir / "verify_all_summary.json")
    if isinstance(summary, dict):
        return _as_bool_or_unknown(summary.get("ok"))
    return "?"


def _extract_verify_total_ms(artifacts_dir: Path, verify_report: dict[str, Any] | None) -> int | str:
    if isinstance(verify_report, dict):
        timing = verify_report.get("timing")
        if isinstance(timing, dict):
            value = _as_int_or_unknown(timing.get("total_ms"))
            if isinstance(value, int):
                return value
    durations = _safe_read_json(artifacts_dir / "verify_step_durations.json")
    if isinstance(durations, dict):
        return _as_int_or_unknown(durations.get("total_ms"))
    return "?"


def _extract_overlay_metric(metric: object) -> dict[str, int | float | str]:
    if not isinstance(metric, dict):
        return {"count": "?", "total_ms": "?", "max_ms": "?", "avg_ms": "?"}
    count = _as_int_or_unknown(metric.get("count"))
    total_ms = _as_float_or_unknown(metric.get("total_ms"))
    max_ms = _as_float_or_unknown(metric.get("max_ms"))
    avg_ms: float | str = "?"
    if isinstance(count, int) and count >= 0 and isinstance(total_ms, float):
        avg_ms = 0.0 if count == 0 else round(total_ms / float(count), 3)
    total_ms_out: float | str = round(total_ms, 3) if isinstance(total_ms, float) else total_ms
    max_ms_out: float | str = round(max_ms, 3) if isinstance(max_ms, float) else max_ms
    return {
        "count": count,
        "total_ms": total_ms_out,
        "max_ms": max_ms_out,
        "avg_ms": avg_ms,
    }


def _extract_overlay_perf(artifacts_dir: Path) -> dict[str, dict[str, int | float | str]] | None:
    payload = _safe_read_json(artifacts_dir / "overlay_perf.json")
    if not isinstance(payload, dict):
        return None
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return None
    return {
        "providers_total": _extract_overlay_metric(metrics.get("providers_total")),
        "command_palette_provider": _extract_overlay_metric(metrics.get("command_palette_provider")),
    }


def _extract_pytest_fast_budget_metrics(artifacts_dir: Path) -> tuple[int | None, int | None]:
    payload = _safe_read_json(artifacts_dir / "verify_step_budget_check.json")
    if not isinstance(payload, dict):
        return None, None
    checked_steps = payload.get("checked_steps")
    if not isinstance(checked_steps, list):
        return None, None
    for row in checked_steps:
        if not isinstance(row, dict):
            continue
        if str(row.get("name", "")).strip() != "pytest-fast":
            continue
        current_raw = row.get("current_ms")
        threshold_raw = row.get("threshold_ms")
        current_ms = int(current_raw) if isinstance(current_raw, (int, float)) else None
        threshold_ms = int(threshold_raw) if isinstance(threshold_raw, (int, float)) else None
        return current_ms, threshold_ms
    return None, None


def _build_entry(repo_root: Path, artifacts_dir: Path) -> dict[str, Any]:
    verify_report = _load_verify_report(artifacts_dir)
    pytest_fast_ms, pytest_fast_threshold_ms = _extract_pytest_fast_budget_metrics(artifacts_dir)
    return {
        "timestamp_utc": _utc_now_iso(),
        "package_version": _read_package_version(repo_root),
        "public_api_semver": _read_public_api_semver(repo_root),
        "verify_ok": _extract_verify_ok(artifacts_dir, verify_report),
        "verify_total_ms": _extract_verify_total_ms(artifacts_dir, verify_report),
        "mypy_budget_ok": _extract_mypy_budget_ok(artifacts_dir),
        "exception_budget_ok": _extract_exception_budget_ok(artifacts_dir, verify_report),
        "swallowed_total": _extract_swallowed_total(artifacts_dir, verify_report),
        "shadow_backend_selected": _extract_shadow_backend_selected(artifacts_dir, verify_report),
        "pytest_fast_ms": pytest_fast_ms,
        "pytest_fast_threshold_ms": pytest_fast_threshold_ms,
        "overlay_perf": _extract_overlay_perf(artifacts_dir),
    }


def _read_trend_entries(path: Path) -> list[dict[str, Any]]:
    payload = _safe_read_json(path)
    if not isinstance(payload, dict):
        return []
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        return []
    entries: list[dict[str, Any]] = []
    for row in raw_entries:
        if isinstance(row, dict):
            entries.append(dict(row))
    return entries


def _write_trends(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "entries": entries,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _handle_trends_update(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_module()
    artifacts_raw = str(getattr(args, "artifacts", "") or "").strip()
    trend_raw = str(getattr(args, "trend_file", _DEFAULT_TREND_FILE) or _DEFAULT_TREND_FILE).strip()

    artifacts_dir = _resolve_path(repo_root, artifacts_raw)
    if not artifacts_dir.exists() or not artifacts_dir.is_dir():
        print(f"error: artifacts directory not found: {artifacts_dir.as_posix()}")
        return 2

    trend_path = _resolve_path(repo_root, trend_raw)
    try:
        entries = _read_trend_entries(trend_path)
        entries.append(_build_entry(repo_root, artifacts_dir))
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        _write_trends(trend_path, entries)
    except Exception as exc:
        print(f"[Mesh][Trends] warning: update failed: {exc}")
        return 0

    print(f"[Mesh][Trends] updated {trend_path.as_posix()} entries={len(entries)}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "trends-update",
        help="Append weekly health trend metrics from artifacts",
    )
    parser.add_argument("--artifacts", required=True, help="Artifacts directory")
    parser.add_argument("--trend-file", default=_DEFAULT_TREND_FILE, help=f"Trend output file (default: {_DEFAULT_TREND_FILE})")
    parser.set_defaults(func=_handle_trends_update)


def handle(args: argparse.Namespace) -> int:
    return _handle_trends_update(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh trends-update")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--trend-file", default=_DEFAULT_TREND_FILE)
    args = parser.parse_args(argv)
    return _handle_trends_update(args)
