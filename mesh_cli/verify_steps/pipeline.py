from __future__ import annotations

from dataclasses import dataclass, field
import json
import importlib.util
from engine.log_utils import get_logger
from engine.swallowed_exceptions import _log_swallow
from pathlib import Path
import time
from typing import Any, Callable, cast

_VERIFY_WEB_GATE_EXCEPTIONS: tuple[type[Exception], ...] = (
    AttributeError,
    FileNotFoundError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

def _normalize_diag_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def _cleanup_stale_pytest_fast_budget_artifacts(
    repo_root: Path,
    *,
    artifacts_dir: Path | None,
) -> None:
    stale_names = (
        "verify_step_budget_check.json",
        "pytest_fast_budget_diagnostic.json",
        "pytest_fast_budget_diagnostic.txt",
    )
    candidate_dirs: list[Path] = [repo_root / "artifacts"]
    if artifacts_dir is not None and artifacts_dir not in candidate_dirs:
        candidate_dirs.append(artifacts_dir)
    for candidate_dir in candidate_dirs:
        for stale_name in stale_names:
            stale_path = candidate_dir / stale_name
            try:
                stale_path.unlink()
            except FileNotFoundError:
                continue


def _read_mypy_baseline_count(metrics_path: Path, *, current_count: int) -> int:
    try:
        return int(metrics_path.read_text(encoding="utf-8").strip() or "0")
    except OSError:  # REASON: mypy-baseline-guard metrics file fallback
        _log_swallow(
            "VSTP-005",
            f"mypy-baseline-guard metrics read fallback path={_normalize_diag_path(metrics_path)}",
            once=False,
        )
    except ValueError:  # REASON: mypy-baseline-guard metrics coercion fallback
        _log_swallow(
            "VSTP-005",
            f"mypy-baseline-guard metrics coercion fallback path={_normalize_diag_path(metrics_path)}",
            once=False,
        )
    return current_count


def _read_swallow_scan_total_matches(scan_path: Path) -> int | None:
    try:
        payload = json.loads(scan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # REASON: swallow-scan-gate artifact parsing fallback
        _log_swallow(
            "VSTP-043",
            f"swallow-scan-gate artifact parse fallback path={_normalize_diag_path(scan_path)}",
            once=False,
        )
        return None
    try:
        return int(payload.get("total_matches", 0))
    except (TypeError, ValueError):  # REASON: swallow-scan-gate total_matches coercion fallback
        _log_swallow(
            "VSTP-043",
            f"swallow-scan-gate total_matches fallback path={_normalize_diag_path(scan_path)}",
            once=False,
        )
        return None


def _read_json_dict_artifact(path: Path, *, tag: str, purpose: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # REASON: artifact read/parse fallback
        _log_swallow(
            tag,
            f"{purpose} parse fallback path={_normalize_diag_path(path)}",
            once=False,
        )
        return None
    if not isinstance(payload, dict):
        _log_swallow(
            tag,
            f"{purpose} root fallback path={_normalize_diag_path(path)}",
            once=False,
        )
        return None
    return payload


def _coerce_int_field(
    payload: dict[str, Any],
    field: str,
    *,
    default: int,
    tag: str,
    path: Path,
    purpose: str,
) -> int | None:
    try:
        return int(payload.get(field, default))
    except (TypeError, ValueError):  # REASON: artifact numeric coercion fallback
        _log_swallow(
            tag,
            f"{purpose} field={field} path={_normalize_diag_path(path)}",
            once=False,
        )
        return None


def _coerce_int(
    value: Any,
    field: str,
    *,
    tag: str,
    path: str | Path,
    purpose: str,
) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):  # REASON: artifact integer coercion fallback
        _log_swallow(
            tag,
            f"{purpose} field={field} path={_normalize_diag_path(path)}",
            once=False,
        )
        return None


def _coerce_float(
    value: Any,
    field: str,
    *,
    tag: str,
    path: str | Path,
    purpose: str,
) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):  # REASON: artifact numeric coercion fallback
        _log_swallow(
            tag,
            f"{purpose} field={field} path={_normalize_diag_path(path)}",
            once=False,
        )
        return None


def _coerce_xy_pair(
    payload: dict[str, Any],
    *,
    default: tuple[float, float],
    tag: str,
    path: str | Path,
    purpose: str,
) -> tuple[float, float]:
    values: list[float] = []
    for field, fallback in (("x", default[0]), ("y", default[1])):
        value = _coerce_float(
            payload.get(field, fallback),
            field,
            tag=tag,
            path=path,
            purpose=purpose,
        )
        if value is None:
            return default
        values.append(value)
    return values[0], values[1]



@dataclass(slots=True)
class VerifyStepContext:
    args: Any
    repo_root: Path
    pytest_args: list[str]
    artifacts_dir: Path | None
    artifacts_written: dict[str, str | None]
    no_index: bool
    write_scenes: Path | None
    write_worlds: Path | None
    suppress_stdout: Callable[..., Any]
    single_line_error: Callable[[str], str]
    normalize_path_for_json: Callable[..., str]
    pushd: Callable[..., Any]
    load_config: Callable[..., Any]
    validate_all: Any
    verify_demo: Any
    resolve_scene_paths: Callable[..., Any]
    generate_encounter_report: Callable[..., Any]
    inventory_list_scenes: Callable[..., Any]
    inventory_list_worlds: Callable[..., Any]
    run_verify_replays_summary: Callable[..., Any]
    evaluate_exception_budget_guard: Callable[..., Any]
    build_exception_budget_payload: Callable[..., Any]
    evaluate_pytest_fast_duration_guard: Callable[..., Any]
    default_transition_entity_id: Callable[..., Any]
    ensure_scene_transition_entity: Callable[..., Any]
    exception_budget_files: tuple[str, ...]
    steps: list[dict[str, Any]] = field(default_factory=list)
    pytest_fast_metrics: dict[str, float | bool | None] = field(
        default_factory=lambda: {"ok": None, "total": None, "top10": None}
    )
    pytest_fast_ran: bool = False
    exit_code: int = 0
    failure_seen: bool = False
    step_duration_rows: list[dict[str, object]] = field(default_factory=list)
    step_duration_total_ms: int = 0

    def add_step(self, name: str, code: int, *, error: str, artifact: str | None) -> None:
        self.steps.append(
            {
                "name": name,
                "ok": int(code) == 0,
                "code": int(code),
                "error": self.single_line_error(error),
                "artifact": artifact,
            }
        )

    def skipped_step(self, name: str) -> None:
        self.add_step(name, 2, error="skipped: previous step failed", artifact=None)


def run_verify_steps(state: VerifyStepContext) -> None:
    args = state.args
    repo_root = state.repo_root
    pytest_args = state.pytest_args
    artifacts_dir = state.artifacts_dir
    artifacts_written = state.artifacts_written
    no_index = state.no_index
    write_scenes = state.write_scenes
    write_worlds = state.write_worlds
    suppress_stdout = state.suppress_stdout
    _single_line_error = state.single_line_error
    _normalize_path_for_json = state.normalize_path_for_json
    _pushd = state.pushd
    load_config = state.load_config
    validate_all = state.validate_all
    verify_demo = state.verify_demo
    _resolve_scene_paths = state.resolve_scene_paths
    generate_encounter_report = state.generate_encounter_report
    _inventory_list_scenes = state.inventory_list_scenes
    _inventory_list_worlds = state.inventory_list_worlds
    _run_verify_replays_summary = state.run_verify_replays_summary
    _evaluate_exception_budget_guard = state.evaluate_exception_budget_guard
    _build_exception_budget_payload = state.build_exception_budget_payload
    _evaluate_pytest_fast_duration_guard = state.evaluate_pytest_fast_duration_guard
    _default_transition_entity_id = state.default_transition_entity_id
    _ensure_scene_transition_entity = state.ensure_scene_transition_entity
    _EXCEPTION_BUDGET_FILES = state.exception_budget_files
    _base_add_step = state.add_step

    steps = state.steps
    pytest_fast_metrics = state.pytest_fast_metrics
    pytest_fast_ran = state.pytest_fast_ran
    exit_code = state.exit_code
    failure_seen = state.failure_seen
    step_duration_rows = state.step_duration_rows
    step_duration_total_ms = int(state.step_duration_total_ms)
    _step_started_at = time.perf_counter()

    def _add_step(
        name: str,
        code: int,
        *,
        error: str,
        artifact: str | None,
    ) -> None:
        nonlocal _step_started_at, step_duration_total_ms
        is_skipped = int(code) == 2 and error == "skipped: previous step failed"
        if is_skipped:
            step_ms = 0
            step_ok = True
        else:
            step_ms = max(0, int((time.perf_counter() - _step_started_at) * 1000))
            step_ok = int(code) == 0
        step_duration_rows.append({"name": name, "ok": bool(step_ok), "ms": int(step_ms)})
        step_duration_total_ms += int(step_ms)
        _step_started_at = time.perf_counter()
        _base_add_step(name, code, error=error, artifact=artifact)

    def _skipped_step(name: str) -> None:
        _add_step(name, 2, error="skipped: previous step failed", artifact=None)
    with _pushd(repo_root):
        # Step 1: verify-demo (pytest)
        if pytest_args:
            err = verify_demo.validate_pytest_passthrough_args(pytest_args)
            if err:
                _add_step("verify-demo", 2, error="invalid pytest passthrough args", artifact=None)
                failure_seen = True
                exit_code = 2
        if not failure_seen:
            from types import ModuleType
            import engine.optional_arcade as optional_arcade

            arcade_module: ModuleType | Any | None = optional_arcade.arcade

            if arcade_module is None or bool(getattr(arcade_module, "__mesh_headless_stub__", False)):
                _add_step("verify-demo", 0, error="skipped: arcade not installed", artifact=None)
            else:
                try:
                    log_path = None
                    scratch_dir = None
                    if artifacts_dir is not None:
                        log_path = artifacts_dir / "verify_demo.log"
                        scratch_dir = artifacts_dir / "verify_demo_pytest"
                    with suppress_stdout():
                        if log_path is None:
                            code = int(verify_demo.run_verify_demo(pytest_args, capture_output=True, quiet=True))
                        else:
                            code = int(
                                verify_demo.run_verify_demo(
                                    pytest_args,
                                    capture_output=True,
                                    quiet=True,
                                    log_path=log_path,
                                    scratch_dir=scratch_dir,
                                )
                            )
                    error = "" if code == 0 else f"VDEMO-001 failed with code {code}"
                except Exception as exc:  # noqa: BLE001  # REASON: verify-demo step isolation
                    _log_swallow("VSTP-001", "verify-demo step isolation fallback", once=False)
                    code = 1
                    error = f"{type(exc).__name__}: {exc}"
                _add_step("verify-demo", code, error=error, artifact=None)
                if code != 0:
                    failure_seen = True
                    exit_code = 1 if code != 2 else 2

        # Step 2: verify-replays
        if failure_seen:
            _skipped_step("verify-replays")
        else:
            try:
                folder_path = repo_root / "replays"
                code, summary = _run_verify_replays_summary(folder_path)
                error = ""
                if code != 0:
                    raw_error = summary.get("error") if isinstance(summary, dict) else None
                    error = raw_error if isinstance(raw_error, str) and raw_error.strip() else f"failed with code {code}"

                artifact = None
                if artifacts_dir is not None and code == 0:
                    from engine.persistence_io import write_json_atomic

                    with suppress_stdout():
                        write_json_atomic(
                            artifacts_dir / "replays_summary.json",
                            summary,
                            indent=2,
                            sort_keys=True,
                            trailing_newline=True,
                        )
                    artifact = _normalize_path_for_json(artifacts_dir / "replays_summary.json", repo_root=repo_root)
                    artifacts_written["replays_summary"] = artifact

                _add_step("verify-replays", code, error=error, artifact=artifact)
                if code != 0:
                    failure_seen = True
                    exit_code = 1 if code != 2 else 2
            except Exception as exc:  # noqa: BLE001  # REASON: verify-replays step isolation
                _log_swallow("VSTP-002", "verify-replays step isolation fallback", once=False)
                _add_step("verify-replays", 1, error=f"{type(exc).__name__}: {exc}", artifact=None)
                failure_seen = True
                exit_code = 1

        # Step 3: verify-strict
        if failure_seen:
            _skipped_step("verify-strict")
        else:
            try:
                config = load_config()
                world_path = str(getattr(args, "world", "") or "").strip()
                if not world_path:
                    world_path = str(getattr(config, "world_file", "") or "").strip()
                if not world_path:
                    world_path = "worlds/main_world.json"
                with suppress_stdout():
                    code = int(validate_all.main([world_path, "--strict", "--schema-strict"]))
                error = "" if code == 0 else f"failed with code {code}"
            except Exception as exc:  # noqa: BLE001  # REASON: verify-strict step isolation
                _log_swallow("VSTP-003", "verify-strict step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
            _add_step("verify-strict", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 4: mypy-gate (ratchet against new typing errors)
        if failure_seen:
            _skipped_step("mypy-gate")
        else:
            try:
                from tooling import mypy_gate

                with suppress_stdout():
                    code = int(mypy_gate.main([]))
                error = "" if code == 0 else f"failed with code {code}"
            except ModuleNotFoundError as exc:
                if str(getattr(exc, "name", "")).startswith("tooling"):
                    code = 0
                    error = "skipped: tooling package unavailable"
                else:
                    raise
            except Exception as exc:  # noqa: BLE001  # REASON: mypy-gate step isolation
                _log_swallow("VSTP-004", "mypy-gate step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("mypy-gate", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 5: mypy-baseline-guard (prevent baseline growth)
        if failure_seen:
            _skipped_step("mypy-baseline-guard")
        else:
            try:
                from tooling import mypy_gate

                baseline_path = mypy_gate.BASELINE_PATH
                if baseline_path.exists():
                    raw = baseline_path.read_text(encoding="utf-8")
                    current_count = sum(1 for line in raw.splitlines() if line.strip())
                else:
                    current_count = 0

                metrics_path = repo_root / ".mesh" / "metrics" / "mypy_baseline_count.txt"
                metrics_path.parent.mkdir(parents=True, exist_ok=True)
                if metrics_path.exists():
                    previous_count = _read_mypy_baseline_count(metrics_path, current_count=current_count)
                else:
                    previous_count = current_count

                if current_count > previous_count:
                    code = 2
                    error = f"mypy baseline grew: {previous_count} -> {current_count}"
                else:
                    code = 0
                    error = ""
                    metrics_path.write_text(f"{current_count}\n", encoding="utf-8")
            except ModuleNotFoundError as exc:
                if str(getattr(exc, "name", "")).startswith("tooling"):
                    code = 0
                    error = "skipped: tooling package unavailable"
                else:
                    raise
            except Exception as exc:  # noqa: BLE001  # REASON: mypy-baseline-guard step isolation
                _log_swallow("VSTP-006", "mypy-baseline-guard step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("mypy-baseline-guard", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 6: ruff-gate (ratchet against new lint findings)
        if failure_seen:
            _skipped_step("ruff-gate")
        else:
            try:
                from tooling import ruff_gate

                with suppress_stdout():
                    code = int(ruff_gate.main([]))
                error = "" if code == 0 else f"failed with code {code}"
            except ModuleNotFoundError as exc:
                if str(getattr(exc, "name", "")).startswith("tooling"):
                    code = 0
                    error = "skipped: tooling package unavailable"
                else:
                    raise
            except Exception as exc:  # noqa: BLE001  # REASON: ruff-gate step isolation
                _log_swallow("VSTP-008", "ruff-gate step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("ruff-gate", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 7: mypy-island (strict typing on curated stable subsystems)
        if failure_seen:
            _skipped_step("mypy-island")
        else:
            try:
                from tooling import mypy_island

                with suppress_stdout():
                    code = int(mypy_island.main([]))
                error = "" if code == 0 else f"typed island failed with code {code}"
            except ModuleNotFoundError as exc:
                if str(getattr(exc, "name", "")).startswith("tooling"):
                    code = 0
                    error = "skipped: tooling package unavailable"
                else:
                    raise
            except Exception as exc:  # noqa: BLE001  # REASON: mypy-island step isolation
                _log_swallow("VSTP-007", "mypy-island step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("mypy-island", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 7: exception-budget-guard (growth-only broad exception budget)
        if failure_seen:
            _skipped_step("exception-budget-guard")
        else:
            try:
                baseline_path = repo_root / "tooling" / "metrics" / "exception_budget_count.txt"
                code, error, current, baseline, per_file = _evaluate_exception_budget_guard(repo_root, baseline_path)
                if artifacts_dir is not None:
                    from engine.persistence_io import write_json_atomic

                    budget_payload = {
                        **_build_exception_budget_payload(
                            ok=code == 0,
                            current_count=current,
                            baseline_count=baseline,
                            per_file_counts=per_file,
                            files_scanned=list(_EXCEPTION_BUDGET_FILES),
                        )
                    }
                    target = artifacts_dir / "exception_budget.json"
                    with suppress_stdout():
                        write_json_atomic(
                            target,
                            budget_payload,
                            indent=2,
                            sort_keys=True,
                            trailing_newline=True,
                        )
                    artifacts_written["exception_budget"] = _normalize_path_for_json(target, repo_root=repo_root)
            except Exception as exc:  # noqa: BLE001  # REASON: exception-budget-guard step isolation
                _log_swallow("VSTP-008", "exception-budget-guard step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("exception-budget-guard", code, error=error, artifact=artifacts_written.get("exception_budget"))
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 8: swallow-scan-gate (ban pass-only blanket swallows)
        if failure_seen:
            _skipped_step("swallow-scan-gate")
        else:
            artifact = None
            try:
                from tooling import find_blanket_swallow

                with suppress_stdout():
                    code = int(find_blanket_swallow.main(["--roots", "engine", "mesh_cli"]))

                scan_path = repo_root / "artifacts" / "swallow_scan.json"
                if scan_path.exists():
                    artifact = _normalize_path_for_json(scan_path, repo_root=repo_root)
                    artifacts_written["swallow_scan"] = artifact

                if code == 0:
                    error = ""
                else:
                    error = "pass-only blanket swallows found"
                    if scan_path.exists():
                        total_matches = _read_swallow_scan_total_matches(scan_path)
                        if total_matches is not None:
                            error = f"pass-only blanket swallows found: {total_matches}"
            except ModuleNotFoundError as exc:
                if str(getattr(exc, "name", "")).startswith("tooling"):
                    code = 0
                    error = "skipped: tooling package unavailable"
                else:
                    raise
            except Exception as exc:  # noqa: BLE001  # REASON: swallow-scan-gate step isolation
                _log_swallow("VSTP-044", "swallow-scan-gate step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("swallow-scan-gate", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 9: exception-policy-scan (BLE001 ratchet + silent broad catches)
        if failure_seen:
            _skipped_step("exception-policy-scan")
        else:
            artifact_ep = None
            try:
                from tooling import scan_exception_policies

                with suppress_stdout():
                    ep_result = scan_exception_policies.scan(
                        ["engine", "mesh_cli", "tooling"],
                        repo_root=repo_root,
                    )

                if artifacts_dir is not None:
                    import json as _json_ep

                    ep_target = artifacts_dir / "exception_policy_scan.json"
                    ep_target.parent.mkdir(parents=True, exist_ok=True)
                    ep_target.write_text(
                        _json_ep.dumps(ep_result, indent=2, sort_keys=False) + "\n",
                        encoding="utf-8",
                    )
                    artifact_ep = _normalize_path_for_json(ep_target, repo_root=repo_root)
                    artifacts_written["exception_policy_scan"] = artifact_ep

                # --- Ratchet: BLE001 cap ---
                baseline_path_ep = repo_root / "tooling" / "exception_policy_baseline.json"
                if baseline_path_ep.exists():
                    bl = _read_json_dict_artifact(
                        baseline_path_ep,
                        tag="VSTP-048",
                        purpose="exception-policy-scan baseline",
                    )
                    if bl is None:
                        code = 1
                        error = "invalid exception_policy_baseline.json"
                    else:
                        bl_ble001 = _coerce_int_field(
                            bl,
                            "ble001_count_total",
                            default=0,
                            tag="VSTP-048",
                            path=baseline_path_ep,
                            purpose="exception-policy-scan baseline coercion fallback",
                        )
                        bl_silent = _coerce_int_field(
                            bl,
                            "silent_broad_catch_count_total",
                            default=0,
                            tag="VSTP-048",
                            path=baseline_path_ep,
                            purpose="exception-policy-scan baseline coercion fallback",
                        )
                        bl_silent_max = _coerce_int_field(
                            bl,
                            "silent_broad_catch_max",
                            default=bl_silent if bl_silent is not None else 0,
                            tag="VSTP-048",
                            path=baseline_path_ep,
                            purpose="exception-policy-scan baseline coercion fallback",
                        )
                        bl_ble001_missing_reason_max = _coerce_int_field(
                            bl,
                            "ble001_missing_reason_max",
                            default=999999,
                            tag="VSTP-048",
                            path=baseline_path_ep,
                            purpose="exception-policy-scan baseline coercion fallback",
                        )
                        cur_ble001 = int(ep_result.get("ble001_count_total", 0))
                        cur_silent = int(ep_result.get("silent_broad_catch_count_total", 0))
                        cur_ble001_missing_reason = int(
                            ep_result.get(
                                "missing_ble001_reason_total",
                                ep_result.get("ble001_missing_reason_count", 0),
                            )
                        )

                        if None in (bl_ble001, bl_silent, bl_silent_max, bl_ble001_missing_reason_max):
                            code = 1
                            error = "invalid exception_policy_baseline.json"
                        else:
                            baseline_ble001 = cast(int, bl_ble001)
                            baseline_silent_max = cast(int, bl_silent_max)
                            baseline_missing_reason_max = cast(int, bl_ble001_missing_reason_max)
                            violations: list[str] = []
                            if cur_ble001 > baseline_ble001:
                                violations.append(
                                    f"BLE001 grew: {baseline_ble001} -> {cur_ble001}"
                                )
                            if cur_silent > baseline_silent_max:
                                violations.append(
                                    f"silent broad catches ({cur_silent}) exceed max ({baseline_silent_max})"
                                )
                            if cur_ble001_missing_reason > baseline_missing_reason_max:
                                violations.append(
                                    f"BLE001 missing REASON annotations ({cur_ble001_missing_reason}) exceed max ({baseline_missing_reason_max})"
                                )
                            if cur_ble001_missing_reason > 0:
                                get_logger(__name__).info(scan_exception_policies._format_missing_ble001_reason_log(ep_result, limit=5))
                            if violations:
                                code = 1
                                error = "; ".join(violations)
                            else:
                                code = 0
                                error = ""
                else:
                    # No baseline yet → pass but warn
                    code = 0
                    error = ""

            except ModuleNotFoundError as exc:
                if str(getattr(exc, "name", "")).startswith("tooling"):
                    code = 0
                    error = "skipped: tooling package unavailable"
                else:
                    raise
            except Exception as exc:  # noqa: BLE001  # REASON: exception-policy-scan step isolation
                _log_swallow("VSTP-045", "exception-policy-scan step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("exception-policy-scan", code, error=error, artifact=artifact_ep)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 10: pytest-fast (exclude slow/e2e tests for local sanity)
        if failure_seen:
            _skipped_step("pytest-fast")
        else:
            try:
                import os
                import subprocess
                import sys

                if (
                    os.getenv("PYTEST_CURRENT_TEST")
                    or os.getenv("MESH_SKIP_PYTEST_FAST") == "1"
                    or "pytest" in sys.modules
                ):
                    code = 0
                    error = "skipped: running under pytest"
                    pytest_fast_ran = False
                elif importlib.util.find_spec("tooling.pytest_fast") is None:
                    code = 0
                    error = "skipped: tooling package unavailable"
                    pytest_fast_ran = False
                else:
                    _cleanup_stale_pytest_fast_budget_artifacts(
                        repo_root,
                        artifacts_dir=artifacts_dir,
                    )
                    metrics_dir = repo_root / ".mesh" / "metrics"
                    metrics_dir.mkdir(parents=True, exist_ok=True)
                    durations_path = metrics_dir / "pytest_durations_fast.json"
                    cmd = [
                        sys.executable,
                        "-m",
                        "tooling.pytest_fast",
                        "--write-durations",
                        str(durations_path),
                    ]
                    with suppress_stdout():
                        pytest_result = subprocess.run(cmd, capture_output=True, text=True)
                    code = int(pytest_result.returncode)
                    error = "" if code == 0 else f"failed with code {code}"
                    pytest_fast_ran = True
            except Exception as exc:  # noqa: BLE001  # REASON: pytest-fast step isolation
                _log_swallow("VSTP-009", "pytest-fast step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("pytest-fast", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 10: pytest-fast-duration-guard (ratchet against slowdowns)
        if failure_seen:
            _skipped_step("pytest-fast-duration-guard")
        elif not pytest_fast_ran:
            _add_step("pytest-fast-duration-guard", 0, error="skipped: pytest-fast not run", artifact=None)
        else:
            try:
                metrics_dir = repo_root / ".mesh" / "metrics"
                durations_path = metrics_dir / "pytest_durations_fast.json"
                total_baseline_path = metrics_dir / "pytest_fast_total_seconds.txt"
                top10_baseline_path = metrics_dir / "pytest_fast_top10_seconds.txt"

                code, error, total_seconds, top10_seconds, ok = _evaluate_pytest_fast_duration_guard(
                    durations_path, total_baseline_path, top10_baseline_path
                )
                pytest_fast_metrics["total"] = total_seconds
                pytest_fast_metrics["top10"] = top10_seconds
                pytest_fast_metrics["ok"] = ok
            except Exception as exc:  # noqa: BLE001  # REASON: pytest-fast-duration-guard step isolation
                _log_swallow("VSTP-010", "pytest-fast-duration-guard step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                pytest_fast_metrics["ok"] = False

            _add_step("pytest-fast-duration-guard", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 11: runtime-player-smoke (runtime-only CI smoke)
        if failure_seen:
            _skipped_step("runtime-player-smoke")
        else:
            try:
                import subprocess
                import sys

                smoke_scene: str | None = None
                smoke_candidates: list[str] = ["scenes/runtime_smoke_scene.json", "scenes/main.json"]
                try:
                    cfg = load_config()
                    cfg_scene = str(getattr(cfg, "start_scene", "") or "").strip()
                    if cfg_scene:
                        smoke_candidates.append(cfg_scene)
                except (AttributeError, OSError):  # REASON: runtime-player-smoke config fallback
                    _log_swallow(
                        "VSTP-011",
                        "runtime-player-smoke config/start_scene fallback",
                        once=False,
                    )
                seen_candidates: set[str] = set()
                for candidate in smoke_candidates:
                    if candidate in seen_candidates:
                        continue
                    seen_candidates.add(candidate)
                    if (repo_root / candidate).exists():
                        smoke_scene = candidate
                        break

                runtime_smoke_artifact: str | None = None
                if smoke_scene:
                    cmd = [sys.executable, "-m", "mesh_cli", "play-runtime", "--headless-smoke"]
                    cmd.extend(["--smoke-scene", smoke_scene])
                    if artifacts_dir is not None:
                        runtime_smoke_artifact = _normalize_path_for_json(
                            artifacts_dir / "runtime_smoke.json", repo_root=repo_root
                        )
                        artifacts_written["runtime_smoke"] = runtime_smoke_artifact
                        artifacts_written["runtime_diagnostics_snapshot"] = _normalize_path_for_json(
                            artifacts_dir / "runtime_diagnostics_snapshot.json",
                            repo_root=repo_root,
                        )
                        cmd.extend(["--smoke-artifact", str(artifacts_dir / "runtime_smoke.json")])
                        cmd.extend(["--diagnostics-artifact", str(artifacts_dir / "runtime_diagnostics_snapshot.json")])
                    with suppress_stdout():
                        smoke_result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
                    code = int(smoke_result.returncode)
                    error = "" if code == 0 else f"failed with code {code}"
                else:
                    code = 0
                    error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: runtime-player-smoke step isolation
                _log_swallow("VSTP-012", "runtime-player-smoke step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                runtime_smoke_artifact = None

            _add_step("runtime-player-smoke", code, error=error, artifact=runtime_smoke_artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 11: player-package-gate (deterministic runtime-only package + smoke)
        if failure_seen:
            _skipped_step("player-package-gate")
        else:
            try:
                import json
                import subprocess
                import sys

                has_packaging_sources = bool((repo_root / "engine").is_dir() and (repo_root / "mesh_cli").is_dir())
                has_smoke_scene = bool((repo_root / "scenes" / "runtime_smoke_scene.json").is_file())
                if not has_packaging_sources or not has_smoke_scene:
                    code = 0
                    error = ""
                else:
                    package_root = (artifacts_dir / "player_pkg") if artifacts_dir is not None else (repo_root / ".mesh" / "player_pkg")
                    manifest_path = package_root / "manifest.json"
                    cmd = [
                        sys.executable,
                        "-m",
                        "mesh_cli",
                        "package-player",
                        "--out",
                        str(package_root),
                        "--manifest",
                        str(manifest_path),
                        "--smoke",
                        "--diagnostics-artifact",
                        str(package_root / "runtime_diagnostics_snapshot.json"),
                    ]
                    with suppress_stdout():
                        package_result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
                    code = int(package_result.returncode)
                    error = "" if code == 0 else f"failed with code {code}"
                    if code == 0:
                        check_path = package_root / "package_check.json"
                        if not check_path.exists():
                            code = 1
                            error = "missing package_check.json"
                        else:
                            check_payload = _read_json_dict_artifact(
                                check_path,
                                tag="VSTP-049",
                                purpose="player-package-gate package_check",
                            )
                            if check_payload is None:
                                code = 1
                                error = "invalid package_check.json payload"
                            elif not bool(check_payload.get("ok", False)):
                                code = 1
                                error = "package_check reported failure"
                    if code == 0 and artifacts_dir is not None:
                        artifacts_written["player_package_manifest"] = _normalize_path_for_json(
                            package_root / "manifest.json",
                            repo_root=repo_root,
                        )
                        artifacts_written["player_package_check"] = _normalize_path_for_json(
                            package_root / "package_check.json",
                            repo_root=repo_root,
                        )
                        artifacts_written["player_package_runtime_smoke"] = _normalize_path_for_json(
                            package_root / "runtime_smoke.json",
                            repo_root=repo_root,
                        )
                        artifacts_written["player_package_runtime_diagnostics_snapshot"] = _normalize_path_for_json(
                            package_root / "runtime_diagnostics_snapshot.json",
                            repo_root=repo_root,
                        )
            except Exception as exc:  # noqa: BLE001  # REASON: player-package-gate step isolation
                _log_swallow("VSTP-013", "player-package-gate step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step(
                "player-package-gate",
                code,
                error=error,
                artifact=artifacts_written.get("player_package_check"),
            )
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 12: web-smoke (build web output, then validate layout deterministically)
        if failure_seen:
            _skipped_step("web-smoke")
        else:
            try:
                import subprocess
                import sys

                artifact = None
                has_web_target = bool((repo_root / "web_main.py").is_file() and (repo_root / "pygbag.toml").is_file())
                if bool(getattr(args, "skip_web_smoke", False)):
                    code = 0
                    error = "skipped: disabled by args"
                elif artifacts_dir is None:
                    code = 0
                    error = "skipped: artifacts directory required"
                elif not has_web_target:
                    code = 0
                    error = "skipped: web target unavailable"
                else:
                    from mesh_cli.web_smoke import run_web_smoke

                    web_build_dir = artifacts_dir / "web_build"
                    web_smoke_path = artifacts_dir / "web_smoke.json"
                    build_cmd = [
                        sys.executable,
                        "-m",
                        "mesh_cli",
                        "build-web",
                        "--out",
                        str(web_build_dir),
                    ]
                    with suppress_stdout():
                        build_result = subprocess.run(build_cmd, capture_output=True, text=True, cwd=str(repo_root))
                    smoke_code = int(
                        run_web_smoke(
                            build_dir=web_build_dir.as_posix(),
                            artifact_path=web_smoke_path.as_posix(),
                        )
                    )
                    if web_smoke_path.exists():
                        artifact = _normalize_path_for_json(web_smoke_path, repo_root=repo_root)
                        artifacts_written["web_smoke"] = artifact
                    build_code = int(build_result.returncode)
                    if build_code != 0:
                        code = build_code
                        error = f"build-web failed with code {build_code}"
                    elif smoke_code != 0:
                        code = smoke_code
                        error = f"web-smoke failed with code {smoke_code}"
                    else:
                        code = 0
                        error = ""
            except _VERIFY_WEB_GATE_EXCEPTIONS as exc:
                _log_swallow("VSTP-046", "web gate fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                artifact = artifacts_written.get("web_smoke")

            _add_step("web-smoke", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 13: perf-baseline-compare
        if failure_seen:
            _skipped_step("perf-baseline-compare")
        else:
            try:
                from engine.persistence_io import write_json_atomic
                from engine.tooling.perf_baselines import compare_perf_run_to_baseline
                from engine.tooling.perf_baselines import load_perf_baseline
                from engine.tooling.perf_baselines import run_perf_scene_capture

                scene_set_path = repo_root / "tooling" / "perf_baselines" / "scenes.json"
                baseline_path = repo_root / "tooling" / "perf_baselines" / "baselines.json"
                if scene_set_path.exists() and baseline_path.exists():
                    with suppress_stdout():
                        perf_run_payload = run_perf_scene_capture(
                            scene_set_path=scene_set_path,
                            ticks=120,
                        )
                    baseline_payload = load_perf_baseline(baseline_path)
                    perf_compare_payload = compare_perf_run_to_baseline(
                        run_payload=perf_run_payload,
                        baseline_payload=baseline_payload,
                    )
                    regressions = perf_compare_payload.get("regressions", [])
                    has_regressions = isinstance(regressions, list) and len(regressions) > 0
                    code = 1 if has_regressions else 0
                    if has_regressions:
                        first = regressions[0] if isinstance(regressions[0], dict) else {}
                        error = (
                            f"regression: {first.get('scene_id')} {first.get('metric')} "
                            f"{first.get('baseline')} -> {first.get('current')}"
                        )
                    else:
                        error = ""

                    if artifacts_dir is not None:
                        target_run = artifacts_dir / "perf_run.json"
                        target_compare = artifacts_dir / "perf_compare.json"
                        with suppress_stdout():
                            write_json_atomic(
                                target_run,
                                perf_run_payload,
                                indent=2,
                                sort_keys=True,
                                trailing_newline=True,
                            )
                            write_json_atomic(
                                target_compare,
                                perf_compare_payload,
                                indent=2,
                                sort_keys=True,
                                trailing_newline=True,
                            )
                        artifacts_written["perf_run"] = _normalize_path_for_json(target_run, repo_root=repo_root)
                        artifacts_written["perf_compare"] = _normalize_path_for_json(target_compare, repo_root=repo_root)
                else:
                    code = 0
                    error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: perf-baseline-compare step isolation
                _log_swallow("VSTP-014", "perf-baseline-compare step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step(
                "perf-baseline-compare",
                code,
                error=error,
                artifact=artifacts_written.get("perf_compare"),
            )
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 14: world-progression-check (start -> key milestones)
        if failure_seen:
            _skipped_step("world-progression-check")
        else:
            try:
                import json

                from engine.paths import resolve_path
                from engine.tooling.world_progression import check_world_progression, world_progression_result_to_payload

                with suppress_stdout():
                    config = load_config()
                    world_path = str(getattr(args, "world", "") or "").strip()
                    if not world_path:
                        world_path = str(getattr(config, "world_file", "") or "").strip()
                    if not world_path:
                        world_path = "worlds/main_world.json"

                    required_paths: tuple[str, ...] = ()
                    world_file = resolve_path(world_path)
                    if world_file.exists():
                        config_payload = _read_json_dict_artifact(
                            world_file,
                            tag="VSTP-015",
                            purpose="world-progression-check config",
                        ) or {}
                        configured = config_payload.get("progression_required_scene_paths")
                        if isinstance(configured, list):
                            required_paths = tuple(str(p) for p in configured if isinstance(p, str) and p.strip())

                    result = check_world_progression(
                        world_path,
                        required_scene_paths=required_paths,
                    )
                    payload = world_progression_result_to_payload(result)

                code = 0 if bool(payload.get("ok")) else 1
                if code == 0:
                    error = ""
                else:
                    missing = payload.get("missing_scene_paths") or []
                    missing_text = ", ".join(str(x) for x in missing) if isinstance(missing, list) else str(missing)
                    error = f"missing required reachable scenes: {missing_text}"
            except Exception as exc:  # noqa: BLE001  # REASON: world-progression-check step isolation
                _log_swallow("VSTP-016", "world-progression-check step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("world-progression-check", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 9: spawn-placeholder-safety (theme_enemy_placeholder safety guard)
        if failure_seen:
            _skipped_step("spawn-placeholder-safety")
        else:
            try:
                from engine.validators.spawn_placeholder_safety_validator import validate_spawn_placeholder_safety

                with suppress_stdout():
                    config = load_config()
                    world_path = str(getattr(args, "world", "") or "").strip()
                    if not world_path:
                        world_path = str(getattr(config, "world_file", "") or "").strip()
                    if not world_path:
                        world_path = "worlds/main_world.json"

                    scene_paths = _resolve_scene_paths(world_path)
                    safety_payload = validate_spawn_placeholder_safety(scene_paths, min_dist=48.0)

                code = 0 if bool(safety_payload.get("ok")) else 1
                if code == 0:
                    error = ""
                else:
                    safety_issues = safety_payload.get("issues") or []
                    if isinstance(safety_issues, list) and safety_issues and isinstance(safety_issues[0], dict):
                        first_issue = safety_issues[0]
                        scene = str(first_issue.get("scene_path") or "")
                        pid = str(first_issue.get("placeholder_id") or "")
                        reason = str(first_issue.get("reason") or "")
                        target_id = str(first_issue.get("offending_target_id") or "")
                        dist = first_issue.get("distance")
                        dist_text = f"{float(dist):.2f}" if isinstance(dist, (int, float)) else "?"
                        error = f"{scene} {pid} {reason} target={target_id} dist={dist_text}"
                    else:
                        error = "spawn-placeholder-safety found errors"
            except Exception as exc:  # noqa: BLE001  # REASON: spawn-placeholder-safety step isolation
                _log_swallow("VSTP-017", "spawn-placeholder-safety step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("spawn-placeholder-safety", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 6: stamp-audit (optional curated stamp dry-run reports)
        if failure_seen:
            _skipped_step("stamp-audit")
        else:
            try:
                import json

                from engine.paths import resolve_path
                from engine.persistence_io import write_json_atomic
                from engine.tooling_runtime.stamp_report import StampReportError, compute_scene_stamp_report

                config = load_config()
                world_path = str(getattr(args, "world", "") or "").strip()
                if not world_path:
                    world_path = str(getattr(config, "world_file", "") or "").strip()
                if not world_path:
                    world_path = "worlds/main_world.json"

                stamp_cases_raw: list[dict[str, Any]] = []
                world_file = resolve_path(world_path)
                if world_file.exists():
                    stamp_world_data = _read_json_dict_artifact(
                        world_file,
                        tag="VSTP-018",
                        purpose="stamp-audit config",
                    ) or {}
                    configured = stamp_world_data.get("stamp_audit_cases")
                    if isinstance(configured, list):
                        for idx, entry in enumerate(configured):
                            if not isinstance(entry, dict):
                                continue
                            scene_path = entry.get("scene_path")
                            stamp_path = entry.get("stamp_path")
                            origin = entry.get("origin")
                            id_prefix = entry.get("id_prefix")
                            if not (
                                isinstance(scene_path, str)
                                and scene_path.strip()
                                and isinstance(stamp_path, str)
                                and stamp_path.strip()
                                and isinstance(origin, dict)
                                and isinstance(origin.get("x"), int)
                                and isinstance(origin.get("y"), int)
                            ):
                                raise StampReportError(
                                    f"invalid stamp_audit_cases[{idx}] (expected scene_path/stamp_path/origin.x/origin.y)",
                                    exit_code=1,
                                )
                            if not isinstance(id_prefix, str) or not id_prefix.strip():
                                id_prefix = "audit"
                            origin_x = _coerce_int(
                                origin["x"],
                                "origin_x",
                                tag="VSTP-018",
                                path=world_file,
                                purpose=f"stamp-audit origin coercion fallback case={idx}",
                            )
                            origin_y = _coerce_int(
                                origin["y"],
                                "origin_y",
                                tag="VSTP-018",
                                path=world_file,
                                purpose=f"stamp-audit origin coercion fallback case={idx}",
                            )
                            if origin_x is None or origin_y is None:
                                raise StampReportError(
                                    f"invalid stamp_audit_cases[{idx}] (expected scene_path/stamp_path/origin.x/origin.y)",
                                    exit_code=1,
                                )
                            stamp_cases_raw.append(
                                {
                                    "scene_path": str(scene_path).strip(),
                                    "stamp_path": str(stamp_path).strip(),
                                    "origin_x": origin_x,
                                    "origin_y": origin_y,
                                    "id_prefix": str(id_prefix).strip(),
                                }
                            )

                stamp_cases_raw.sort(
                    key=lambda c: (
                        str(c.get("scene_path") or ""),
                        str(c.get("stamp_path") or ""),
                        int(c.get("origin_x") or 0),
                        int(c.get("origin_y") or 0),
                        str(c.get("id_prefix") or ""),
                    )
                )

                stamp_out_cases: list[dict[str, Any]] = []
                for case in stamp_cases_raw:
                    scene_path_display = str(case["scene_path"])
                    stamp_path_raw = str(case["stamp_path"])

                    resolved_scene = resolve_path(scene_path_display)
                    if not resolved_scene.exists():
                        raise StampReportError(f"scene not found: {scene_path_display}")
                    resolved_stamp = resolve_path(stamp_path_raw)
                    if not resolved_stamp.exists():
                        raise StampReportError(f"stamp not found: {stamp_path_raw}")

                    raw_scene = _read_json_dict_artifact(
                        resolved_scene,
                        tag="VSTP-019",
                        purpose="stamp-audit scene",
                    )
                    if raw_scene is None:
                        raise StampReportError(f"failed to parse scene JSON: {scene_path_display}")

                    stamp = _read_json_dict_artifact(
                        resolved_stamp,
                        tag="VSTP-020",
                        purpose="stamp-audit stamp",
                    )
                    if stamp is None:
                        raise StampReportError(f"failed to parse stamp JSON: {stamp_path_raw}")

                    raw_scene["_mesh_source_path"] = scene_path_display
                    stamp["_mesh_source_path"] = stamp_path_raw

                    origin_x = _coerce_int(
                        case["origin_x"],
                        "origin_x",
                        tag="VSTP-018",
                        path=stamp_path_raw,
                        purpose="stamp-audit origin coercion fallback case_path",
                    )
                    origin_y = _coerce_int(
                        case["origin_y"],
                        "origin_y",
                        tag="VSTP-018",
                        path=stamp_path_raw,
                        purpose="stamp-audit origin coercion fallback case_path",
                    )
                    if origin_x is None or origin_y is None:
                        raise StampReportError(
                            f"invalid stamp origin for {stamp_path_raw}",
                            exit_code=1,
                        )

                    stamp_report = compute_scene_stamp_report(
                        raw_scene,
                        stamp,
                        origin_x,
                        origin_y,
                        str(case["id_prefix"]),
                    )
                    tile_changes = list(stamp_report.get("tile_changes") or [])
                    entity_changes = list(stamp_report.get("entity_changes") or [])
                    stamp_out_cases.append(
                        {
                            "scene_path": stamp_report.get("scene_path"),
                            "stamp_path": stamp_report.get("stamp_path"),
                            "origin": stamp_report.get("origin"),
                            "id_prefix": str(case["id_prefix"]),
                            "tile_change_count": int(len(tile_changes)),
                            "entity_change_count": int(len(entity_changes)),
                            "tile_changes": tile_changes[:200],
                            "entity_changes": entity_changes,
                        }
                    )

                stamp_audit_payload = {"ok": True, "case_count": int(len(stamp_out_cases)), "cases": stamp_out_cases}

                artifact = None
                if artifacts_dir is not None:
                    with suppress_stdout():
                        write_json_atomic(
                            artifacts_dir / "stamp_audit.json",
                            stamp_audit_payload,
                            indent=2,
                            sort_keys=True,
                            trailing_newline=True,
                        )
                    artifact = _normalize_path_for_json(artifacts_dir / "stamp_audit.json", repo_root=repo_root)
                    artifacts_written["stamp_audit"] = artifact

                code = 0
                error = ""
            except StampReportError as exc:
                code = exc.exit_code
                error = exc.message
                artifact = None
            except Exception as exc:  # noqa: BLE001  # REASON: stamp-audit step isolation
                _log_swallow("VSTP-021", "stamp-audit step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                artifact = None

            _add_step("stamp-audit", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 7: brush-audit (optional curated brush dry-run reports)
        if failure_seen:
            _skipped_step("brush-audit")
        else:
            try:
                import json

                from engine.paths import resolve_path
                from engine.persistence_io import write_json_atomic
                from engine.tooling_runtime.brush_report import BrushReportError, compute_scene_brush_report
                from engine.tilemap_brush import Anchor

                config = load_config()
                world_path = str(getattr(args, "world", "") or "").strip()
                if not world_path:
                    world_path = str(getattr(config, "world_file", "") or "").strip()
                if not world_path:
                    world_path = "worlds/main_world.json"

                brush_cases_raw: list[dict[str, Any]] = []
                world_file = resolve_path(world_path)
                if world_file.exists():
                    brush_world_data = _read_json_dict_artifact(
                        world_file,
                        tag="VSTP-022",
                        purpose="brush-audit config",
                    ) or {}
                    configured = brush_world_data.get("brush_audit_cases")
                    if isinstance(configured, list):
                        for idx, entry in enumerate(configured):
                            if not isinstance(entry, dict):
                                continue
                            scene_path = entry.get("scene_path")
                            brush_path = entry.get("brush_path")
                            origin = entry.get("origin")
                            layer_id = entry.get("layer_id")
                            anchor = entry.get("anchor", "tl")
                            clip = entry.get("clip", False)
                            if not (
                                isinstance(scene_path, str)
                                and scene_path.strip()
                                and isinstance(brush_path, str)
                                and brush_path.strip()
                                and isinstance(origin, dict)
                                and isinstance(origin.get("x"), int)
                                and isinstance(origin.get("y"), int)
                                and isinstance(layer_id, str)
                                and layer_id.strip()
                            ):
                                raise BrushReportError(
                                    f"invalid brush_audit_cases[{idx}] (expected scene_path/brush_path/layer_id/origin.x/origin.y)",
                                    exit_code=1,
                                )
                            origin_x = _coerce_int(
                                origin["x"],
                                "origin_x",
                                tag="VSTP-022",
                                path=world_file,
                                purpose=f"brush-audit origin coercion fallback case={idx}",
                            )
                            origin_y = _coerce_int(
                                origin["y"],
                                "origin_y",
                                tag="VSTP-022",
                                path=world_file,
                                purpose=f"brush-audit origin coercion fallback case={idx}",
                            )
                            if origin_x is None or origin_y is None:
                                raise BrushReportError(
                                    f"invalid brush_audit_cases[{idx}] (expected scene_path/brush_path/layer_id/origin.x/origin.y)",
                                    exit_code=1,
                                )
                            brush_cases_raw.append(
                                {
                                    "scene_path": str(scene_path).strip(),
                                    "brush_path": str(brush_path).strip(),
                                    "layer_id": str(layer_id).strip(),
                                    "origin_x": origin_x,
                                    "origin_y": origin_y,
                                    "anchor": str(anchor or "tl").strip().lower(),
                                    "clip": bool(clip),
                                }
                            )

                brush_cases_raw.sort(
                    key=lambda c: (
                        str(c.get("scene_path") or ""),
                        str(c.get("brush_path") or ""),
                        str(c.get("layer_id") or ""),
                        int(c.get("origin_x") or 0),
                        int(c.get("origin_y") or 0),
                        str(c.get("anchor") or ""),
                    )
                )

                def _coerce_brush_anchor(value: Any) -> Anchor:
                    anchor_text = str(value or "tl").strip().lower()
                    return "center" if anchor_text == "center" else "tl"

                brush_out_cases: list[dict[str, Any]] = []
                for case in brush_cases_raw:
                    scene_path_display = str(case["scene_path"])
                    brush_path_raw = str(case["brush_path"])

                    resolved_scene = resolve_path(scene_path_display)
                    if not resolved_scene.exists():
                        raise BrushReportError(f"scene not found: {scene_path_display}")
                    resolved_brush = resolve_path(brush_path_raw)
                    if not resolved_brush.exists():
                        raise BrushReportError(f"brush not found: {brush_path_raw}")

                    raw_scene = _read_json_dict_artifact(
                        resolved_scene,
                        tag="VSTP-023",
                        purpose="brush-audit scene",
                    )
                    if raw_scene is None:
                        raise BrushReportError(f"failed to parse scene JSON: {scene_path_display}")

                    raw_brush = _read_json_dict_artifact(
                        resolved_brush,
                        tag="VSTP-024",
                        purpose="brush-audit brush",
                    )
                    if raw_brush is None:
                        raise BrushReportError(f"failed to parse brush JSON: {brush_path_raw}")

                    raw_scene["_mesh_source_path"] = scene_path_display
                    raw_brush["_mesh_source_path"] = brush_path_raw

                    origin_x = _coerce_int(
                        case["origin_x"],
                        "origin_x",
                        tag="VSTP-022",
                        path=brush_path_raw,
                        purpose="brush-audit origin coercion fallback case_path",
                    )
                    origin_y = _coerce_int(
                        case["origin_y"],
                        "origin_y",
                        tag="VSTP-022",
                        path=brush_path_raw,
                        purpose="brush-audit origin coercion fallback case_path",
                    )
                    if origin_x is None or origin_y is None:
                        raise BrushReportError(
                            f"invalid brush origin for {brush_path_raw}",
                            exit_code=1,
                        )

                    brush_report = compute_scene_brush_report(
                        raw_scene,
                        raw_brush,
                        origin_x=origin_x,
                        origin_y=origin_y,
                        layer_id=str(case["layer_id"]),
                        anchor=_coerce_brush_anchor(case.get("anchor")),
                        clip=bool(case["clip"]),
                    )
                    tile_changes = list(brush_report.get("tile_changes") or [])
                    brush_out_cases.append(
                        {
                            "scene_path": brush_report.get("scene_path"),
                            "brush_path": brush_report.get("brush_path"),
                            "layer_id": brush_report.get("layer_id"),
                            "origin": brush_report.get("origin"),
                            "anchor": str(case["anchor"] or "tl"),
                            "clip": bool(case["clip"]),
                            "tile_change_count": int(len(tile_changes)),
                            "tile_changes": tile_changes[:200],
                        }
                    )

                brush_audit_payload = {"ok": True, "case_count": int(len(brush_out_cases)), "cases": brush_out_cases}

                artifact = None
                if artifacts_dir is not None:
                    with suppress_stdout():
                        write_json_atomic(
                            artifacts_dir / "brush_audit.json",
                            brush_audit_payload,
                            indent=2,
                            sort_keys=True,
                            trailing_newline=True,
                        )
                    artifact = _normalize_path_for_json(artifacts_dir / "brush_audit.json", repo_root=repo_root)
                    artifacts_written["brush_audit"] = artifact

                code = 0
                error = ""
            except BrushReportError as exc:
                code = exc.exit_code
                error = exc.message
                artifact = None
            except Exception as exc:  # noqa: BLE001  # REASON: brush-audit step isolation
                _log_swallow("VSTP-025", "brush-audit step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                artifact = None

            _add_step("brush-audit", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 8: macro-audit (optional curated macro dry-run reports)
        if failure_seen:
            _skipped_step("macro-audit")
        else:
            try:
                import json

                from engine.paths import resolve_path
                from engine.persistence_io import write_json_atomic
                from engine.scene_controller import SceneController
                from engine.tooling_runtime.macro_assets import load_macro_asset, parse_macro_asset, validate_macro_asset

                config = load_config()
                world_path = str(getattr(args, "world", "") or "").strip()
                if not world_path:
                    world_path = str(getattr(config, "world_file", "") or "").strip()
                if not world_path:
                    world_path = "worlds/main_world.json"

                macro_cases_raw: list[dict[str, Any]] = []
                world_file = resolve_path(world_path)
                if world_file.exists():
                    macro_world_data = _read_json_dict_artifact(
                        world_file,
                        tag="VSTP-026",
                        purpose="macro-audit config",
                    ) or {}
                    configured = macro_world_data.get("macro_audit_cases")
                    if isinstance(configured, list):
                        for idx, entry in enumerate(configured):
                            if not isinstance(entry, dict):
                                continue
                            scene_path = entry.get("scene_path")
                            macro_path = entry.get("macro_path")
                            args_payload = entry.get("args")
                            if not (
                                isinstance(scene_path, str)
                                and scene_path.strip()
                                and isinstance(macro_path, str)
                                and macro_path.strip()
                                and isinstance(args_payload, dict)
                            ):
                                raise ValueError(
                                    f"invalid macro_audit_cases[{idx}] (expected scene_path/macro_path/args object)"
                                )
                            macro_cases_raw.append(
                                {
                                    "scene_path": str(scene_path).strip(),
                                    "macro_path": str(macro_path).strip(),
                                    "args": dict(args_payload),
                                }
                            )

                macro_cases_raw.sort(
                    key=lambda c: (
                        str(c.get("scene_path") or ""),
                        str(c.get("macro_path") or ""),
                        json.dumps(c.get("args") or {}, sort_keys=True),
                    )
                )

                def _find_player_pos(scene_payload: dict[str, Any], *, scene_path: str) -> tuple[float, float]:
                    entities = scene_payload.get("entities")
                    if isinstance(entities, list):
                        for e in entities:
                            if not isinstance(e, dict):
                                continue
                            pid = e.get("prefab_id")
                            tags = e.get("tags")
                            if pid == "player" or (isinstance(tags, list) and "player" in tags):
                                return _coerce_xy_pair(
                                    e,
                                    default=(0.0, 0.0),
                                    tag="VSTP-027",
                                    path=scene_path,
                                    purpose="macro-audit player position coercion fallback entity=player",
                                )
                    return 0.0, 0.0

                macro_out_cases: list[dict[str, Any]] = []
                for case in macro_cases_raw:
                    scene_path_raw = str(case["scene_path"])
                    macro_path_raw = str(case["macro_path"])
                    args_payload_obj = case.get("args")
                    macro_case_args_payload: dict[str, Any] = dict(args_payload_obj) if isinstance(args_payload_obj, dict) else {}

                    scene_path = resolve_path(scene_path_raw)
                    if not scene_path.exists():
                        raise ValueError(f"scene not found: {scene_path_raw}")
                    macro_path = resolve_path(macro_path_raw)
                    if not macro_path.exists():
                        raise ValueError(f"macro not found: {macro_path_raw}")

                    scene_payload = _read_json_dict_artifact(
                        scene_path,
                        tag="VSTP-050",
                        purpose="macro-audit scene",
                    )
                    if scene_payload is None:
                        raise ValueError(f"failed to parse scene JSON: {scene_path_raw}")

                    macro_payload = load_macro_asset(str(macro_path))
                    rel_macro_path = macro_path_raw.replace("\\", "/")
                    macro_asset_issues = validate_macro_asset(macro_payload, rel_path=rel_macro_path)
                    if macro_asset_issues:
                        first_macro_issue = macro_asset_issues[0]
                        raise ValueError(f"{first_macro_issue.path} :: {first_macro_issue.code} :: {first_macro_issue.detail}")
                    asset = parse_macro_asset(macro_payload, rel_path=rel_macro_path)
                    merged_args: dict[str, Any] = dict(asset.defaults or {})
                    merged_args.update(macro_case_args_payload)

                    macro_id = str(asset.macro_id or "").strip()
                    anchor = str(merged_args.get("anchor") or "player").strip().lower()
                    pos = _find_player_pos(scene_payload, scene_path=scene_path_raw)
                    if anchor == "primary":
                        raise ValueError(f"macro-audit unsupported anchor=primary for {macro_id}")

                    # SceneController-based preview.
                    sc = SceneController(cast(Any, object()))
                    sc.current_scene_path = scene_path_raw
                    sc._loaded_scene_source_data = scene_payload

                    preview: dict[str, Any] | None = None
                    if macro_id == "macro.objective_zone":
                        toast_seconds_raw = merged_args.get("toast_seconds")
                        toast_seconds_val = None
                        if isinstance(toast_seconds_raw, (int, float)):
                            toast_seconds_val = _coerce_float(
                                toast_seconds_raw,
                                "toast_seconds",
                                tag="VSTP-026",
                                path=macro_path_raw,
                                purpose=(
                                    "macro-audit preview arg coercion fallback "
                                    f"macro_id={macro_id} scene_path={scene_path_raw}"
                                ),
                            )
                        elif toast_seconds_raw is not None:
                            _log_swallow(
                                "VSTP-026",
                                (
                                    "macro-audit preview arg coercion fallback "
                                    f"macro_id={macro_id} scene_path={scene_path_raw} "
                                    f"field=toast_seconds path={_normalize_diag_path(macro_path_raw)}"
                                ),
                                once=False,
                            )
                        radius_value = _coerce_float(
                            merged_args.get("radius") or 0.0,
                            "radius",
                            tag="VSTP-026",
                            path=macro_path_raw,
                            purpose=(
                                "macro-audit preview arg coercion fallback "
                                f"macro_id={macro_id} scene_path={scene_path_raw}"
                            ),
                        )
                        if radius_value is None:
                            raise ValueError(f"invalid radius for macro-audit preview: {macro_id}")
                        preview = sc.debug_preview_macro_objective_zone(
                            center_x=pos[0],
                            center_y=pos[1],
                            zone_id=str(merged_args.get("zone_id") or ""),
                            set_flag=str(merged_args.get("set_flag") or ""),
                            radius=radius_value,
                            toast=str(merged_args.get("toast") or "").strip() or None,
                            require_flags=merged_args.get("require_flags") if isinstance(merged_args.get("require_flags"), list) else None,
                            forbid_flags=merged_args.get("forbid_flags") if isinstance(merged_args.get("forbid_flags"), list) else None,
                            toast_seconds=toast_seconds_val,
                        )
                    elif macro_id == "macro.door_transition":
                        preview = sc.debug_preview_macro_door_transition(
                            center_x=pos[0],
                            center_y=pos[1],
                            target_scene=str(merged_args.get("target_scene") or ""),
                            spawn_id=str(merged_args.get("spawn_id") or ""),
                            primary_id=None,
                        )
                    elif macro_id == "macro.dialogue_choice_flag":
                        preview = sc.debug_preview_macro_dialogue_choice_flag(
                            speaker_id=str(merged_args.get("speaker_id") or ""),
                            choice_id=str(merged_args.get("choice_id") or ""),
                            choice_text=str(merged_args.get("choice_text") or ""),
                            set_flag=str(merged_args.get("set_flag") or ""),
                            toast=str(merged_args.get("toast") or "").strip() or None,
                        )
                    else:
                        raise ValueError(f"unknown macro_id: {macro_id}")

                    create_ids = preview.get("create_ids") if isinstance(preview, dict) else []
                    update_ids = preview.get("update_ids") if isinstance(preview, dict) else []
                    create_first = [v for v in create_ids if isinstance(v, str) and v.strip()][:5] if isinstance(create_ids, list) else []
                    update_first = [v for v in update_ids if isinstance(v, str) and v.strip()][:5] if isinstance(update_ids, list) else []

                    macro_out_cases.append(
                        {
                            "scene_path": scene_path_raw.replace("\\", "/"),
                            "macro_path": rel_macro_path,
                            "args": merged_args,
                            "will_create": int(preview.get("will_create", 0) or 0) if isinstance(preview, dict) else 0,
                            "will_update": int(preview.get("will_update", 0) or 0) if isinstance(preview, dict) else 0,
                            "create_ids_first": create_first,
                            "update_ids_first": update_first,
                        }
                    )

                macro_audit_payload = {"ok": True, "case_count": int(len(macro_out_cases)), "cases": macro_out_cases}
                artifact = None
                if artifacts_dir is not None:
                    with suppress_stdout():
                        write_json_atomic(
                            artifacts_dir / "macro_audit.json",
                            macro_audit_payload,
                            indent=2,
                            sort_keys=True,
                            trailing_newline=True,
                        )
                    artifact = _normalize_path_for_json(artifacts_dir / "macro_audit.json", repo_root=repo_root)
                    artifacts_written["macro_audit"] = artifact

                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: macro-audit step isolation
                _log_swallow("VSTP-028", "macro-audit step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                artifact = None

            _add_step("macro-audit", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 9: room-audit (optional curated room scaffold dry-run reports)
        if failure_seen:
            _skipped_step("room-audit")
        else:
            try:
                import copy
                import json

                from engine.paths import resolve_path
                from engine.persistence_io import write_json_atomic
                from engine.tooling_runtime.macro_apply_report import compute_scene_macro_report

                config = load_config()
                world_path = str(getattr(args, "world", "") or "").strip()
                if not world_path:
                    world_path = str(getattr(config, "world_file", "") or "").strip()
                if not world_path:
                    world_path = "worlds/main_world.json"

                world_file = resolve_path(world_path)
                room_world_data: dict[str, Any] = {}
                if world_file.exists():
                    room_world_data = _read_json_dict_artifact(
                        world_file,
                        tag="VSTP-047",
                        purpose="room-audit config",
                    ) or {}

                scenes_value = room_world_data.get("scenes")
                scenes_map: dict[str, Any] = scenes_value if isinstance(scenes_value, dict) else {}

                def _norm(p: str) -> str:
                    return str(p or "").replace("\\", "/")

                def _world_key_for_path(scene_path: str) -> str:
                    wanted = _norm(scene_path)
                    for k, v in scenes_map.items():
                        if not isinstance(k, str) or not isinstance(v, dict):
                            continue
                        raw = v.get("path")
                        if isinstance(raw, str) and _norm(raw) == wanted:
                            return k
                    # Deterministic fallback: stem (then stem_2, stem_3, ...)
                    base = Path(scene_path).stem or "scene"
                    candidate = base
                    i = 2
                    while candidate in scenes_map:
                        candidate = f"{base}_{i}"
                        i += 1
                    return candidate

                def _spawn_points(scene_payload: dict[str, Any], *, scene_path: str) -> dict[str, tuple[float, float]]:
                    out: dict[str, tuple[float, float]] = {}
                    entities = scene_payload.get("entities")
                    if not isinstance(entities, list):
                        return out
                    for ent in entities:
                        if not isinstance(ent, dict):
                            continue
                        if str(ent.get("tag") or "") != "spawn_point":
                            continue
                        sid = ent.get("spawn_id")
                        if not isinstance(sid, str) or not sid.strip():
                            continue
                        spawn_id = sid.strip()
                        out[spawn_id] = _coerce_xy_pair(
                            ent,
                            default=(0.0, 0.0),
                            tag="VSTP-029",
                            path=scene_path,
                            purpose=f"room-audit spawn position coercion fallback spawn_id={spawn_id}",
                        )
                    return out

                raw_cases = room_world_data.get("room_audit_cases") if isinstance(room_world_data, dict) else None
                room_cases_raw: list[dict[str, Any]] = []
                if isinstance(raw_cases, list):
                    for idx, entry in enumerate(raw_cases):
                        if not isinstance(entry, dict):
                            continue
                        from_scene = entry.get("from_scene")
                        to_scene = entry.get("to_scene")
                        stamp_path = entry.get("stamp_path")
                        door_macro = entry.get("door_macro")
                        args_payload = entry.get("args")
                        anchor = entry.get("anchor", "player")
                        if not (
                            isinstance(from_scene, str)
                            and from_scene.strip()
                            and isinstance(to_scene, str)
                            and to_scene.strip()
                            and isinstance(stamp_path, str)
                            and stamp_path.strip()
                            and isinstance(door_macro, str)
                            and door_macro.strip()
                            and isinstance(args_payload, dict)
                        ):
                            raise ValueError(
                                f"invalid room_audit_cases[{idx}] (expected from_scene/to_scene/stamp_path/door_macro/args object)"
                            )
                        room_cases_raw.append(
                            {
                                "from_scene": str(from_scene).strip(),
                                "to_scene": str(to_scene).strip(),
                                "stamp_path": str(stamp_path).strip(),
                                "door_macro": str(door_macro).strip(),
                                "args": dict(args_payload),
                                "anchor": str(anchor or "player").strip().lower() or "player",
                            }
                        )

                room_cases_raw.sort(
                    key=lambda c: (
                        str(c.get("from_scene") or ""),
                        str(c.get("to_scene") or ""),
                        str(c.get("stamp_path") or ""),
                        str(c.get("door_macro") or ""),
                        json.dumps(c.get("args") or {}, sort_keys=True),
                    )
                )

                room_out_cases: list[dict[str, Any]] = []
                for case in room_cases_raw:
                    from_scene = str(case["from_scene"])
                    to_scene = str(case["to_scene"])
                    stamp_path = str(case["stamp_path"])
                    door_macro = str(case["door_macro"])
                    args_payload_obj = case.get("args")
                    case_args_payload: dict[str, Any] = dict(args_payload_obj) if isinstance(args_payload_obj, dict) else {}
                    anchor = str(case.get("anchor") or "player").strip().lower() or "player"

                    from_key = _world_key_for_path(from_scene)
                    to_key = _world_key_for_path(to_scene)

                    # Load scenes for spawn anchor extraction (best-effort; missing => (0,0)).
                    from_payload: dict[str, Any] = {}
                    to_payload: dict[str, Any] = {}
                    fp = resolve_path(from_scene)
                    if fp.exists():
                        from_payload = _read_json_dict_artifact(
                            fp,
                            tag="VSTP-030",
                            purpose="room-audit from_scene",
                        ) or {}
                    tp = resolve_path(to_scene)
                    if tp.exists():
                        to_payload = _read_json_dict_artifact(
                            tp,
                            tag="VSTP-031",
                            purpose="room-audit to_scene",
                        ) or {}

                    from_spawns = _spawn_points(from_payload, scene_path=from_scene)
                    to_spawns = _spawn_points(to_payload, scene_path=to_scene)

                    start_scene = str(room_world_data.get("start_scene") or "").strip() if isinstance(room_world_data, dict) else ""
                    start_spawn = str(room_world_data.get("start_spawn") or "").strip() if isinstance(room_world_data, dict) else ""
                    from_spawn = None
                    if start_scene and start_scene == from_key and start_spawn and start_spawn in from_spawns:
                        from_spawn = start_spawn
                    elif "default" in from_spawns:
                        from_spawn = "default"
                    elif from_spawns:
                        from_spawn = sorted(from_spawns.keys())[0]
                    else:
                        from_spawn = "default"

                    spawn_id_arg = case_args_payload.get("spawn_id")
                    to_spawn = str(spawn_id_arg or "").strip() if isinstance(spawn_id_arg, str) and str(spawn_id_arg).strip() else None
                    if to_spawn is None:
                        if "default" in to_spawns:
                            to_spawn = "default"
                        elif to_spawns:
                            to_spawn = sorted(to_spawns.keys())[0]
                        else:
                            to_spawn = "default"

                    from_x, from_y = from_spawns.get(from_spawn, (0.0, 0.0))
                    to_x, to_y = to_spawns.get(to_spawn, (0.0, 0.0))

                    # Simulate Step 5 (world link-scenes) in-memory for the from-scene side,
                    # so door macros can be previewed against the deterministic link id.
                    from_payload_sim = copy.deepcopy(from_payload) if isinstance(from_payload, dict) else {"entities": []}
                    entities = from_payload_sim.get("entities")
                    if entities is None:
                        entities = []
                        from_payload_sim["entities"] = entities
                    if not isinstance(entities, list):
                        entities = []
                        from_payload_sim["entities"] = entities

                    from_entity_id = _default_transition_entity_id(from_scene, to_key, from_x, from_y)
                    changed, err = _ensure_scene_transition_entity(
                        entities=entities,
                        entity_id=from_entity_id,
                        target_scene=to_key,
                        spawn_id=to_spawn,
                        x=from_x,
                        y=from_y,
                        name=f"TransitionTo_{to_key}",
                    )
                    if err:
                        raise ValueError(f"{from_scene}: {err}")

                    # Convert args dict to k=v list deterministically (stable JSON for non-scalars).
                    raw_args: list[str] = []
                    for k in sorted(case_args_payload.keys()):
                        v = case_args_payload.get(k)
                        if isinstance(v, (dict, list, bool)) or v is None:
                            raw_args.append(f"{k}={json.dumps(v, sort_keys=True)}")
                        else:
                            raw_args.append(f"{k}={v}")

                    macro_result = compute_scene_macro_report(
                        scene_payload=from_payload_sim,
                        scene_path=from_scene,
                        macro_path=door_macro,
                        raw_args=raw_args,
                        anchor_override=anchor,
                        cursor_world_pos=(from_x, from_y),
                        primary_entity_id=from_entity_id,
                    )
                    macro_report = macro_result.report
                    macro_entity_changes = macro_report.get("entity_changes") if isinstance(macro_report, dict) else None
                    macro_config_changes = macro_report.get("config_changes") if isinstance(macro_report, dict) else None

                    room_out_cases.append(
                        {
                            "from_scene": _norm(from_scene),
                            "to_scene": _norm(to_scene),
                            "stamp_path": _norm(stamp_path),
                            "door_macro": _norm(door_macro),
                            "will_create": int(macro_report.get("will_create") or 0) if isinstance(macro_report, dict) else 0,
                            "will_update": int(macro_report.get("will_update") or 0) if isinstance(macro_report, dict) else 0,
                            "entity_change_count": int(len(macro_entity_changes)) if isinstance(macro_entity_changes, list) else 0,
                            "config_change_count": int(len(macro_config_changes)) if isinstance(macro_config_changes, list) else 0,
                        }
                    )

                room_audit_payload = {"ok": True, "case_count": int(len(room_out_cases)), "cases": room_out_cases}
                artifact = None
                if artifacts_dir is not None:
                    with suppress_stdout():
                        write_json_atomic(
                            artifacts_dir / "room_audit.json",
                            room_audit_payload,
                            indent=2,
                            sort_keys=True,
                            trailing_newline=True,
                        )
                    artifact = _normalize_path_for_json(artifacts_dir / "room_audit.json", repo_root=repo_root)
                    artifacts_written["room_audit"] = artifact

                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: room-audit step isolation
                _log_swallow("VSTP-032", "room-audit step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                artifact = None

            _add_step("room-audit", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 9: encounter-set-uniqueness (prevent accidental duplicate IDs across sources)
        if failure_seen:
            _skipped_step("encounter-set-uniqueness")
        else:
            try:
                from engine.validators.encounter_set_uniqueness_validator import validate_encounter_set_uniqueness

                with suppress_stdout():
                    uniqueness_payload = validate_encounter_set_uniqueness()
                code = 0 if bool(uniqueness_payload.get("ok")) else 1
                if code == 0:
                    error = ""
                else:
                    uniqueness_errors = uniqueness_payload.get("errors") or []
                    if isinstance(uniqueness_errors, list) and uniqueness_errors and isinstance(uniqueness_errors[0], dict):
                        first_error = uniqueness_errors[0]
                        set_id = str(first_error.get("encounter_set_id") or "")
                        sources = first_error.get("source_paths")
                        sources_text = ", ".join(str(x) for x in sources) if isinstance(sources, list) else str(sources)
                        error = f"duplicate encounter_set_id={set_id} sources={sources_text}"
                    else:
                        error = "encounter-set-uniqueness found errors"
            except Exception as exc:  # noqa: BLE001  # REASON: encounter-set-uniqueness step isolation
                _log_swallow("VSTP-033", "encounter-set-uniqueness step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("encounter-set-uniqueness", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 7: encounter-set-variety (prevent accidental all-one-prefab sets)
        if failure_seen:
            _skipped_step("encounter-set-variety")
        else:
            try:
                from engine.validators.encounter_set_variety_validator import validate_encounter_set_variety

                with suppress_stdout():
                    variety_payload = validate_encounter_set_variety()
                code = 0 if bool(variety_payload.get("ok")) else 1
                if code == 0:
                    error = ""
                else:
                    variety_errors = variety_payload.get("errors") or []
                    if isinstance(variety_errors, list) and variety_errors and isinstance(variety_errors[0], dict):
                        first_error = variety_errors[0]
                        set_id = str(first_error.get("encounter_set_id") or "")
                        unique = first_error.get("unique_prefabs")
                        required = first_error.get("required")
                        error = f"low variety encounter_set_id={set_id} unique_prefabs={unique} required={required}"
                    else:
                        error = "encounter-set-variety found errors"
            except Exception as exc:  # noqa: BLE001  # REASON: encounter-set-variety step isolation
                _log_swallow("VSTP-034", "encounter-set-variety step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("encounter-set-variety", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 8: prefab-lint-overrides (unexpected prefab override guard)
        if failure_seen:
            _skipped_step("prefab-lint-overrides")
        else:
            try:
                from engine.tooling.prefab_cli import compute_lint_overrides

                with suppress_stdout():
                    overrides_payload, ok = compute_lint_overrides()
                code = 0 if ok else 2
                error = ""
                if code != 0:
                    allow_error = overrides_payload.get("error")
                    if isinstance(allow_error, str) and allow_error.strip():
                        error = allow_error
                    else:
                        unexpected = overrides_payload.get("unexpected") or []
                        if isinstance(unexpected, list) and unexpected and isinstance(unexpected[0], dict):
                            first = unexpected[0]
                            prefab_id = first.get("prefab_id")
                            winner = first.get("winner")
                            error = f"unexpected override prefab_id={prefab_id} winner={winner}"
                        else:
                            error = "prefab-lint-overrides found unexpected overrides"
            except Exception as exc:  # noqa: BLE001  # REASON: prefab-lint-overrides step isolation
                _log_swallow("VSTP-035", "prefab-lint-overrides step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("prefab-lint-overrides", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        pre_coverage_failure = failure_seen

        # Step 10: encounter-coverage (theme encounter set affordability)
        if failure_seen:
            _skipped_step("encounter-coverage")
        else:
            try:
                from engine.validators.encounter_coverage_validator import validate_encounter_coverage

                with suppress_stdout():
                    coverage_payload = validate_encounter_coverage(difficulties=("easy", "hard"))
                code = 0 if bool(coverage_payload.get("ok")) else 1
                error = "" if code == 0 else "encounter-coverage found errors"
            except Exception as exc:  # noqa: BLE001  # REASON: encounter-coverage step isolation
                _log_swallow("VSTP-036", "encounter-coverage step isolation fallback", once=False)
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("encounter-coverage", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 11: encounter-coverage-matrix (coverage tuning summary artifact)
        if pre_coverage_failure:
            _skipped_step("encounter-coverage-matrix")
        else:
            try:
                from engine.validators.encounter_coverage_validator import (
                    compute_encounter_coverage_rows,
                    encounter_coverage_rows_to_payload,
                )
                from engine.persistence_io import write_json_atomic

                with suppress_stdout():
                    rows = compute_encounter_coverage_rows(difficulties=("easy", "hard"))
                    matrix_payload = encounter_coverage_rows_to_payload(rows, difficulties=("easy", "hard"))
                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: encounter-coverage-matrix step isolation
                _log_swallow("VSTP-037", "encounter-coverage-matrix step isolation fallback", once=False)
                matrix_payload = None
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            artifact = None
            if code == 0 and artifacts_dir is not None:
                matrix_target_path = artifacts_dir / "encounter_coverage_matrix.json"
                with suppress_stdout():
                    write_json_atomic(
                        matrix_target_path,
                        matrix_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                artifact = _normalize_path_for_json(matrix_target_path, repo_root=repo_root)
                artifacts_written["encounter_coverage_matrix"] = artifact

            _add_step("encounter-coverage-matrix", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 12: doctor-assets (non-strict; warnings allowed)
        if failure_seen:
            _skipped_step("doctor-assets")
        else:
            from engine.tooling.asset_doctor import doctor_assets

            try:
                with suppress_stdout():
                    doctor_payload = doctor_assets(repo_root=repo_root, fix=False, strict=False)
                code = 0 if bool(doctor_payload.get("ok")) else 1
                error = "" if code == 0 else "doctor-assets found errors"
            except Exception as exc:  # noqa: BLE001  # REASON: doctor-assets step isolation
                _log_swallow("VSTP-038", "doctor-assets step isolation fallback", once=False)
                doctor_payload = {
                    "ok": False,
                    "errors": [
                        {
                            "code": "doctor_assets.exception",
                            "path": "",
                            "message": _single_line_error(f"{type(exc).__name__}: {exc}"),
                        }
                    ],
                    "warnings": [],
                    "fixes": [],
                }
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            artifact = None
            if artifacts_dir is not None:
                from engine.persistence_io import write_json_atomic

                doctor_assets_target_path = artifacts_dir / "doctor_assets.json"
                with suppress_stdout():
                    write_json_atomic(
                        doctor_assets_target_path,
                        doctor_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                artifact = _normalize_path_for_json(doctor_assets_target_path, repo_root=repo_root)
                artifacts_written["doctor_assets"] = artifact

            _add_step("doctor-assets", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 13: content-audit (cross-registry integrity)
        if failure_seen:
            _skipped_step("content-audit")
        else:
            try:
                from mesh_cli import content_integrity
                from engine.persistence_io import write_json_atomic, write_text_atomic

                should_run_content_audit = content_integrity.has_required_content_roots(repo_root)
                content_audit_report = None
                if should_run_content_audit:
                    with suppress_stdout():
                        content_audit_report = content_integrity.run_content_audit(repo_root)
                    code = 0 if bool(content_audit_report.ok) else 1
                    error = "" if code == 0 else "content-audit found errors"
                else:
                    code = 0
                    error = ""

            except Exception as exc:  # noqa: BLE001  # REASON: content-audit step isolation
                _log_swallow("VSTP-039", "content-audit step isolation fallback", once=False)
                content_audit_report = None
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            artifact = None
            if (
                code == 0
                and artifacts_dir is not None
                and content_audit_report is not None
            ):
                content_audit_json_path = artifacts_dir / "content_audit_report.json"
                content_audit_txt_path = artifacts_dir / "content_audit_report.txt"
                with suppress_stdout():
                    write_json_atomic(
                        content_audit_json_path,
                        content_audit_report.to_dict(),
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                        durable=True,
                    )
                    write_text_atomic(
                        content_audit_txt_path,
                        content_integrity.format_content_audit_text(content_audit_report),
                        encoding="utf-8",
                        durable=True,
                    )
                artifact = _normalize_path_for_json(content_audit_json_path, repo_root=repo_root)
                artifacts_written["content_audit"] = artifact

            _add_step("content-audit", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 14: encounter-audit (compact report artifact)
        if failure_seen:
            _skipped_step("encounter-audit")
        else:
            try:
                from engine.encounter_report import (
                    encounter_report_to_audit_payload,
                    encounter_report_to_compact_payload,
                    encounter_report_to_headroom_payload,
                )
                from engine.persistence_io import write_json_atomic

                with suppress_stdout():
                    config = load_config()
                    world_path = str(getattr(config, "world_file", "") or "").strip() or "worlds/main_world.json"
                    scene_paths = _resolve_scene_paths(world_path)
                    encounter_report = generate_encounter_report(
                        scene_paths=scene_paths,
                        difficulties=["easy", "normal", "hard"],
                        theme_filter=[],
                        only_dungeons=False,
                    )
                    audit_payload = encounter_report_to_audit_payload(encounter_report)
                    compact_payload = encounter_report_to_compact_payload(encounter_report)
                    headroom_payload = encounter_report_to_headroom_payload(encounter_report)

                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: encounter-audit step isolation
                _log_swallow("VSTP-040", "encounter-audit step isolation fallback", once=False)
                audit_payload = None
                compact_payload = None
                headroom_payload = None
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            artifact = None
            if code == 0 and artifacts_dir is not None:
                target_summary = artifacts_dir / "encounter_audit_summary.json"
                target_compact = artifacts_dir / "encounter_audit_compact.json"
                target_headroom = artifacts_dir / "encounter_headroom.json"
                with suppress_stdout():
                    write_json_atomic(
                        target_summary,
                        audit_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                    write_json_atomic(
                        target_compact,
                        compact_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                    write_json_atomic(
                        target_headroom,
                        headroom_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                artifact = _normalize_path_for_json(target_summary, repo_root=repo_root)
                artifacts_written["encounter_audit_summary"] = artifact
                artifacts_written["encounter_audit_compact"] = _normalize_path_for_json(target_compact, repo_root=repo_root)
                artifacts_written["encounter_headroom"] = _normalize_path_for_json(target_headroom, repo_root=repo_root)

            _add_step("encounter-audit", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 15: list-scenes
        if failure_seen:
            _skipped_step("list-scenes")
        else:
            try:
                with suppress_stdout():
                    scenes_payload = _inventory_list_scenes()
                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: list-scenes step isolation
                _log_swallow("VSTP-041", "list-scenes step isolation fallback", once=False)
                scenes_payload = None
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            artifact = None
            if code == 0 and not no_index and write_scenes is not None:
                scenes_index_target = artifacts_dir / "scenes_index.json" if artifacts_dir is not None else write_scenes
                from engine.persistence_io import write_json_atomic

                with suppress_stdout():
                    write_json_atomic(
                        scenes_index_target,
                        scenes_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                artifact = _normalize_path_for_json(scenes_index_target, repo_root=repo_root)
                if artifacts_dir is not None:
                    artifacts_written["scenes_index"] = artifact
            _add_step("list-scenes", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1

        # Step 16: list-worlds
        if failure_seen:
            _skipped_step("list-worlds")
        else:
            try:
                with suppress_stdout():
                    worlds_payload = _inventory_list_worlds()
                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001  # REASON: list-worlds step isolation
                _log_swallow("VSTP-042", "list-worlds step isolation fallback", once=False)
                worlds_payload = None
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            artifact = None
            if code == 0 and not no_index and write_worlds is not None:
                worlds_index_target = artifacts_dir / "worlds_index.json" if artifacts_dir is not None else write_worlds
                from engine.persistence_io import write_json_atomic

                with suppress_stdout():
                    write_json_atomic(
                        worlds_index_target,
                        worlds_payload,
                        indent=2,
                        sort_keys=True,
                        trailing_newline=True,
                    )
                artifact = _normalize_path_for_json(worlds_index_target, repo_root=repo_root)
                if artifacts_dir is not None:
                    artifacts_written["worlds_index"] = artifact
            _add_step("list-worlds", code, error=error, artifact=artifact)
            if code != 0:
                failure_seen = True
                exit_code = 1
    state.pytest_fast_ran = bool(pytest_fast_ran)
    state.exit_code = int(exit_code)
    state.failure_seen = bool(failure_seen)
    state.step_duration_total_ms = int(step_duration_total_ms)
