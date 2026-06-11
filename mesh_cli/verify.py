from __future__ import annotations

import argparse
import ast
from engine.swallowed_exceptions import _log_swallow
import json
import os
from pathlib import Path
from typing import Any, Callable, TypedDict

from mesh_cli.verify_steps import STEP_ORDER as VERIFY_ALL_STEPS
from mesh_cli.verify_steps import VerifyStepContext, run_verify_steps
from mesh_cli.shipping_policy import build_verify_summary_key_artifacts

class _VerifyStepDurationRow(TypedDict):
    name: str
    ok: bool
    ms: int


class _VerifyStepBudgetCheckRow(TypedDict):
    name: str
    budget_ms: int
    tolerance_ms: int
    ratio_limit: float
    threshold_ms: int
    current_ms: int
    median_ms: int | None
    effective_ms: int
    delta_ms: int
    ok: bool


_VERIFY_STEP_BUDGET_SCHEMA_VERSION = 2
_VERIFY_STEP_BUDGET_TOP_N = 5
_VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS = 50
_VERIFY_STEP_BUDGET_DEFAULT_RATIO_LIMIT = 1.25
_VERIFY_STEP_BUDGET_NULL_MEDIAN_MARGIN_MS: dict[str, int] = {
    "player-package-gate": 700,
    "verify-demo": 250,
    "web-smoke": 600,
}
_VERIFY_LOCAL_STEP_EXCEPTIONS: tuple[type[Exception], ...] = (
    AttributeError,
    FileNotFoundError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)
_VERIFY_STEP_BUDGET_RATIO_LIMIT_OVERRIDES: dict[str, float] = {
    "mypy-gate": 1.35,
}
_VERIFY_STEP_BUDGET_ENFORCE_ENV = "MESH_VERIFY_BUDGET_ENFORCE"


def _verify_all_invalid_args() -> int:
    # Kept for backward call sites; `_handle_verify_all` emits schema-complete output.
    import sys

    from engine.persistence_io import dumps_json_deterministic

    payload = {"ok": False, "steps": [], "artifacts": {"dir": None, "written": {}}}
    sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
    return 2


def _verify_step_budget_enforced() -> bool:
    return os.getenv(_VERIFY_STEP_BUDGET_ENFORCE_ENV, "0") == "1"


def _apply_verify_step_budget_exit_state(
    *,
    overall_ok: bool,
    exit_code: int,
    budget_code: int,
) -> tuple[bool, int]:
    if int(budget_code) == 0:
        return bool(overall_ok), int(exit_code)
    if not _verify_step_budget_enforced():
        return bool(overall_ok), int(exit_code)
    next_exit_code = int(exit_code)
    if next_exit_code == 0:
        next_exit_code = 2 if int(budget_code) == 2 else 1
    return False, next_exit_code


def _artifact_base_dir(repo_root, dir_arg: str):
    from pathlib import Path

    path = Path(dir_arg)
    return path if path.is_absolute() else (Path(repo_root) / path)


def _missing_required_verify_metric_artifacts(artifacts_dir: Path) -> list[str]:
    required = (
        artifacts_dir / "verify_step_durations.json",
        artifacts_dir / "verify_step_budget_check.json",
    )
    return sorted(path.name for path in required if not path.is_file())


def _write_verify_all_summary_artifact(artifact_dir, payload: dict) -> None:
    from pathlib import Path

    from engine.persistence_io import write_json_atomic

    write_json_atomic(
        Path(artifact_dir) / "verify_all_summary.json",
        payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )


def _build_verify_summary_payload(
    *,
    overall_ok: bool,
    steps: list[dict[str, object]],
    artifacts_written: dict[str, str | None],
) -> dict[str, object]:
    def _path_from_written(key: str) -> str | None:
        value = artifacts_written.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    step_rows: list[dict[str, object]] = []
    for row in steps:
        name = str(row.get("name", "")).strip()
        ok_raw = row.get("ok")
        ok = bool(ok_raw) if isinstance(ok_raw, bool) else False
        code_raw = row.get("code")
        error_text = str(row.get("error", "") or "")
        skipped = (isinstance(code_raw, (int, float)) and int(code_raw) == 2) or error_text.startswith("skipped:")
        item: dict[str, object] = {
            "name": name,
            "ok": ok,
            "skipped": bool(skipped),
        }
        artifact_raw = row.get("artifact")
        if isinstance(artifact_raw, str) and artifact_raw.strip():
            item["artifact"] = artifact_raw.strip()
        step_rows.append(item)

    key_artifacts = build_verify_summary_key_artifacts(
        {
            "player_package_manifest": _path_from_written("player_package_manifest"),
            "player_package_check": _path_from_written("player_package_check"),
            "player_package_runtime_smoke": _path_from_written("player_package_runtime_smoke"),
            "player_package_runtime_diagnostics_snapshot": _path_from_written("player_package_runtime_diagnostics_snapshot"),
            "web_smoke": _path_from_written("web_smoke"),
            "perf_compare": _path_from_written("perf_compare"),
            "swallow_scan": _path_from_written("swallow_scan"),
            "runtime_smoke": _path_from_written("runtime_smoke"),
            "runtime_diagnostics_snapshot": _path_from_written("runtime_diagnostics_snapshot"),
        }
    )

    diagnostics: dict[str, str | None] = {
        "verify_report": _path_from_written("verify_report"),
        "swallowed_exceptions": _path_from_written("swallowed_exceptions"),
        "shadow_backend": _path_from_written("shadow_backend"),
    }

    return {
        "schema_version": 1,
        "ok": bool(overall_ok),
        "steps": step_rows,
        "key_artifacts": key_artifacts,
        "diagnostics": diagnostics,
    }


def _build_verify_summary_text(payload: dict[str, object]) -> str:
    lines: list[str] = []
    ok_value = payload.get("ok")
    ok_text = "true" if (isinstance(ok_value, bool) and ok_value) else "false"
    lines.append(f"VERIFY_SUMMARY_OK: {ok_text}")

    steps_raw = payload.get("steps")
    if isinstance(steps_raw, list):
        for row in steps_raw:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            row_ok = bool(row.get("ok")) if isinstance(row.get("ok"), bool) else False
            row_skipped = bool(row.get("skipped")) if isinstance(row.get("skipped"), bool) else False
            artifact_raw = row.get("artifact")
            artifact = artifact_raw.strip() if isinstance(artifact_raw, str) and artifact_raw.strip() else "-"
            lines.append(
                f"VERIFY_STEP: {name} ok={'true' if row_ok else 'false'} "
                f"skipped={'true' if row_skipped else 'false'} artifact={artifact}"
            )

    key_artifacts_raw = payload.get("key_artifacts")
    key_artifacts: dict[str, str | None] = key_artifacts_raw if isinstance(key_artifacts_raw, dict) else {}
    for name in key_artifacts:
        value = key_artifacts.get(name)
        rendered = value if isinstance(value, str) and value.strip() else "-"
        lines.append(f"VERIFY_ARTIFACT: {name} {rendered}")

    diagnostics_raw = payload.get("diagnostics")
    diagnostics: dict[str, str | None] = diagnostics_raw if isinstance(diagnostics_raw, dict) else {}
    for name in ("verify_report", "swallowed_exceptions", "shadow_backend"):
        value = diagnostics.get(name)
        rendered = value if isinstance(value, str) and value.strip() else "-"
        lines.append(f"VERIFY_DIAGNOSTIC: {name} {rendered}")

    return "\n".join(lines) + "\n"


def _write_verify_summary_artifacts(artifact_dir: Path, payload: dict[str, object]) -> None:
    from engine.persistence_io import write_json_atomic, write_text_atomic

    write_json_atomic(
        artifact_dir / "verify_summary.json",
        payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    write_text_atomic(
        artifact_dir / "verify_summary.txt",
        _build_verify_summary_text(payload),
        encoding="utf-8",
    )


def _build_verify_step_durations_payload(
    *,
    expected_steps: list[str],
    rows: list[dict[str, object]],
) -> dict[str, object]:
    row_by_name: dict[str, dict[str, object]] = {}
    for row in rows:
        name = row.get("name")
        if isinstance(name, str) and name not in row_by_name:
            row_by_name[name] = row

    ordered_steps: list[_VerifyStepDurationRow] = []
    for name in expected_steps:
        row_data = row_by_name.get(name)
        if row_data is None:
            ordered_steps.append({"name": name, "ok": True, "ms": 0})
            continue
        ms_raw = row_data.get("ms")
        ms = int(ms_raw) if isinstance(ms_raw, (int, float)) else 0
        ok_raw = row_data.get("ok")
        ok = bool(ok_raw) if isinstance(ok_raw, bool) else False
        ordered_steps.append({"name": name, "ok": ok, "ms": max(0, ms)})

    total_ms = int(sum(step["ms"] for step in ordered_steps))
    return {
        "schema_version": 1,
        "total_ms": total_ms,
        "steps": ordered_steps,
    }


def _read_verify_step_durations_payload(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("verify_step_durations payload must be an object")
    return data


def _next_verify_step_history_path(artifacts_dir: Path) -> Path:
    history_dir = artifacts_dir / "verify_step_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    prefix = "verify_step_durations_"
    suffix = ".json"
    max_index = 0
    for path in history_dir.glob(f"{prefix}*{suffix}"):
        stem = path.stem
        if not stem.startswith(prefix):
            continue
        index_text = stem[len(prefix) :]
        try:
            index = int(index_text)
        except ValueError:
            continue
        max_index = max(max_index, index)
    return history_dir / f"{prefix}{max_index + 1:04d}{suffix}"


def _archive_verify_step_durations_artifact(artifacts_dir: Path) -> Path | None:
    source = artifacts_dir / "verify_step_durations.json"
    if not source.is_file():
        return None
    try:
        payload = _read_verify_step_durations_payload(source)
    except (OSError, json.JSONDecodeError, ValueError):
        _log_swallow("VFYC-023", "verify-step-durations history archive fallback", once=False)
        return None

    from engine.persistence_io import write_json_atomic

    target = _next_verify_step_history_path(artifacts_dir)
    write_json_atomic(
        target,
        payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    return target


def _extract_step_duration_ms(step_durations_payload: dict[str, object]) -> dict[str, int]:
    steps_raw = step_durations_payload.get("steps")
    if not isinstance(steps_raw, list):
        raise ValueError("verify_step_durations.steps must be a list")
    result: dict[str, int] = {}
    for row in steps_raw:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        ms_raw = row.get("ms")
        if isinstance(name, str) and isinstance(ms_raw, (int, float)):
            result[name] = max(0, int(ms_raw))
    return result


def _build_verify_step_budget_baseline_payload(
    step_durations_payload: dict[str, object],
    *,
    top_n: int = _VERIFY_STEP_BUDGET_TOP_N,
    tolerance_ms: int = _VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS,
) -> dict[str, object]:
    step_ms = _extract_step_duration_ms(step_durations_payload)
    ranked = sorted(step_ms.items(), key=lambda item: (-int(item[1]), item[0]))
    selected = ranked[: max(0, int(top_n))]
    budgets_ms = {name: int(ms) for name, ms in sorted(selected)}
    ratio_limits = {
        name: float(_VERIFY_STEP_BUDGET_RATIO_LIMIT_OVERRIDES.get(name, _VERIFY_STEP_BUDGET_DEFAULT_RATIO_LIMIT))
        for name in sorted(budgets_ms)
    }
    return {
        "schema_version": _VERIFY_STEP_BUDGET_SCHEMA_VERSION,
        "budgets_ms": budgets_ms,
        "ratio_limits": ratio_limits,
        "tolerance_ms": max(0, int(tolerance_ms)),
    }


def _write_verify_step_budget_baseline(
    baseline_path: Path,
    step_durations_payload: dict[str, object],
    *,
    top_n: int = _VERIFY_STEP_BUDGET_TOP_N,
    tolerance_ms: int = _VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS,
) -> dict[str, object]:
    from engine.persistence_io import write_json_atomic

    payload = _build_verify_step_budget_baseline_payload(
        step_durations_payload,
        top_n=top_n,
        tolerance_ms=tolerance_ms,
    )
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        baseline_path,
        payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    return payload


def _write_verify_step_budget_baseline_from_artifacts(
    *,
    repo_root: Path,
    artifacts_dir: Path,
) -> tuple[Path, dict[str, object]]:
    durations_path = artifacts_dir / "verify_step_durations.json"
    baseline_path = repo_root / "tooling" / "metrics" / "verify_step_budget.json"
    payload = _read_verify_step_durations_payload(durations_path)
    baseline_payload = _write_verify_step_budget_baseline(baseline_path, payload)
    return baseline_path, baseline_payload


def _verify_step_budget_update_command(artifacts_dir: Path | None) -> str:
    artifacts_rel = "artifacts"
    if artifacts_dir is not None:
        artifacts_rel = Path(artifacts_dir).as_posix()
    return (
        "python -c \"from pathlib import Path; import os; import mesh_cli.verify as m; "
        f"artifacts=Path(os.getenv('MESH_ARTIFACTS_DIR', r'{artifacts_rel}')); "
        "repo=Path(m.__file__).resolve().parent.parent; "
        "if not artifacts.is_absolute(): artifacts = repo / artifacts; "
        "target,_=m._write_verify_step_budget_baseline_from_artifacts(repo_root=repo, artifacts_dir=artifacts); "
        "print(f'updated {target.as_posix()} from {artifacts.as_posix()}/verify_step_durations.json (run from any cwd)')\""
    )


def _build_verify_step_budget_check_payload(
    *,
    ok: bool,
    tolerance_ms: int,
    checked_steps: list[_VerifyStepBudgetCheckRow],
    candidates_used: list[str],
) -> dict[str, object]:
    offenders = [
        {
            "name": row["name"],
            "delta_ms": int(row["delta_ms"]),
            "effective_ms": int(row["effective_ms"]),
        }
        for row in sorted(
            (r for r in checked_steps if not bool(r["ok"])),
            key=lambda row: (-int(row["delta_ms"]), row["name"]),
        )
    ]
    ordered_checked = sorted(checked_steps, key=lambda row: row["name"])
    return {
        "schema_version": _VERIFY_STEP_BUDGET_SCHEMA_VERSION,
        "ok": bool(ok),
        "tolerance_ms": max(0, int(tolerance_ms)),
        "candidates_used": sorted(candidates_used),
        "checked_steps": ordered_checked,
        "offenders": offenders,
    }


def _is_mypy_budget_offender(verify_step_budget_payload: dict[str, object]) -> bool:
    checked_steps = verify_step_budget_payload.get("checked_steps", [])
    if not isinstance(checked_steps, list):
        return False
    for row in checked_steps:
        if not isinstance(row, dict):
            continue
        if str(row.get("name", "")).strip() != "mypy-gate":
            continue
        if bool(row.get("ok", True)):
            continue
        return True
    return False


def _find_budget_row(
    verify_step_budget_payload: dict[str, object],
    *,
    step_name: str,
) -> dict[str, object] | None:
    checked_steps = verify_step_budget_payload.get("checked_steps", [])
    if not isinstance(checked_steps, list):
        return None
    for row in checked_steps:
        if not isinstance(row, dict):
            continue
        if str(row.get("name", "")).strip() != step_name:
            continue
        return row
    return None


def _is_pytest_fast_budget_offender(verify_step_budget_payload: dict[str, object]) -> bool:
    row = _find_budget_row(verify_step_budget_payload, step_name="pytest-fast")
    if row is None:
        return False
    return not bool(row.get("ok", True))


def _load_mypy_gate_run_diagnostics() -> dict[str, object]:
    try:
        from tooling import mypy_gate

        getter = getattr(mypy_gate, "get_last_run_diagnostics", None)
        if callable(getter):
            payload = getter()
            if isinstance(payload, dict):
                return payload
    except Exception:  # noqa: BLE001  # REASON: verify step isolation
        _log_swallow("VFYC-001", "blanket exception fallback", once=False)
        pass
    return {}


def _build_mypy_budget_diagnostic_payload(
    *,
    mypy_diagnostics: dict[str, object],
    verify_step_budget_payload: dict[str, object],
) -> dict[str, object]:
    row: dict[str, object] | None = None
    checked_steps = verify_step_budget_payload.get("checked_steps", [])
    if isinstance(checked_steps, list):
        for candidate in checked_steps:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("name", "")).strip() == "mypy-gate":
                row = candidate
                break
    cache_payload = mypy_diagnostics.get("cache")
    cache_info = cache_payload if isinstance(cache_payload, dict) else {}
    command_argv_raw = mypy_diagnostics.get("command_argv")
    command_argv = [str(part) for part in command_argv_raw] if isinstance(command_argv_raw, list) else []
    return {
        "schema_version": 1,
        "step": "mypy-gate",
        "command_argv": command_argv,
        "command_line": str(mypy_diagnostics.get("command_line", "")),
        "wall_time_seconds": mypy_diagnostics.get("wall_time_seconds"),
        "files_checked": mypy_diagnostics.get("files_checked"),
        "summary": mypy_diagnostics.get("summary"),
        "cache": {
            "enabled": bool(cache_info.get("enabled", False)),
            "incremental": bool(cache_info.get("incremental", False)),
            "cache_dir": str(cache_info.get("cache_dir", "")),
        },
        "python_version": str(mypy_diagnostics.get("python_version", "")),
        "budget_row": row,
    }


def _format_mypy_budget_diagnostic_text(payload: dict[str, object]) -> str:
    cache_payload = payload.get("cache")
    cache_info = cache_payload if isinstance(cache_payload, dict) else {}
    budget_row_payload = payload.get("budget_row")
    budget_row = budget_row_payload if isinstance(budget_row_payload, dict) else {}
    lines = [
        "mypy budget diagnostic",
        f"command: {str(payload.get('command_line', ''))}",
        f"wall_time_seconds: {payload.get('wall_time_seconds')}",
        f"files_checked: {payload.get('files_checked')}",
        f"summary: {payload.get('summary')}",
        (
            "cache: enabled="
            f"{cache_info.get('enabled')} incremental={cache_info.get('incremental')} "
            f"dir={cache_info.get('cache_dir')}"
        ),
        f"python_version: {payload.get('python_version')}",
        (
            "budget: threshold_ms="
            f"{budget_row.get('threshold_ms')} current_ms={budget_row.get('current_ms')} "
            f"effective_ms={budget_row.get('effective_ms')} delta_ms={budget_row.get('delta_ms')}"
        ),
    ]
    return "\n".join(lines) + "\n"


def _truncate_diagnostic_text(text: object, *, max_chars: int = 120000) -> str:
    value = str(text or "")
    if len(value) <= int(max_chars):
        return value
    keep = max(0, int(max_chars))
    dropped = len(value) - keep
    return f"... [truncated {dropped} chars] ...\n{value[-keep:]}"


def _build_verify_pytest_fast_command_argv(*, repo_root: Path) -> list[str]:
    import sys

    durations_path = repo_root / ".mesh" / "metrics" / "pytest_durations_fast.json"
    return [
        sys.executable,
        "-m",
        "tooling.pytest_fast",
        "--write-durations",
        str(durations_path),
    ]


def _run_pytest_fast_budget_diagnostic(*, repo_root: Path) -> tuple[int, str, str]:
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "fast",
        "--durations=20",
    ]
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return int(result.returncode), str(result.stdout or ""), str(result.stderr or "")


def _build_pytest_fast_budget_diagnostic_payload(
    *,
    verify_step_budget_payload: dict[str, object],
    normal_command_argv: list[str],
    diagnostic_command_argv: list[str],
    diagnostic_returncode: int,
    diagnostic_stdout: str,
    diagnostic_stderr: str,
) -> dict[str, object]:
    import platform

    row = _find_budget_row(verify_step_budget_payload, step_name="pytest-fast") or {}
    current_ms_raw = row.get("current_ms", 0)
    threshold_ms_raw = row.get("threshold_ms", 0)
    current_ms = int(current_ms_raw) if isinstance(current_ms_raw, (int, float)) else 0
    threshold_ms = int(threshold_ms_raw) if isinstance(threshold_ms_raw, (int, float)) else 0
    wall_time_seconds = round(max(0, current_ms) / 1000.0, 3)
    return {
        "schema_version": 1,
        "step": "pytest-fast",
        "command_argv": [str(part) for part in normal_command_argv],
        "command_line": " ".join(str(part) for part in normal_command_argv),
        "wall_time_seconds": wall_time_seconds,
        "threshold_ms": threshold_ms,
        "current_ms": current_ms,
        "python_version": str(platform.python_version()),
        "diagnostic_command_argv": [str(part) for part in diagnostic_command_argv],
        "diagnostic_command_line": " ".join(str(part) for part in diagnostic_command_argv),
        "diagnostic_returncode": int(diagnostic_returncode),
        "diagnostic_stdout_tail": _truncate_diagnostic_text(diagnostic_stdout),
        "diagnostic_stderr_tail": _truncate_diagnostic_text(diagnostic_stderr),
        "budget_row": row,
    }


def _format_pytest_fast_budget_diagnostic_text(payload: dict[str, object]) -> str:
    lines = [
        "pytest-fast budget diagnostic",
        f"command: {payload.get('command_line')}",
        f"wall_time_seconds: {payload.get('wall_time_seconds')}",
        f"threshold_ms: {payload.get('threshold_ms')}",
        f"current_ms: {payload.get('current_ms')}",
        f"python_version: {payload.get('python_version')}",
        f"diagnostic_command: {payload.get('diagnostic_command_line')}",
        f"diagnostic_returncode: {payload.get('diagnostic_returncode')}",
        "",
        "diagnostic stdout (tail):",
        str(payload.get("diagnostic_stdout_tail", "")),
        "",
        "diagnostic stderr (tail):",
        str(payload.get("diagnostic_stderr_tail", "")),
    ]
    return "\n".join(lines) + "\n"


def _write_pytest_fast_budget_diagnostic_artifacts(
    *,
    repo_root: Path,
    artifacts_dir: Path,
    verify_step_budget_payload: dict[str, object],
) -> None:
    from engine.persistence_io import write_json_atomic, write_text_atomic

    normal_command_argv = _build_verify_pytest_fast_command_argv(repo_root=repo_root)
    diagnostic_command_argv = [
        normal_command_argv[0],
        "-m",
        "pytest",
        "-q",
        "-m",
        "fast",
        "--durations=20",
    ]
    diag_code, diag_stdout, diag_stderr = _run_pytest_fast_budget_diagnostic(repo_root=repo_root)
    diag_payload = _build_pytest_fast_budget_diagnostic_payload(
        verify_step_budget_payload=verify_step_budget_payload,
        normal_command_argv=normal_command_argv,
        diagnostic_command_argv=diagnostic_command_argv,
        diagnostic_returncode=diag_code,
        diagnostic_stdout=diag_stdout,
        diagnostic_stderr=diag_stderr,
    )
    diag_text = _format_pytest_fast_budget_diagnostic_text(diag_payload)
    write_json_atomic(
        artifacts_dir / "pytest_fast_budget_diagnostic.json",
        diag_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    write_text_atomic(
        artifacts_dir / "pytest_fast_budget_diagnostic.txt",
        diag_text,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Authoring-trace budget guard (default-off, growth-only ratchet)
# ---------------------------------------------------------------------------

_AUTHORING_TRACE_BUDGET_SCHEMA_VERSION = 1
_AUTHORING_TRACE_BUDGET_DEFAULT_TOLERANCE_MS = 5


class _AuthoringTraceBudgetCheckRow(TypedDict):
    name: str
    budget_ms: int
    tolerance_ms: int
    current_ms: int
    delta_ms: int
    ok: bool


def _authoring_trace_budget_update_command(artifacts_dir: Path | None) -> str:
    """Return a deterministic Windows-safe one-liner that regenerates the baseline."""
    artifacts_rel = "artifacts"
    if artifacts_dir is not None:
        artifacts_rel = Path(artifacts_dir).as_posix()
    return (
        "python -c \"from pathlib import Path; import json, mesh_cli.verify as m; "
        f"src=Path(r'{artifacts_rel}') / 'authoring_trace.json'; "
        "repo=Path(m.__file__).resolve().parent.parent; "
        "src=src if src.is_absolute() else repo / src; "
        "data=json.loads(src.read_text(encoding='utf-8')); "
        "target=repo / 'tooling' / 'metrics' / 'authoring_trace_budget.json'; "
        "budget={'schema_version':1,'tolerance_ms':5,'total_ms_budget':int(data.get('total_ms',0) or 0),"
        "'functions':{f['name']:int(f.get('total_ms',0) or 0) for f in data.get('functions',[])}};  "
        "target.parent.mkdir(parents=True,exist_ok=True); "
        "target.write_text(json.dumps(budget,indent=2,sort_keys=True)+'\\n',encoding='utf-8'); "
        "print(f'updated {target.as_posix()} from {src.as_posix()}')\""
    )


def _build_authoring_trace_budget_check_payload(
    *,
    ok: bool,
    tolerance_ms: int,
    total_budget_ms: int | None,
    total_current_ms: int | None,
    checked_functions: list[_AuthoringTraceBudgetCheckRow],
) -> dict[str, object]:
    offenders = [
        {
            "name": row["name"],
            "delta_ms": int(row["delta_ms"]),
            "current_ms": int(row["current_ms"]),
        }
        for row in sorted(
            (r for r in checked_functions if not bool(r["ok"])),
            key=lambda row: (-int(row["delta_ms"]), row["name"]),
        )
    ]
    ordered_checked = sorted(checked_functions, key=lambda row: row["name"])
    return {
        "schema_version": _AUTHORING_TRACE_BUDGET_SCHEMA_VERSION,
        "ok": bool(ok),
        "tolerance_ms": max(0, int(tolerance_ms)),
        "total_budget_ms": total_budget_ms,
        "total_current_ms": total_current_ms,
        "checked_functions": ordered_checked,
        "offenders": offenders,
    }


def _evaluate_authoring_trace_budget_guard(
    *,
    authoring_trace_payload: dict[str, object],
    baseline_path: Path,
    update_command: str,
) -> tuple[int, str, dict[str, object]]:
    """Compare authoring-trace totals against baseline budgets.

    Returns ``(code, error_message, check_payload)`` matching the step-budget
    guard convention.  *code* is ``0`` = pass, ``2`` = budget exceeded,
    ``1`` = structural error.  Default-off: callers should only invoke this
    when ``MESH_AUTHORING_TRACE_ARTIFACT`` is set AND the trace artifact
    indicates ``enabled=true``.
    """
    # ---- guard: baseline may not exist yet --------------------------------
    if not baseline_path.exists():
        payload = _build_authoring_trace_budget_check_payload(
            ok=True,
            tolerance_ms=_AUTHORING_TRACE_BUDGET_DEFAULT_TOLERANCE_MS,
            total_budget_ms=None,
            total_current_ms=None,
            checked_functions=[],
        )
        return 0, "", payload

    # ---- load baseline ----------------------------------------------------
    try:
        baseline_raw = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log_swallow("VFYC-002", "authoring-trace-budget baseline parse fallback", once=False)
        payload = _build_authoring_trace_budget_check_payload(
            ok=False,
            tolerance_ms=_AUTHORING_TRACE_BUDGET_DEFAULT_TOLERANCE_MS,
            total_budget_ms=None,
            total_current_ms=None,
            checked_functions=[],
        )
        return 1, f"authoring-trace-budget baseline parse failed: {type(exc).__name__}: {exc}", payload

    if not isinstance(baseline_raw, dict):
        payload = _build_authoring_trace_budget_check_payload(
            ok=False,
            tolerance_ms=_AUTHORING_TRACE_BUDGET_DEFAULT_TOLERANCE_MS,
            total_budget_ms=None,
            total_current_ms=None,
            checked_functions=[],
        )
        return 1, "authoring-trace-budget baseline must be an object", payload

    tolerance_raw = baseline_raw.get("tolerance_ms")
    tolerance_ms = (
        max(0, int(tolerance_raw))
        if isinstance(tolerance_raw, (int, float))
        else _AUTHORING_TRACE_BUDGET_DEFAULT_TOLERANCE_MS
    )

    # ---- extract current totals from the trace payload --------------------
    functions_list = authoring_trace_payload.get("functions", [])
    if not isinstance(functions_list, list):
        functions_list = []
    current_by_name: dict[str, int] = {}
    for entry in functions_list:
        if isinstance(entry, dict) and "name" in entry:
            current_by_name[str(entry["name"])] = int(entry.get("total_ms", 0) or 0)

    total_current_ms_raw = authoring_trace_payload.get("total_ms")
    total_current_ms = int(total_current_ms_raw) if isinstance(total_current_ms_raw, (int, float)) else 0

    # ---- check total_ms_budget --------------------------------------------
    total_budget_raw = baseline_raw.get("total_ms_budget")
    total_budget_ms = (
        max(0, int(total_budget_raw))
        if isinstance(total_budget_raw, (int, float))
        else None
    )

    total_ok = True
    if total_budget_ms is not None:
        total_ok = total_current_ms <= total_budget_ms + tolerance_ms

    # ---- check per-function budgets ---------------------------------------
    functions_raw = baseline_raw.get("functions")
    if not isinstance(functions_raw, dict):
        functions_raw = {}

    checked_functions: list[_AuthoringTraceBudgetCheckRow] = []
    for func_name in sorted(str(n) for n in functions_raw):
        budget_raw = functions_raw.get(func_name)
        if not isinstance(budget_raw, (int, float)):
            continue
        budget_ms = max(0, int(budget_raw))
        current_ms = max(0, current_by_name.get(func_name, 0))
        threshold_ms = budget_ms + tolerance_ms
        delta_ms = current_ms - threshold_ms
        func_ok = current_ms <= threshold_ms
        checked_functions.append(
            {
                "name": func_name,
                "budget_ms": budget_ms,
                "tolerance_ms": tolerance_ms,
                "current_ms": current_ms,
                "delta_ms": delta_ms,
                "ok": bool(func_ok),
            }
        )

    offenders = sorted(
        (row for row in checked_functions if not bool(row["ok"])),
        key=lambda row: (-int(row["delta_ms"]), row["name"]),
    )
    all_ok = total_ok and len(offenders) == 0

    payload = _build_authoring_trace_budget_check_payload(
        ok=all_ok,
        tolerance_ms=tolerance_ms,
        total_budget_ms=total_budget_ms,
        total_current_ms=total_current_ms,
        checked_functions=checked_functions,
    )
    if all_ok:
        return 0, "", payload

    parts: list[str] = []
    if not total_ok and total_budget_ms is not None:
        parts.append(
            f"total: budget_ms={total_budget_ms} tolerance_ms={tolerance_ms} "
            f"current_ms={total_current_ms} delta_ms={total_current_ms - (total_budget_ms + tolerance_ms)}"
        )
    for row in offenders:
        parts.append(
            f"{row['name']}: budget_ms={row['budget_ms']} tolerance_ms={row['tolerance_ms']} "
            f"current_ms={row['current_ms']} delta_ms={row['delta_ms']}"
        )
    offender_text = ", ".join(parts)
    return (
        2,
        (
            f"authoring-trace budget exceeded: {offender_text}; "
            f"update baseline with: {update_command}"
        ),
        payload,
    )


def _fetch_swallowed_exceptions_snapshot() -> dict[str, object]:
    """Snapshot swallowed-exception counts without resetting them.

    Returns a schema-v1 dict.  If the provider is unavailable, returns a
    safe fallback so verify-all never crashes.
    """
    try:
        from engine.swallowed_exceptions import read_counts  # noqa: PLC0415

        raw = read_counts()
        if not isinstance(raw, dict):
            raise TypeError("expected dict")
        per_site: list[dict[str, object]] = sorted(
            ({"site": str(site), "count": int(count)} for site, count in raw.items()),
            key=lambda row: (-int(str(row["count"])), str(row["site"])),
        )
        total = sum(int(str(r["count"])) for r in per_site)
        return {
            "schema_version": 1,
            "ok": True,
            "total": total,
            "distinct": len(per_site),
            "per_site": per_site,
        }
    except (
        AttributeError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        _log_swallow("VFYC-003", "swallowed-exceptions snapshot fallback", once=False)
        return {
            "schema_version": 1,
            "ok": False,
            "total": 0,
            "distinct": 0,
            "per_site": [],
        }


def _fetch_authoring_trace_snapshot() -> dict[str, object] | None:
    """Return an authoring-trace snapshot when ``MESH_AUTHORING_TRACE_ARTIFACT=1``.

    Default-off: returns *None* (and the artifact is not written) unless the
    environment variable is set to a truthy value.  When enabled but no live
    trace data is available, a deterministic empty snapshot is returned.
    """
    if not os.getenv("MESH_AUTHORING_TRACE_ARTIFACT"):
        return None
    # Attempt to read a module-level snapshot if one was stashed by a prior
    # engine run.  In typical verify-all this will be empty because the
    # engine is never booted — that's fine; we still write the artifact.
    try:
        from engine.scene_controller import SceneController  # noqa: PLC0415

        sc = object.__new__(SceneController)
        sc._authoring_trace_enabled = False
        sc._authoring_trace_data = {}
        snap = sc.get_authoring_trace_snapshot(limit=50)
        if isinstance(snap, dict) and "schema_version" in snap:
            return snap
    except Exception:  # noqa: BLE001  # REASON: verify step isolation
        _log_swallow("VFYC-004", "blanket exception fallback", once=False)
        pass
    return {
        "schema_version": 1,
        "enabled": False,
        "total_calls": 0,
        "functions": [],
    }


def _fetch_shadow_backend_diagnostics() -> dict[str, object]:
    """Fetch shadow backend diagnostics without initialising rendering.

    Returns a schema-v1 dict.  If the provider is unavailable (e.g. headless
    CI without GPU libraries), returns a safe fallback so verify-all never
    crashes.
    """
    try:
        from engine.lighting.shadows import get_shadow_backend_diagnostics  # noqa: PLC0415

        raw = get_shadow_backend_diagnostics()
        if not isinstance(raw, dict):
            raise TypeError("expected dict")
        raw_fallbacks = raw.get("fallbacks", [])
        fallbacks = [str(f) for f in raw_fallbacks] if isinstance(raw_fallbacks, (list, tuple)) else []
        return {
            "schema_version": 1,
            "selected": str(raw.get("selected", "?")),
            "reason": str(raw.get("reason", "?")),
            "fallbacks": fallbacks,
        }
    except (
        AttributeError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        _log_swallow("VFYC-005", "shadow-backend diagnostics fallback", once=False)
        return {
            "schema_version": 1,
            "selected": "?",
            "reason": "unavailable",
            "fallbacks": [],
        }


def _fetch_overlay_perf_snapshot() -> dict[str, object]:
    """Fetch overlay/provider performance aggregates.

    Returns a schema-v1 dict with deterministic keys. If unavailable,
    returns a safe zeroed payload so verify-all never crashes.
    """
    empty_metrics = {
        "command_palette_provider": {"count": 0, "total_ms": 0.0, "max_ms": 0.0},
        "providers_total": {"count": 0, "total_ms": 0.0, "max_ms": 0.0},
    }
    try:
        from engine.ui_overlays.providers import read_overlay_perf_telemetry  # noqa: PLC0415

        raw = read_overlay_perf_telemetry(reset=False)
        if not isinstance(raw, dict):
            raise TypeError("expected dict")
        metrics: dict[str, dict[str, object]] = {}
        for name, data in sorted(raw.items()):
            if not isinstance(data, dict):
                continue
            count_raw = data.get("count")
            total_raw = data.get("total_ms")
            max_raw = data.get("max_ms")
            metrics[str(name)] = {
                "count": int(count_raw) if isinstance(count_raw, (int, float)) else 0,
                "total_ms": float(total_raw) if isinstance(total_raw, (int, float)) else 0.0,
                "max_ms": float(max_raw) if isinstance(max_raw, (int, float)) else 0.0,
            }
        for required, defaults in empty_metrics.items():
            metrics.setdefault(required, dict(defaults))
        return {
            "schema_version": 1,
            "metrics": metrics,
        }
    except (
        AttributeError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        _log_swallow("VFYC-006", "overlay-perf snapshot fallback", once=False)
        return {
            "schema_version": 1,
            "metrics": empty_metrics,
        }


def _median_int(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(int(v) for v in values)
    count = len(ordered)
    mid = count // 2
    if count % 2 == 1:
        return int(ordered[mid])
    return int((ordered[mid - 1] + ordered[mid]) // 2)


def _collect_recent_step_durations(
    artifacts_dir: Path,
    *,
    limit: int = 5,
    exclude_paths: set[Path] | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    excludes = {path.resolve() for path in (exclude_paths or set())}
    candidates: dict[Path, tuple[int, str]] = {}

    for path in artifacts_dir.rglob("verify_step_durations*.json"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in excludes:
            continue
        try:
            mtime_ns = int(path.stat().st_mtime_ns)
        except OSError:
            continue
        rel_path = path.relative_to(artifacts_dir).as_posix()
        candidates[resolved] = (mtime_ns, rel_path)

    for path in artifacts_dir.glob("verify_step_durations*.json"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in excludes:
            continue
        try:
            mtime_ns = int(path.stat().st_mtime_ns)
        except OSError:
            continue
        rel_path = path.relative_to(artifacts_dir).as_posix()
        candidates[resolved] = (mtime_ns, rel_path)

    ordered = sorted(
        (
            (int(meta[0]), str(meta[1]), path)
            for path, meta in candidates.items()
        ),
        key=lambda item: (item[0], item[1]),
    )
    selected = ordered[-max(0, int(limit)) :]

    payloads: list[dict[str, object]] = []
    candidates_used: list[str] = []
    for _mtime_ns, rel_path, path in selected:
        try:
            payload = _read_verify_step_durations_payload(path)
            _extract_step_duration_ms(payload)
        except Exception:
            _log_swallow("VFYC-007", "blanket exception fallback", once=False)
            continue
        payloads.append(payload)
        candidates_used.append(str(rel_path))
    return payloads, sorted(candidates_used)


def _evaluate_verify_step_budget_guard(
    *,
    step_durations_payload: dict[str, object],
    baseline_path: Path,
    update_command: str,
    artifacts_dir: Path | None,
) -> tuple[int, str, dict[str, object]]:
    use_history = os.getenv("MESH_VERIFY_STEP_BUDGET_NO_HISTORY", "0") != "1"
    current_step_ms = _extract_step_duration_ms(step_durations_payload)
    history_step_maps: list[dict[str, int]] = []
    candidates_used: list[str] = []
    if use_history and artifacts_dir is not None and artifacts_dir.exists():
        selected_payloads, candidates_used = _collect_recent_step_durations(
            artifacts_dir,
            limit=5,
            exclude_paths={artifacts_dir / "verify_step_durations.json"},
        )
        history_step_maps = [_extract_step_duration_ms(payload) for payload in selected_payloads]

    if not baseline_path.exists():
        payload = _build_verify_step_budget_check_payload(
            ok=True,
            tolerance_ms=_VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS,
            checked_steps=[],
            candidates_used=[],
        )
        return 0, "", payload

    try:
        baseline_raw = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log_swallow("VFYC-008", "blanket exception fallback", once=False)
        payload = _build_verify_step_budget_check_payload(
            ok=False,
            tolerance_ms=_VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS,
            checked_steps=[],
            candidates_used=candidates_used,
        )
        return 1, f"verify-step-budget baseline parse failed: {type(exc).__name__}: {exc}", payload

    if not isinstance(baseline_raw, dict):
        payload = _build_verify_step_budget_check_payload(
            ok=False,
            tolerance_ms=_VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS,
            checked_steps=[],
            candidates_used=candidates_used,
        )
        return 1, "verify-step-budget baseline must be an object", payload

    budgets_raw = baseline_raw.get("budgets_ms")
    if not isinstance(budgets_raw, dict):
        payload = _build_verify_step_budget_check_payload(
            ok=False,
            tolerance_ms=_VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS,
            checked_steps=[],
            candidates_used=candidates_used,
        )
        return 1, "verify-step-budget baseline missing budgets_ms object", payload

    tolerance_raw = baseline_raw.get("tolerance_ms")
    tolerance_ms = (
        max(0, int(tolerance_raw))
        if isinstance(tolerance_raw, (int, float))
        else _VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS
    )
    ratio_limits_raw = baseline_raw.get("ratio_limits")
    ratio_limits_map = ratio_limits_raw if isinstance(ratio_limits_raw, dict) else {}

    checked_steps: list[_VerifyStepBudgetCheckRow] = []
    for step_name in sorted(str(name) for name in budgets_raw):
        budget_raw = budgets_raw.get(step_name)
        if not isinstance(budget_raw, (int, float)):
            continue
        budget_ms = max(0, int(budget_raw))
        ratio_raw = ratio_limits_map.get(step_name)
        ratio_limit = (
            float(ratio_raw)
            if isinstance(ratio_raw, (int, float)) and float(ratio_raw) > 0.0
            else _VERIFY_STEP_BUDGET_DEFAULT_RATIO_LIMIT
        )
        current_ms = max(0, int(current_step_ms.get(step_name, 0)))
        history_values: list[int] = []
        if use_history:
            for history_map in history_step_maps:
                if step_name in history_map:
                    history_values.append(int(history_map[step_name]))
        median_ms = _median_int(history_values) if use_history else None
        effective_ms = max(current_ms, int(median_ms)) if median_ms is not None else current_ms
        near_miss_margin_ms = 0
        if median_ms is None:
            margin_raw = _VERIFY_STEP_BUDGET_NULL_MEDIAN_MARGIN_MS.get(step_name, 0)
            if isinstance(margin_raw, int):
                near_miss_margin_ms = max(0, int(margin_raw))
        effective_tolerance_ms = tolerance_ms + near_miss_margin_ms
        threshold_ms = max(
            budget_ms + tolerance_ms,
            int(budget_ms * ratio_limit),
        )
        if near_miss_margin_ms > 0:
            threshold_ms += near_miss_margin_ms
        delta_ms = effective_ms - threshold_ms
        step_ok = effective_ms <= threshold_ms
        checked_steps.append(
            {
                "name": step_name,
                "budget_ms": budget_ms,
                "tolerance_ms": effective_tolerance_ms,
                "ratio_limit": ratio_limit,
                "threshold_ms": threshold_ms,
                "current_ms": current_ms,
                "median_ms": median_ms,
                "effective_ms": effective_ms,
                "delta_ms": delta_ms,
                "ok": bool(step_ok),
            }
        )

    offenders = sorted(
        (row for row in checked_steps if not bool(row["ok"])),
        key=lambda row: (-int(row["delta_ms"]), row["name"]),
    )
    ok = len(offenders) == 0
    payload = _build_verify_step_budget_check_payload(
        ok=ok,
        tolerance_ms=tolerance_ms,
        checked_steps=checked_steps,
        candidates_used=candidates_used if use_history else [],
    )
    if ok:
        return 0, "", payload

    offender_text = ", ".join(
        (
            f"{row['name']}: budget_ms={row['budget_ms']} tolerance_ms={row['tolerance_ms']} "
            f"ratio_limit={row['ratio_limit']:.2f} threshold_ms={row['threshold_ms']} "
            f"current_ms={row['current_ms']} median_ms={row['median_ms'] if row['median_ms'] is not None else 'n/a'} "
            f"effective_ms={row['effective_ms']} delta_ms={row['delta_ms']}"
        )
        for row in offenders
    )
    return (
        2,
        (
            f"verify slow-step budget exceeded: {offender_text}; "
            f"update baseline with: {update_command}"
        ),
        payload,
    )


def _verify_all_scene_index_out_paths(repo_root, out_dir: str):
    from pathlib import Path

    out_dir_path = Path(out_dir)
    write_base = out_dir_path if out_dir_path.is_absolute() else (Path(repo_root) / out_dir_path)
    scenes_write = write_base / "scenes_index.json"
    worlds_write = write_base / "worlds_index.json"

    scenes_report = (out_dir_path / "scenes_index.json").as_posix()
    worlds_report = (out_dir_path / "worlds_index.json").as_posix()
    if out_dir_path.is_absolute():
        scenes_report = scenes_write.as_posix()
        worlds_report = worlds_write.as_posix()

    return scenes_write, scenes_report, worlds_write, worlds_report


def _read_pytest_fast_durations(metrics_path):
    import json

    raw = metrics_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("durations payload must be a list")
    durations: list[float] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        seconds = item.get("seconds")
        if isinstance(seconds, (int, float)):
            durations.append(float(seconds))
    durations.sort(reverse=True)
    total_seconds = float(sum(durations))
    top10_seconds = float(sum(durations[:10]))
    return total_seconds, top10_seconds


def _evaluate_pytest_fast_duration_guard(metrics_path, total_baseline_path, top10_baseline_path):
    """Ratchet guard for pytest-fast test execution time (not wall-clock).

    This guards the *sum of individual test durations* from pytest_durations_fast.json.
    This is NOT the wall-clock time for the pytest-fast verify step.
    Wall-clock budget is enforced separately by verify_step_budget_check.json.
    """
    total_seconds, top10_seconds = _read_pytest_fast_durations(metrics_path)

    if total_baseline_path.exists():
        try:
            baseline_total = float(total_baseline_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            _log_swallow("VFYC-009", "pytest-fast total baseline parse fallback", once=False)
            baseline_total = total_seconds
    else:
        baseline_total = total_seconds

    if top10_baseline_path.exists():
        try:
            baseline_top10 = float(top10_baseline_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            _log_swallow("VFYC-010", "pytest-fast top10 baseline parse fallback", once=False)
            baseline_top10 = top10_seconds
    else:
        baseline_top10 = top10_seconds

    def _exceeds(current: float, baseline: float) -> bool:
        if baseline <= 0:
            return False
        return current > baseline + 20.0 and current > baseline * 1.15

    total_exceeded = _exceeds(total_seconds, baseline_total)
    top10_exceeded = _exceeds(top10_seconds, baseline_top10)

    if total_exceeded or top10_exceeded:
        parts = []
        if total_exceeded:
            parts.append(f"total {baseline_total:.2f} -> {total_seconds:.2f}")
        if top10_exceeded:
            parts.append(f"top10 {baseline_top10:.2f} -> {top10_seconds:.2f}")
        return 2, "pytest-fast durations regressed: " + ", ".join(parts), total_seconds, top10_seconds, False

    total_baseline_path.write_text(f"{total_seconds:.2f}\n", encoding="utf-8")
    top10_baseline_path.write_text(f"{top10_seconds:.2f}\n", encoding="utf-8")
    return 0, "", total_seconds, top10_seconds, True


_EXCEPTION_BUDGET_FILES: tuple[str, ...] = (
    "engine/game_runtime/tick.py",
    "engine/scene_controller.py",
    "engine/lighting/shadows.py",
)


def _is_exception_budget_handler_type(expr: ast.expr | None) -> bool:
    # Budget semantics:
    # - Count handlers that include Exception:
    #   except Exception:
    #   except Exception as exc:
    #   except (Exception, FooError):
    # - Do not count BaseException-only handlers.
    if expr is None:
        return False
    if isinstance(expr, ast.Name):
        return expr.id == "Exception"
    if isinstance(expr, ast.Attribute):
        return expr.attr == "Exception"
    if isinstance(expr, ast.Tuple):
        return any(_is_exception_budget_handler_type(elt) for elt in expr.elts)
    return False


def _count_exception_handlers_in_text(source: str) -> int:
    try:
        module = ast.parse(source)
    except SyntaxError:
        # Keep guard resilient against temporary parse failures.
        return sum(1 for line in source.splitlines() if line.lstrip().startswith("except Exception"))

    count = 0
    for node in ast.walk(module):
        if isinstance(node, ast.ExceptHandler) and _is_exception_budget_handler_type(node.type):
            count += 1
    return count


def _count_exception_budget(repo_root: Path, rel_paths: tuple[str, ...]) -> tuple[int, dict[str, int]]:
    per_file: dict[str, int] = {}
    total = 0
    for rel in sorted(rel_paths):
        path = (repo_root / rel).resolve()
        count = 0
        if path.exists():
            source = path.read_text(encoding="utf-8")
            count = _count_exception_handlers_in_text(source)
        per_file[rel] = count
        total += count
    return total, per_file


def _write_exception_budget_baseline(baseline_path: Path, current_count: int) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(f"{int(current_count)}\n", encoding="utf-8")


def _exception_budget_update_command() -> str:
    return (
        "python -c \"from pathlib import Path; import mesh_cli.verify as m; from mesh_cli.verify import "
        "_count_exception_budget,_EXCEPTION_BUDGET_FILES,_write_exception_budget_baseline; "
        "repo=Path(m.__file__).resolve().parent.parent; baseline=repo/'tooling/metrics/exception_budget_count.txt'; "
        "current,_=_count_exception_budget(repo,_EXCEPTION_BUDGET_FILES); "
        "_write_exception_budget_baseline(baseline,current); "
        "print(f'updated {baseline.as_posix()} -> {current} (run from any cwd)')\""
    )


def _build_exception_budget_payload(
    *,
    ok: bool,
    current_count: int,
    baseline_count: int,
    per_file_counts: dict[str, int],
    files_scanned: list[str] | None = None,
) -> dict[str, object]:
    sorted_files = sorted(files_scanned if files_scanned is not None else per_file_counts.keys())
    sorted_per_file = {path: int(per_file_counts.get(path, 0)) for path in sorted(per_file_counts)}
    return {
        "schema_version": 1,
        "ok": bool(ok),
        "current_count": int(current_count),
        "baseline_count": int(baseline_count),
        "files_scanned": sorted_files,
        "per_file_counts": sorted_per_file,
    }


def _evaluate_exception_budget_guard(repo_root: Path, baseline_path: Path) -> tuple[int, str, int, int, dict[str, int]]:
    current, per_file = _count_exception_budget(repo_root, _EXCEPTION_BUDGET_FILES)
    if baseline_path.exists():
        try:
            baseline = int(baseline_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            _log_swallow("VFYC-011", "exception-budget baseline parse fallback", once=False)
            baseline = current
    else:
        baseline = current
    if current > baseline:
        return (
            2,
            (
                f"exception budget grew: baseline_count={baseline} current_count={current}. "
                f"update baseline with: {_exception_budget_update_command()}"
            ),
            current,
            baseline,
            per_file,
        )
    return 0, "", current, baseline, per_file


def _run_verify_replays_summary(folder_path):
    """Run the replay suite and return (exit_code, summary_payload)."""

    from pathlib import Path

    from engine.logging_tools import suppress_stdout

    from . import legacy_impl as legacy_mod

    folder_path = Path(folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        return 2, {"ok": False, "code": 2, "error": "replays.folder_not_found"}

    scripts = sorted(
        [
            p
            for p in folder_path.glob("*.json")
            if p.is_file()
            and not p.name.endswith(".hash.json")
            and p.name != "suite.json"
            and not p.name.endswith("_golden.json")
        ],
        key=lambda p: p.name,
    )
    if not scripts:
        return 2, {"ok": False, "code": 2, "error": "replays.no_scripts"}

    try:
        with suppress_stdout():
            summary = legacy_mod.replay_suite.run_replay_suite(str(folder_path))

        failed = summary.get("failed", 0) if isinstance(summary, dict) else 1
        try:
            failed_int = int(failed)
        except (TypeError, ValueError):
            failed_int = 1

        return (0 if failed_int == 0 else 1), summary if isinstance(summary, dict) else {"ok": False, "code": 1}
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        _log_swallow("VFYC-012", "verify-replays summary fallback", once=False)
        return 1, {"ok": False, "code": 1, "error": "replays.failed"}


def _build_artifact_index_payload(
    *,
    overall_ok: bool,
    artifacts_dir: "Path",
    artifacts_written: dict[str, str | None],
    normalize: "Callable",
    repo_root: "Path",
) -> dict:
    """Build the ``index.json`` manifest payload (schema v1)."""
    import json as _json

    verify_all_path = artifacts_written.get("verify_all_summary")

    schemas: dict[str, int] = {}
    readable: dict[str, bool] = {}

    for key, rel_path in sorted(artifacts_written.items()):
        if rel_path is None:
            readable[key] = False
            continue
        rel_candidate = Path(str(rel_path))
        abs_path = rel_candidate if rel_candidate.is_absolute() else (repo_root / rel_candidate)
        if not abs_path.is_file():
            readable[key] = False
            continue
        try:
            raw = abs_path.read_text(encoding="utf-8")
            data = _json.loads(raw)
        except (OSError, json.JSONDecodeError):
            _log_swallow("VFYC-013", "artifact-index read fallback", once=False)
            readable[key] = False
            continue
        if not isinstance(data, dict):
            readable[key] = False
            continue
        readable[key] = True
        sv = data.get("schema_version")
        if isinstance(sv, int):
            schemas[key] = sv

    generated_files = sorted({v for v in artifacts_written.values() if v is not None})

    return {
        "schema_version": 1,
        "bundle_schema_version": 1,
        "ok": bool(overall_ok),
        "verify_all": verify_all_path,
        "written": dict(sorted(artifacts_written.items())),
        "schemas": dict(sorted(schemas.items())),
        "readable": dict(sorted(readable.items())),
        "generated_files": generated_files,
    }


def _handle_verify_all(args: argparse.Namespace) -> int:
    import contextlib
    import io
    import sys

    from engine.persistence_io import dumps_json_deterministic

    # --ci-bundle implies --report-json-artifact and --artifact-index
    if getattr(args, "ci_bundle", False):
        args.report_json_artifact = True
        args.artifact_index = True

    # Keep verify-all stdout pure JSON by discarding any noisy prints from deeper
    # engine/tooling layers while computing the payload.
    with contextlib.redirect_stdout(io.StringIO()):
        payload, exit_code = _build_verify_all_payload(args)

    sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))

    # --report: append human-friendly diagnostics from verify_report
    if getattr(args, "report", False):
        artifacts_dir_arg = str(getattr(args, "artifacts", "") or "").strip()
        if artifacts_dir_arg:
            try:
                from pathlib import Path as _Path

                from .verify_report import build_report_text

                _artifacts = _Path(artifacts_dir_arg)
                if not _artifacts.is_absolute():
                    from engine.repo_root import get_repo_root

                    _artifacts = (get_repo_root(start=_Path.cwd(), strict=False) / _artifacts).resolve()
                if _artifacts.is_dir():
                    sys.stdout.write("\n")
                    sys.stdout.write(build_report_text(_artifacts))
                    sys.stdout.write("\n")
            except Exception:  # noqa: BLE001  # REASON: verify step isolation
                _log_swallow("VFYC-014", "blanket exception fallback", once=False)
                pass  # best-effort; keep original exit code

    # --report-json: append machine-readable JSON diagnostics
    if getattr(args, "report_json", False):
        artifacts_dir_arg = str(getattr(args, "artifacts", "") or "").strip()
        if artifacts_dir_arg:
            try:
                from pathlib import Path as _Path

                from .verify_report import build_report_payload

                _artifacts = _Path(artifacts_dir_arg)
                if not _artifacts.is_absolute():
                    from engine.repo_root import get_repo_root

                    _artifacts = (get_repo_root(start=_Path.cwd(), strict=False) / _artifacts).resolve()
                if _artifacts.is_dir():
                    import json as _json

                    sys.stdout.write("\n")
                    sys.stdout.write(_json.dumps(build_report_payload(_artifacts), indent=2, sort_keys=True))
                    sys.stdout.write("\n")
            except Exception:  # noqa: BLE001  # REASON: verify step isolation
                _log_swallow("VFYC-015", "blanket exception fallback", once=False)
                pass  # best-effort; keep original exit code

    return int(exit_code)


def _handle_verify_local(args: argparse.Namespace) -> int:
    import contextlib
    import io
    import shutil
    import subprocess
    import sys

    from engine.persistence_io import dumps_json_deterministic, write_json_atomic

    from . import legacy_impl as legacy_mod

    suppress_stdout = legacy_mod.suppress_stdout
    _normalize_path_for_json = legacy_mod._normalize_path_for_json

    try:
        from engine.repo_root import get_repo_root

        repo_root = get_repo_root(start=Path.cwd(), strict=True)
    except _VERIFY_LOCAL_STEP_EXCEPTIONS as exc:
        _log_swallow("VFYC-026", "blanket exception fallback", once=False)
        payload = {
            "ok": False,
            "steps": [
                {
                    "name": "verify-local",
                    "ok": False,
                    "code": 1,
                    "error": f"{type(exc).__name__}: {exc}",
                    "artifact": None,
                }
            ],
            "artifacts": {"dir": None, "written": {}},
        }
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 1

    repo_root = Path(repo_root).resolve()
    artifacts_dir_arg = str(getattr(args, "artifacts", "") or "").strip() or None
    artifacts_dir = _artifact_base_dir(repo_root, artifacts_dir_arg) if artifacts_dir_arg else None
    artifacts_dir_json = _normalize_path_for_json(artifacts_dir_arg, repo_root=repo_root) if artifacts_dir_arg else None
    if artifacts_dir is not None:
        artifacts_dir.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, object]] = []
    artifacts_written: dict[str, str | None] = {
        "swallow_scan": None,
        "exception_policy_scan": None,
    }

    def _add_step(name: str, code: int, *, error: str, artifact: str | None) -> None:
        steps.append(
            {
                "name": name,
                "ok": int(code) == 0,
                "code": int(code),
                "error": str(error or ""),
                "artifact": artifact,
            }
        )

    with contextlib.redirect_stdout(io.StringIO()):
        with legacy_mod._pushd(repo_root):
            try:
                config = legacy_mod.load_config()
                world_path = str(getattr(config, "world_file", "") or "").strip() or "worlds/main_world.json"
                with suppress_stdout():
                    code = int(legacy_mod.validate_all.main([world_path, "--strict", "--schema-strict"]))
                _add_step("verify-strict", code, error="" if code == 0 else f"failed with code {code}", artifact=None)
            except _VERIFY_LOCAL_STEP_EXCEPTIONS as exc:
                _log_swallow("VFYC-027", "blanket exception fallback", once=False)
                _add_step("verify-strict", 1, error=f"{type(exc).__name__}: {exc}", artifact=None)

            try:
                from tooling import mypy_island

                with suppress_stdout():
                    code = int(mypy_island.main([]))
                _add_step("mypy-island", code, error="" if code == 0 else f"failed with code {code}", artifact=None)
            except ModuleNotFoundError as exc:
                if str(getattr(exc, "name", "")).startswith("tooling"):
                    _add_step("mypy-island", 0, error="skipped: tooling package unavailable", artifact=None)
                else:
                    raise
            except _VERIFY_LOCAL_STEP_EXCEPTIONS as exc:
                _log_swallow("VFYC-028", "blanket exception fallback", once=False)
                _add_step("mypy-island", 1, error=f"{type(exc).__name__}: {exc}", artifact=None)

            try:
                from tooling import find_blanket_swallow

                with suppress_stdout():
                    code = int(find_blanket_swallow.main(["--roots", "engine", "mesh_cli"]))
                scan_path = repo_root / "artifacts" / "swallow_scan.json"
                artifact = None
                if scan_path.exists():
                    target_path = scan_path
                    if artifacts_dir is not None:
                        target_path = artifacts_dir / "swallow_scan.json"
                        if target_path != scan_path:
                            shutil.copyfile(scan_path, target_path)
                    artifact = _normalize_path_for_json(target_path, repo_root=repo_root)
                    artifacts_written["swallow_scan"] = artifact
                _add_step(
                    "swallow-scan-gate",
                    code,
                    error="" if code == 0 else "pass-only blanket swallows found",
                    artifact=artifact,
                )
            except _VERIFY_LOCAL_STEP_EXCEPTIONS as exc:
                _log_swallow("VFYC-029", "blanket exception fallback", once=False)
                _add_step("swallow-scan-gate", 1, error=f"{type(exc).__name__}: {exc}", artifact=None)

            try:
                from tooling import scan_exception_policies

                with suppress_stdout():
                    payload = scan_exception_policies.scan(
                        ["engine", "mesh_cli", "tooling"],
                        repo_root=repo_root,
                    )
                artifact = None
                if artifacts_dir is not None:
                    target = artifacts_dir / "exception_policy_scan.json"
                    write_json_atomic(target, payload, indent=2, sort_keys=False, trailing_newline=True)
                    artifact = _normalize_path_for_json(target, repo_root=repo_root)
                    artifacts_written["exception_policy_scan"] = artifact
                _add_step("exception-policy-scan", 0, error="", artifact=artifact)
            except _VERIFY_LOCAL_STEP_EXCEPTIONS as exc:
                _log_swallow("VFYC-030", "blanket exception fallback", once=False)
                _add_step("exception-policy-scan", 1, error=f"{type(exc).__name__}: {exc}", artifact=None)

            try:
                if "pytest" in sys.modules:
                    _add_step("pytest-fast", 0, error="skipped: running under pytest", artifact=None)
                else:
                    cmd = [sys.executable, "-m", "tooling.pytest_fast"]
                    with suppress_stdout():
                        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
                    code = int(result.returncode)
                    _add_step("pytest-fast", code, error="" if code == 0 else f"failed with code {code}", artifact=None)
            except _VERIFY_LOCAL_STEP_EXCEPTIONS as exc:
                _log_swallow("VFYC-031", "blanket exception fallback", once=False)
                _add_step("pytest-fast", 1, error=f"{type(exc).__name__}: {exc}", artifact=None)

    overall_ok = all(bool(step.get("ok")) for step in steps)
    payload = {
        "ok": bool(overall_ok),
        "steps": steps,
        "artifacts": {
            "dir": artifacts_dir_json,
            "written": artifacts_written,
        },
    }
    sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
    return 0 if overall_ok else 1


def _build_verify_all_payload(args: argparse.Namespace):
    import sys
    from pathlib import Path
    from typing import Any

    from . import legacy_impl as legacy_mod

    suppress_stdout = legacy_mod.suppress_stdout
    _single_line_error = legacy_mod._single_line_error
    _normalize_path_for_json = legacy_mod._normalize_path_for_json
    _pushd = legacy_mod._pushd
    load_config = legacy_mod.load_config
    validate_all = legacy_mod.validate_all
    verify_demo = legacy_mod.verify_demo
    _resolve_scene_paths = legacy_mod._resolve_scene_paths
    generate_encounter_report = legacy_mod.generate_encounter_report
    _inventory_list_scenes = legacy_mod._inventory_list_scenes
    _inventory_list_worlds = legacy_mod._inventory_list_worlds

    # Only accept pytest passthrough args after `--` (argparse captures them as REMAINDER).
    pytest_args = list(getattr(args, "pytest_args", None) or [])
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    try:
        from engine.repo_root import get_repo_root

        repo_root = get_repo_root(start=Path.cwd(), strict=True)
    except Exception as exc:  # noqa: BLE001  # REASON: verify step isolation
        _log_swallow("VFYC-016", "blanket exception fallback", once=False)
        error_steps: list[dict[str, Any]] = []
        is_first_step = True
        for name in VERIFY_ALL_STEPS:
            if is_first_step:
                error_steps.append(
                    {
                        "name": name,
                        "ok": False,
                        "code": 2,
                        "error": _single_line_error(f"{type(exc).__name__}: {exc}"),
                        "artifact": None,
                    }
                )
                is_first_step = False
                continue
            error_steps.append(
                {
                    "name": name,
                    "ok": False,
                    "code": 2,
                    "error": "skipped: previous step failed",
                    "artifact": None,
                }
            )
        payload = {
            "ok": False,
            "steps": error_steps,
            "pytest_fast": {"ok": None, "total": None, "top10": None},
            "artifacts": {
                "dir": None,
                "written": {
                    "verify_all_summary": None,
                    "verify_step_durations": None,
                    "verify_step_budget_check": None,
                    "overlay_perf": None,
                    "shadow_backend": None,
                    "swallowed_exceptions": None,
                    "release_notes_json": None,
                    "release_notes_md": None,
                    "scenes_index": None,
                    "worlds_index": None,
                    "replays_summary": None,
                    "doctor_assets": None,
                    "stamp_audit": None,
                    "brush_audit": None,
                    "macro_audit": None,
                    "room_audit": None,
                    "encounter_coverage_matrix": None,
                    "exception_budget": None,
                    "content_audit": None,
                    "encounter_audit_summary": None,
                    "encounter_audit_compact": None,
                    "encounter_headroom": None,
                    "perf_run": None,
                    "perf_compare": None,
                    "player_package_manifest": None,
                    "player_package_check": None,
                    "player_package_runtime_smoke": None,
                    "player_package_runtime_diagnostics_snapshot": None,
                    "runtime_smoke": None,
                    "runtime_diagnostics_snapshot": None,
                    "web_smoke": None,
                    "authoring_trace": None,
                    "authoring_trace_budget_check": None,
                    "verify_summary_json": None,
                    "verify_summary_txt": None,
                },
            },
        }
        from engine.persistence_io import dumps_json_deterministic

        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 2
    repo_root = Path(repo_root).resolve()

    out_dir = str(getattr(args, "out_dir", "") or "").strip() or None
    artifacts_dir_arg = str(getattr(args, "artifacts", "") or "").strip() or None
    no_index = bool(getattr(args, "no_index", False))

    artifacts_dir = _artifact_base_dir(repo_root, artifacts_dir_arg) if artifacts_dir_arg else None
    artifacts_dir_json = _normalize_path_for_json(artifacts_dir_arg, repo_root=repo_root) if artifacts_dir_arg else None

    artifacts_written: dict[str, str | None] = {
        "verify_all_summary": None,
        "verify_step_durations": None,
        "verify_step_budget_check": None,
        "overlay_perf": None,
        "shadow_backend": None,
        "swallowed_exceptions": None,
        "release_notes_json": None,
        "release_notes_md": None,
        "scenes_index": None,
        "worlds_index": None,
        "replays_summary": None,
        "doctor_assets": None,
        "stamp_audit": None,
        "brush_audit": None,
        "macro_audit": None,
        "room_audit": None,
        "encounter_coverage_matrix": None,
        "exception_budget": None,
        "content_audit": None,
        "encounter_audit_summary": None,
        "encounter_audit_compact": None,
        "encounter_headroom": None,
        "perf_run": None,
        "perf_compare": None,
        "player_package_manifest": None,
        "player_package_check": None,
        "player_package_runtime_smoke": None,
        "player_package_runtime_diagnostics_snapshot": None,
        "runtime_smoke": None,
        "runtime_diagnostics_snapshot": None,
        "web_smoke": None,
        "authoring_trace": None,
        "authoring_trace_budget_check": None,
        "verify_summary_json": None,
        "verify_summary_txt": None,
        "verify_report": None,
        "artifact_index": None,
    }

    write_scenes: Path | None = None
    write_worlds: Path | None = None
    report_scenes: str | None = None
    report_worlds: str | None = None
    if (artifacts_dir_arg or out_dir) and not no_index:
        sink_dir = artifacts_dir_arg or out_dir or ""
        if sink_dir:
            write_scenes, report_scenes, write_worlds, report_worlds = _verify_all_scene_index_out_paths(repo_root, sink_dir)

    context = VerifyStepContext(
        args=args,
        repo_root=repo_root,
        pytest_args=pytest_args,
        artifacts_dir=artifacts_dir,
        artifacts_written=artifacts_written,
        no_index=no_index,
        write_scenes=write_scenes,
        write_worlds=write_worlds,
        suppress_stdout=suppress_stdout,
        single_line_error=_single_line_error,
        normalize_path_for_json=_normalize_path_for_json,
        pushd=_pushd,
        load_config=load_config,
        validate_all=validate_all,
        verify_demo=verify_demo,
        resolve_scene_paths=_resolve_scene_paths,
        generate_encounter_report=generate_encounter_report,
        inventory_list_scenes=_inventory_list_scenes,
        inventory_list_worlds=_inventory_list_worlds,
        run_verify_replays_summary=_run_verify_replays_summary,
        evaluate_exception_budget_guard=_evaluate_exception_budget_guard,
        build_exception_budget_payload=_build_exception_budget_payload,
        evaluate_pytest_fast_duration_guard=_evaluate_pytest_fast_duration_guard,
        default_transition_entity_id=legacy_mod._default_transition_entity_id,
        ensure_scene_transition_entity=legacy_mod._ensure_scene_transition_entity,
        exception_budget_files=_EXCEPTION_BUDGET_FILES,
    )
    run_verify_steps(context)

    expected_steps = list(VERIFY_ALL_STEPS)
    steps = context.steps
    pytest_fast_metrics = context.pytest_fast_metrics
    exit_code = context.exit_code

    # Ensure stable shape: include skipped steps even if failure happened before they were processed.
    seen_names = {s.get("name") for s in steps}
    for name in expected_steps:
        if name not in seen_names:
            context.skipped_step(name)

    overall_ok = all(bool(s.get("ok")) for s in steps)

    step_durations_payload = _build_verify_step_durations_payload(
        expected_steps=expected_steps,
        rows=context.step_duration_rows,
    )

    if artifacts_dir is not None:
        artifacts_written["verify_all_summary"] = _normalize_path_for_json(
            artifacts_dir / "verify_all_summary.json", repo_root=repo_root
        )
        artifacts_written["verify_step_durations"] = _normalize_path_for_json(
            artifacts_dir / "verify_step_durations.json", repo_root=repo_root
        )
        artifacts_written["verify_step_budget_check"] = _normalize_path_for_json(
            artifacts_dir / "verify_step_budget_check.json", repo_root=repo_root
        )
        artifacts_written["shadow_backend"] = _normalize_path_for_json(
            artifacts_dir / "shadow_backend.json", repo_root=repo_root
        )
        artifacts_written["swallowed_exceptions"] = _normalize_path_for_json(
            artifacts_dir / "swallowed_exceptions.json", repo_root=repo_root
        )

    if artifacts_dir is not None:
        import sys

        from engine.persistence_io import write_json_atomic

        with suppress_stdout():
            _archive_verify_step_durations_artifact(artifacts_dir)

        with suppress_stdout():
            write_json_atomic(
                artifacts_dir / "verify_step_durations.json",
                step_durations_payload,
                indent=2,
                sort_keys=True,
                trailing_newline=True,
            )

        verify_step_budget_baseline = repo_root / "tooling" / "metrics" / "verify_step_budget.json"
        update_command = _verify_step_budget_update_command(artifacts_dir)
        try:
            step_durations_from_artifact = _read_verify_step_durations_payload(artifacts_dir / "verify_step_durations.json")
            budget_code, budget_error, verify_step_budget_payload = _evaluate_verify_step_budget_guard(
                step_durations_payload=step_durations_from_artifact,
                baseline_path=verify_step_budget_baseline,
                update_command=update_command,
                artifacts_dir=artifacts_dir,
            )
        except Exception as exc:
            _log_swallow("VFYC-017", "blanket exception fallback", once=False)
            budget_code = 1
            budget_error = f"verify-step-budget guard failed: {type(exc).__name__}: {exc}"
            verify_step_budget_payload = _build_verify_step_budget_check_payload(
                ok=False,
                tolerance_ms=_VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS,
                checked_steps=[],
                candidates_used=[],
            )

        with suppress_stdout():
            write_json_atomic(
                artifacts_dir / "verify_step_budget_check.json",
                verify_step_budget_payload,
                indent=2,
                sort_keys=True,
                trailing_newline=True,
            )
        if budget_code != 0:
            overall_ok, exit_code = _apply_verify_step_budget_exit_state(
                overall_ok=overall_ok,
                exit_code=exit_code,
                budget_code=budget_code,
            )
            if budget_error:
                print(f"[Mesh][Verify] {budget_error}", file=sys.stderr)
            if _is_mypy_budget_offender(verify_step_budget_payload):
                try:
                    from engine.persistence_io import write_text_atomic

                    mypy_diag_raw = _load_mypy_gate_run_diagnostics()
                    mypy_diag_payload = _build_mypy_budget_diagnostic_payload(
                        mypy_diagnostics=mypy_diag_raw,
                        verify_step_budget_payload=verify_step_budget_payload,
                    )
                    mypy_diag_text = _format_mypy_budget_diagnostic_text(mypy_diag_payload)
                    with suppress_stdout():
                        write_json_atomic(
                            artifacts_dir / "mypy_budget_diagnostic.json",
                            mypy_diag_payload,
                            indent=2,
                            sort_keys=True,
                            trailing_newline=True,
                        )
                        write_text_atomic(
                            artifacts_dir / "mypy_budget_diagnostic.txt",
                            mypy_diag_text,
                            encoding="utf-8",
                        )
                except Exception:  # noqa: BLE001  # REASON: verify step isolation
                    _log_swallow("VFYC-018", "blanket exception fallback", once=False)
                    pass
            if _is_pytest_fast_budget_offender(verify_step_budget_payload):
                try:
                    with suppress_stdout():
                        _write_pytest_fast_budget_diagnostic_artifacts(
                            repo_root=repo_root,
                            artifacts_dir=artifacts_dir,
                            verify_step_budget_payload=verify_step_budget_payload,
                        )
                except Exception:  # noqa: BLE001  # REASON: verify step isolation
                    _log_swallow("VFYC-019", "blanket exception fallback", once=False)
                    pass

        # Shadow backend diagnostics artifact
        shadow_backend_payload = _fetch_shadow_backend_diagnostics()
        with suppress_stdout():
            write_json_atomic(
                artifacts_dir / "shadow_backend.json",
                shadow_backend_payload,
                indent=2,
                sort_keys=True,
                trailing_newline=True,
            )

        # Swallowed exceptions snapshot artifact
        swallowed_payload = _fetch_swallowed_exceptions_snapshot()
        with suppress_stdout():
            write_json_atomic(
                artifacts_dir / "swallowed_exceptions.json",
                swallowed_payload,
                indent=2,
                sort_keys=True,
                trailing_newline=True,
            )

        # Overlay/provider perf telemetry artifact (CI bundle only).
        if bool(getattr(args, "ci_bundle", False)):
            overlay_perf_payload = _fetch_overlay_perf_snapshot()
            with suppress_stdout():
                write_json_atomic(
                    artifacts_dir / "overlay_perf.json",
                    overlay_perf_payload,
                    indent=2,
                    sort_keys=True,
                    trailing_newline=True,
                )
            artifacts_written["overlay_perf"] = _normalize_path_for_json(
                artifacts_dir / "overlay_perf.json", repo_root=repo_root
            )

        # Authoring trace snapshot artifact (optional, default-off)
        authoring_trace_payload = _fetch_authoring_trace_snapshot()
        if authoring_trace_payload is not None:
            with suppress_stdout():
                write_json_atomic(
                    artifacts_dir / "authoring_trace.json",
                    authoring_trace_payload,
                    indent=2,
                    sort_keys=True,
                    trailing_newline=True,
                )
            artifacts_written["authoring_trace"] = _normalize_path_for_json(
                artifacts_dir / "authoring_trace.json", repo_root=repo_root
            )

            # Authoring-trace budget guard (optional, default-off)
            if (
                authoring_trace_payload.get("schema_version") == 1
                and authoring_trace_payload.get("enabled") is True
            ):
                trace_budget_baseline = repo_root / "tooling" / "metrics" / "authoring_trace_budget.json"
                trace_budget_update_cmd = _authoring_trace_budget_update_command(artifacts_dir)
                try:
                    trace_budget_code, trace_budget_error, trace_budget_payload = _evaluate_authoring_trace_budget_guard(
                        authoring_trace_payload=authoring_trace_payload,
                        baseline_path=trace_budget_baseline,
                        update_command=trace_budget_update_cmd,
                    )
                except Exception as exc:
                    _log_swallow("VFYC-020", "blanket exception fallback", once=False)
                    trace_budget_code = 1
                    trace_budget_error = f"authoring-trace-budget guard failed: {type(exc).__name__}: {exc}"
                    trace_budget_payload = _build_authoring_trace_budget_check_payload(
                        ok=False,
                        tolerance_ms=_AUTHORING_TRACE_BUDGET_DEFAULT_TOLERANCE_MS,
                        total_budget_ms=None,
                        total_current_ms=None,
                        checked_functions=[],
                    )

                with suppress_stdout():
                    write_json_atomic(
                        artifacts_dir / "authoring_trace_budget_check.json",
                        trace_budget_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                artifacts_written["authoring_trace_budget_check"] = _normalize_path_for_json(
                    artifacts_dir / "authoring_trace_budget_check.json", repo_root=repo_root
                )
                if trace_budget_code != 0:
                    overall_ok = False
                    if exit_code == 0:
                        exit_code = 2 if trace_budget_code == 2 else 1
                    if trace_budget_error:
                        print(f"[Mesh][Verify] {trace_budget_error}", file=sys.stderr)

    # --report-json-artifact: write verify_report.json to artifacts dir
    if artifacts_dir is not None and getattr(args, "report_json_artifact", False):
        try:
            from .verify_report import build_report_payload

            _report_payload = build_report_payload(artifacts_dir)
            with suppress_stdout():
                write_json_atomic(
                    artifacts_dir / "verify_report.json",
                    _report_payload,
                    indent=2,
                    sort_keys=True,
                    trailing_newline=True,
                )
            artifacts_written["verify_report"] = _normalize_path_for_json(
                artifacts_dir / "verify_report.json", repo_root=repo_root
            )
        except Exception:  # noqa: BLE001  # REASON: verify step isolation
            _log_swallow("VFYC-021", "blanket exception fallback", once=False)
            pass  # best-effort; keep exit code unchanged

    # --release-notes-artifact: write release_notes.json + release_notes.md to artifacts dir
    if artifacts_dir is not None and getattr(args, "release_notes_artifact", False):
        try:
            from engine.persistence_io import write_text_atomic

            from .release_notes import build_release_notes, build_release_notes_payload

            release_notes_payload = build_release_notes_payload(
                artifacts_dir,
                title=None,
                max_sites=5,
                max_steps=5,
            )
            release_notes_text = build_release_notes(
                artifacts_dir,
                title=None,
                max_sites=5,
                max_steps=5,
            )
            with suppress_stdout():
                write_json_atomic(
                    artifacts_dir / "release_notes.json",
                    release_notes_payload,
                    indent=2,
                    sort_keys=True,
                    trailing_newline=True,
                )
                write_text_atomic(
                    artifacts_dir / "release_notes.md",
                    release_notes_text,
                    encoding="utf-8",
                )
            artifacts_written["release_notes_json"] = _normalize_path_for_json(
                artifacts_dir / "release_notes.json", repo_root=repo_root
            )
            artifacts_written["release_notes_md"] = _normalize_path_for_json(
                artifacts_dir / "release_notes.md", repo_root=repo_root
            )
        except Exception:  # noqa: BLE001  # REASON: verify step isolation
            _log_swallow("VFYC-022", "blanket exception fallback", once=False)
            pass  # best-effort; keep exit code unchanged

    # Always write compact verify summary artifacts when --artifacts is enabled.
    if artifacts_dir is not None:
        try:
            verify_summary_payload = _build_verify_summary_payload(
                overall_ok=overall_ok,
                steps=steps,
                artifacts_written=artifacts_written,
            )
            with suppress_stdout():
                _write_verify_summary_artifacts(artifacts_dir, verify_summary_payload)
            artifacts_written["verify_summary_json"] = _normalize_path_for_json(
                artifacts_dir / "verify_summary.json", repo_root=repo_root
            )
            artifacts_written["verify_summary_txt"] = _normalize_path_for_json(
                artifacts_dir / "verify_summary.txt", repo_root=repo_root
            )
        except Exception:  # noqa: BLE001  # REASON: verify step isolation
            _log_swallow("VFYC-025", "blanket exception fallback", once=False)
            pass  # best-effort; keep exit code unchanged

    # --artifact-index: write artifacts/index.json manifest
    if artifacts_dir is not None and getattr(args, "artifact_index", False):
        try:
            _index_payload = _build_artifact_index_payload(
                overall_ok=overall_ok,
                artifacts_dir=artifacts_dir,
                artifacts_written=artifacts_written,
                normalize=_normalize_path_for_json,
                repo_root=repo_root,
            )
            with suppress_stdout():
                write_json_atomic(
                    artifacts_dir / "index.json",
                    _index_payload,
                    indent=2,
                    sort_keys=True,
                    trailing_newline=True,
                )
            artifacts_written["artifact_index"] = _normalize_path_for_json(
                artifacts_dir / "index.json", repo_root=repo_root
            )
        except Exception:  # noqa: BLE001  # REASON: verify step isolation
            _log_swallow("VFYC-032", "blanket exception fallback", once=False)
            pass  # best-effort; keep exit code unchanged

    if artifacts_dir is not None:
        missing_metric_artifacts = _missing_required_verify_metric_artifacts(artifacts_dir)
        if missing_metric_artifacts:
            overall_ok = False
            if exit_code == 0:
                exit_code = 1
            print(
                "[Mesh][Verify] missing required metric artifacts: "
                + ", ".join(missing_metric_artifacts),
                file=sys.stderr,
            )

    payload = {
        "ok": bool(overall_ok),
        "steps": steps,
        "pytest_fast": pytest_fast_metrics,
        "artifacts": {
            "dir": artifacts_dir_json,
            "written": artifacts_written,
        },
    }

    if artifacts_dir is not None:
        # Always write the verify-all summary artifact (even on failure).
        with suppress_stdout():
            _write_verify_all_summary_artifact(artifacts_dir, payload)

    return payload, exit_code


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # Verify demo (fast deterministic test subset)
    verify_demo_parser = subparsers.add_parser("verify-demo", help="Run curated demo verification tests")
    verify_demo_parser.add_argument(
        "--artifacts",
        help="Optional artifact directory for verify-demo scratch and failure diagnostics",
    )
    verify_demo_parser.add_argument(
        "--ci-bundle",
        action="store_true",
        default=False,
        dest="ci_bundle",
        help="Compatibility flag accepted for verify-all parity; verify-demo ignores it",
    )
    verify_demo_parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Optional pytest args after `--` (selection-changing args are blocked)",
    )

    # Verify strict (validate-all --strict CI gate)
    verify_strict_parser = subparsers.add_parser(
        "verify-strict",
        help="Run validate-all in strict mode and fail on any errors",
    )
    verify_strict_parser.add_argument("--world", help="World file to validate")

    # Verify replays (deterministic replay-suite wrapper)
    verify_replays_parser = subparsers.add_parser(
        "verify-replays",
        help="Run the deterministic replay suite and fail if any script fails",
    )
    verify_replays_parser.add_argument(
        "--folder",
        help="Folder containing replay scripts (defaults to repo-root replays/)",
    )
    verify_replays_parser.add_argument(
        "--out",
        help="Optional path to write summary JSON",
    )

    # Verify all (umbrella CI gate with deterministic JSON output)
    verify_all_parser = subparsers.add_parser(
        "verify-all",
        help="Run core verification gates in order and print a deterministic JSON summary",
    )
    verify_all_parser.add_argument("--out-dir", help="Optional directory to write scene/world indices")
    verify_all_parser.add_argument("--artifacts", help="Optional directory to write CI-friendly JSON artifacts")
    verify_all_parser.add_argument(
        "--no-index",
        action="store_true",
        help="Disable writing indices even if --out-dir is provided",
    )
    verify_all_parser.add_argument(
        "--report",
        action="store_true",
        default=False,
        help="Print a human-friendly diagnostics report after the JSON summary",
    )
    verify_all_parser.add_argument(
        "--report-json",
        action="store_true",
        default=False,
        dest="report_json",
        help="Print a machine-readable JSON diagnostics report after the JSON summary",
    )
    verify_all_parser.add_argument(
        "--report-json-artifact",
        action="store_true",
        default=False,
        dest="report_json_artifact",
        help="Write a verify_report.json artifact to the artifacts directory",
    )
    verify_all_parser.add_argument(
        "--artifact-index",
        action="store_true",
        default=False,
        dest="artifact_index",
        help="Write an index.json artifact manifest to the artifacts directory",
    )
    verify_all_parser.add_argument(
        "--ci-bundle",
        action="store_true",
        default=False,
        dest="ci_bundle",
        help="Convenience flag: implies --report-json-artifact and --artifact-index",
    )
    verify_all_parser.add_argument(
        "--release-notes-artifact",
        action="store_true",
        default=False,
        dest="release_notes_artifact",
        help="Write release_notes.json and release_notes.md to the artifacts directory",
    )
    verify_all_parser.add_argument(
        "--skip-web-smoke",
        action="store_true",
        default=False,
        dest="skip_web_smoke",
        help="Skip the web build + web smoke shipping gate",
    )
    verify_local_parser = subparsers.add_parser(
        "verify-local",
        help="Run a fast local verification subset with deterministic JSON output",
    )
    verify_local_parser.add_argument("--artifacts", help="Optional directory to write local verify artifacts")
    verify_all_parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Optional pytest args after `--` for verify-demo only (selection-changing args are blocked)",
    )


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "command", None)

    if command == "verify-demo":
        import sys
        from pathlib import Path

        from engine.logging_tools import suppress_stdout
        from engine.persistence_io import dumps_json_deterministic
        from engine.tooling import verify_demo

        pytest_args = list(getattr(args, "pytest_args", None) or [])
        artifacts_arg = str(getattr(args, "artifacts", "") or "").strip()
        scratch_dir = (Path(artifacts_arg) / "verify_demo_pytest") if artifacts_arg else None
        log_path = (Path(artifacts_arg) / "verify_demo.log") if artifacts_arg else None
        if pytest_args and pytest_args[0] == "--":
            pytest_args = pytest_args[1:]
        with suppress_stdout():
            verify_demo_code = int(
                verify_demo.run_verify_demo(
                    pytest_args,
                    capture_output=True,
                    quiet=True,
                    log_path=log_path,
                    scratch_dir=scratch_dir,
                )
            )
        verify_demo_payload = {"ok": verify_demo_code == 0, "code": verify_demo_code}
        sys.stdout.write(dumps_json_deterministic(verify_demo_payload, indent=2, sort_keys=True, trailing_newline=True))
        return verify_demo_code

    if command == "verify-strict":
        import sys
        from pathlib import Path

        from engine.logging_tools import suppress_stdout
        from engine.persistence_io import dumps_json_deterministic

        from . import legacy_impl as legacy_mod

        try:
            config = legacy_mod.load_config()
            world_path = str(getattr(args, "world", "") or "").strip()
            if not world_path:
                world_path = str(getattr(config, "world_file", "") or "").strip()
            if not world_path:
                world_path = "worlds/main_world.json"

            with suppress_stdout():
                code = int(legacy_mod.validate_all.main([world_path, "--strict", "--schema-strict"]))
            error = "" if code == 0 else f"failed with code {code}"
        except Exception as exc:  # noqa: BLE001  # REASON: verify step isolation
            _log_swallow("VFYC-024", "blanket exception fallback", once=False)
            code = 1
            error = f"{type(exc).__name__}: {exc}"

        payload = {
            "ok": code == 0,
            "code": int(code),
            "error": str(error or ""),
            "world": str(Path(world_path).as_posix()),
            "checks": ["validate-all --strict", "validate-all --schema-strict"],
        }
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return int(code)

    if command == "verify-replays":
        import sys
        from pathlib import Path

        from engine.logging_tools import suppress_stdout
        from engine.persistence_io import dumps_json_deterministic, write_json_atomic


        folder_arg = str(getattr(args, "folder", "") or "").strip() or None
        if folder_arg is None:
            from engine.repo_root import get_repo_root

            repo_root = get_repo_root(start=Path.cwd(), strict=False)
            folder_path = repo_root / "replays"
        else:
            folder_path = Path(folder_arg)

        verify_replays_code, verify_replays_payload = _run_verify_replays_summary(folder_path)

        out_path = getattr(args, "out", None)
        if out_path and verify_replays_code == 0:
            with suppress_stdout():
                write_json_atomic(Path(out_path), verify_replays_payload, indent=2, sort_keys=True, trailing_newline=True)

        sys.stdout.write(dumps_json_deterministic(verify_replays_payload, indent=2, sort_keys=True, trailing_newline=True))
        return int(verify_replays_code)

    if command == "verify-all":
        return int(_handle_verify_all(args))
    if command == "verify-local":
        return int(_handle_verify_local(args))

    return 1
