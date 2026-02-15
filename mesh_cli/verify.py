from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
from typing import TypedDict

from mesh_cli.verify_steps import STEP_ORDER as VERIFY_ALL_STEPS
from mesh_cli.verify_steps import VerifyStepContext, run_verify_steps


class _VerifyStepDurationRow(TypedDict):
    name: str
    ok: bool
    ms: int


class _VerifyStepBudgetCheckRow(TypedDict):
    name: str
    budget_ms: int
    tolerance_ms: int
    current_ms: int
    median_ms: int | None
    effective_ms: int
    delta_ms: int
    ok: bool


_VERIFY_STEP_BUDGET_SCHEMA_VERSION = 2
_VERIFY_STEP_BUDGET_TOP_N = 5
_VERIFY_STEP_BUDGET_DEFAULT_TOLERANCE_MS = 50


def _verify_all_invalid_args() -> int:
    # Kept for backward call sites; `_handle_verify_all` emits schema-complete output.
    import sys

    from engine.persistence_io import dumps_json_deterministic

    payload = {"ok": False, "steps": [], "artifacts": {"dir": None, "written": {}}}
    sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
    return 2


def _artifact_base_dir(repo_root, dir_arg: str):
    from pathlib import Path

    path = Path(dir_arg)
    return path if path.is_absolute() else (Path(repo_root) / path)


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
    return {
        "schema_version": _VERIFY_STEP_BUDGET_SCHEMA_VERSION,
        "budgets_ms": budgets_ms,
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
        "python -c \"from pathlib import Path; import mesh_cli.verify as m; "
        f"artifacts=Path(r'{artifacts_rel}'); "
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
    except Exception:
        return {
            "schema_version": 1,
            "ok": False,
            "total": 0,
            "distinct": 0,
            "per_site": [],
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
    except Exception:
        return {
            "schema_version": 1,
            "selected": "?",
            "reason": "unavailable",
            "fallbacks": [],
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

    for path in artifacts_dir.rglob("verify_step_durations.json"):
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

    checked_steps: list[_VerifyStepBudgetCheckRow] = []
    for step_name in sorted(str(name) for name in budgets_raw):
        budget_raw = budgets_raw.get(step_name)
        if not isinstance(budget_raw, (int, float)):
            continue
        budget_ms = max(0, int(budget_raw))
        current_ms = max(0, int(current_step_ms.get(step_name, 0)))
        history_values: list[int] = []
        if use_history:
            for history_map in history_step_maps:
                if step_name in history_map:
                    history_values.append(int(history_map[step_name]))
        median_ms = _median_int(history_values) if use_history else None
        effective_ms = max(current_ms, int(median_ms)) if median_ms is not None else current_ms
        threshold_ms = budget_ms + tolerance_ms
        delta_ms = effective_ms - threshold_ms
        step_ok = effective_ms <= threshold_ms
        checked_steps.append(
            {
                "name": step_name,
                "budget_ms": budget_ms,
                "tolerance_ms": tolerance_ms,
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
    total_seconds, top10_seconds = _read_pytest_fast_durations(metrics_path)

    if total_baseline_path.exists():
        try:
            baseline_total = float(total_baseline_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            baseline_total = total_seconds
    else:
        baseline_total = total_seconds

    if top10_baseline_path.exists():
        try:
            baseline_top10 = float(top10_baseline_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
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
        except Exception:
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
    except Exception:
        return 1, {"ok": False, "code": 1, "error": "replays.failed"}


def _handle_verify_all(args: argparse.Namespace) -> int:
    import contextlib
    import io
    import sys

    from engine.persistence_io import dumps_json_deterministic

    # Keep verify-all stdout pure JSON by discarding any noisy prints from deeper
    # engine/tooling layers while computing the payload.
    with contextlib.redirect_stdout(io.StringIO()):
        payload, exit_code = _build_verify_all_payload(args)

    sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
    return int(exit_code)


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
    except Exception as exc:  # noqa: BLE001
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
                    "shadow_backend": None,
                    "swallowed_exceptions": None,
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
        "shadow_backend": None,
        "swallowed_exceptions": None,
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
            overall_ok = False
            if exit_code == 0:
                exit_code = 2 if budget_code == 2 else 1
            if budget_error:
                print(f"[Mesh][Verify] {budget_error}", file=sys.stderr)

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
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Optional pytest args after `--` for verify-demo only (selection-changing args are blocked)",
    )


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "command", None)

    if command == "verify-demo":
        import sys

        from engine.logging_tools import suppress_stdout
        from engine.persistence_io import dumps_json_deterministic
        from engine.tooling import verify_demo

        pytest_args = list(getattr(args, "pytest_args", None) or [])
        if pytest_args and pytest_args[0] == "--":
            pytest_args = pytest_args[1:]
        with suppress_stdout():
            verify_demo_code = int(verify_demo.run_verify_demo(pytest_args, capture_output=True, quiet=True))
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
        except Exception as exc:  # noqa: BLE001
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

    return 1
