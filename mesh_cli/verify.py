from __future__ import annotations

import argparse


VERIFY_ALL_STEPS: tuple[str, ...] = (
    "verify-demo",
    "verify-replays",
    "verify-strict",
    "mypy-gate",
    "mypy-baseline-guard",
    "pytest-fast",
    "pytest-fast-duration-guard",
    "world-progression-check",
    "spawn-placeholder-safety",
    "stamp-audit",
    "brush-audit",
    "macro-audit",
    "room-audit",
    "encounter-set-uniqueness",
    "encounter-set-variety",
    "prefab-lint-overrides",
    "encounter-coverage",
    "encounter-coverage-matrix",
    "doctor-assets",
    "encounter-audit",
    "list-scenes",
    "list-worlds",
)


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
            if p.is_file() and not p.name.endswith(".hash.json")
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
                    "scenes_index": None,
                    "worlds_index": None,
                    "replays_summary": None,
                    "doctor_assets": None,
                    "stamp_audit": None,
                    "brush_audit": None,
                    "macro_audit": None,
                    "room_audit": None,
                    "encounter_coverage_matrix": None,
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
        "scenes_index": None,
        "worlds_index": None,
        "replays_summary": None,
        "doctor_assets": None,
        "stamp_audit": None,
        "brush_audit": None,
        "macro_audit": None,
        "room_audit": None,
        "encounter_coverage_matrix": None,
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

    steps: list[dict] = []
    pytest_fast_metrics: dict[str, float | bool | None] = {"ok": None, "total": None, "top10": None}
    pytest_fast_ran = False

    def _add_step(
        name: str,
        code: int,
        *,
        error: str,
        artifact: str | None,
    ) -> None:
        steps.append(
            {
                "name": name,
                "ok": int(code) == 0,
                "code": int(code),
                "error": _single_line_error(error),
                "artifact": artifact,
            }
        )

    def _skipped_step(name: str) -> None:
        _add_step(
            name,
            2,
            error="skipped: previous step failed",
            artifact=None,
        )

    expected_steps = list(VERIFY_ALL_STEPS)

    exit_code = 0
    failure_seen = False

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
                    if artifacts_dir is not None:
                        log_path = artifacts_dir / "verify_demo.log"
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
                                )
                            )
                    error = "" if code == 0 else f"failed with code {code}"
                except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
                    try:
                        previous_count = int(metrics_path.read_text(encoding="utf-8").strip() or "0")
                    except Exception:
                        previous_count = current_count
                else:
                    previous_count = current_count

                if current_count > previous_count:
                    code = 2
                    error = f"mypy baseline grew: {previous_count} -> {current_count}"
                else:
                    code = 0
                    error = ""
                    metrics_path.write_text(f"{current_count}\n", encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("mypy-baseline-guard", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 6: pytest-fast (exclude slow/e2e tests for local sanity)
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
                else:
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
            except Exception as exc:  # noqa: BLE001
                code = 1
                error = f"{type(exc).__name__}: {exc}"

            _add_step("pytest-fast", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 7: pytest-fast-duration-guard (ratchet against slowdowns)
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
            except Exception as exc:  # noqa: BLE001
                code = 1
                error = f"{type(exc).__name__}: {exc}"
                pytest_fast_metrics["ok"] = False

            _add_step("pytest-fast-duration-guard", code, error=error, artifact=None)
            if code != 0:
                failure_seen = True
                exit_code = 1 if code != 2 else 2

        # Step 8: world-progression-check (start -> key milestones)
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
                    try:
                        world_file = resolve_path(world_path)
                        if world_file.exists():
                            raw = json.loads(world_file.read_text(encoding="utf-8"))
                            if isinstance(raw, dict):
                                configured = raw.get("progression_required_scene_paths")
                                if isinstance(configured, list):
                                    required_paths = tuple(str(p) for p in configured if isinstance(p, str) and p.strip())
                    except Exception:
                        required_paths = ()

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
            except Exception as exc:  # noqa: BLE001
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
                        target = str(first_issue.get("offending_target_id") or "")
                        dist = first_issue.get("distance")
                        dist_text = f"{float(dist):.2f}" if isinstance(dist, (int, float)) else "?"
                        error = f"{scene} {pid} {reason} target={target} dist={dist_text}"
                    else:
                        error = "spawn-placeholder-safety found errors"
            except Exception as exc:  # noqa: BLE001
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
                try:
                    world_file = resolve_path(world_path)
                    if world_file.exists():
                        stamp_world_data = json.loads(world_file.read_text(encoding="utf-8"))
                        if isinstance(stamp_world_data, dict):
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
                                    stamp_cases_raw.append(
                                        {
                                            "scene_path": str(scene_path).strip(),
                                            "stamp_path": str(stamp_path).strip(),
                                            "origin_x": int(origin["x"]),
                                            "origin_y": int(origin["y"]),
                                            "id_prefix": str(id_prefix).strip(),
                                        }
                                    )
                except StampReportError:
                    raise
                except Exception:
                    stamp_cases_raw = []

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

                    try:
                        raw_scene = json.loads(resolved_scene.read_text(encoding="utf-8"))
                    except Exception as exc:  # noqa: BLE001
                        raise StampReportError(f"failed to parse scene JSON: {scene_path_display}: {exc}") from exc
                    if not isinstance(raw_scene, dict):
                        raise StampReportError(f"scene JSON root must be an object: {scene_path_display}")

                    try:
                        stamp = json.loads(resolved_stamp.read_text(encoding="utf-8"))
                    except Exception as exc:  # noqa: BLE001
                        raise StampReportError(f"failed to parse stamp JSON: {stamp_path_raw}: {exc}") from exc
                    if not isinstance(stamp, dict):
                        raise StampReportError(f"stamp JSON root must be an object: {stamp_path_raw}")

                    raw_scene["_mesh_source_path"] = scene_path_display
                    stamp["_mesh_source_path"] = stamp_path_raw

                    stamp_report = compute_scene_stamp_report(
                        raw_scene,
                        stamp,
                        int(case["origin_x"]),
                        int(case["origin_y"]),
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
            except Exception as exc:  # noqa: BLE001
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

                config = load_config()
                world_path = str(getattr(args, "world", "") or "").strip()
                if not world_path:
                    world_path = str(getattr(config, "world_file", "") or "").strip()
                if not world_path:
                    world_path = "worlds/main_world.json"

                brush_cases_raw: list[dict[str, Any]] = []
                try:
                    world_file = resolve_path(world_path)
                    if world_file.exists():
                        brush_world_data = json.loads(world_file.read_text(encoding="utf-8"))
                        if isinstance(brush_world_data, dict):
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
                                    brush_cases_raw.append(
                                        {
                                            "scene_path": str(scene_path).strip(),
                                            "brush_path": str(brush_path).strip(),
                                            "layer_id": str(layer_id).strip(),
                                            "origin_x": int(origin["x"]),
                                            "origin_y": int(origin["y"]),
                                            "anchor": str(anchor or "tl").strip().lower(),
                                            "clip": bool(clip),
                                        }
                                    )
                except BrushReportError:
                    raise
                except Exception:
                    brush_cases_raw = []

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

                    try:
                        raw_scene = json.loads(resolved_scene.read_text(encoding="utf-8"))
                    except Exception as exc:  # noqa: BLE001
                        raise BrushReportError(f"failed to parse scene JSON: {scene_path_display}: {exc}") from exc
                    if not isinstance(raw_scene, dict):
                        raise BrushReportError(f"scene JSON root must be an object: {scene_path_display}")

                    try:
                        raw_brush = json.loads(resolved_brush.read_text(encoding="utf-8"))
                    except Exception as exc:  # noqa: BLE001
                        raise BrushReportError(f"failed to parse brush JSON: {brush_path_raw}: {exc}") from exc
                    if not isinstance(raw_brush, dict):
                        raise BrushReportError(f"brush JSON root must be an object: {brush_path_raw}")

                    raw_scene["_mesh_source_path"] = scene_path_display
                    raw_brush["_mesh_source_path"] = brush_path_raw

                    brush_report = compute_scene_brush_report(
                        raw_scene,
                        raw_brush,
                        origin_x=int(case["origin_x"]),
                        origin_y=int(case["origin_y"]),
                        layer_id=str(case["layer_id"]),
                        anchor=str(case["anchor"] or "tl"),  # type: ignore[arg-type]
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
            except Exception as exc:  # noqa: BLE001
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
                try:
                    world_file = resolve_path(world_path)
                    if world_file.exists():
                        macro_world_data = json.loads(world_file.read_text(encoding="utf-8"))
                        configured = macro_world_data.get("macro_audit_cases") if isinstance(macro_world_data, dict) else None
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
                except Exception:
                    macro_cases_raw = []

                macro_cases_raw.sort(
                    key=lambda c: (
                        str(c.get("scene_path") or ""),
                        str(c.get("macro_path") or ""),
                        json.dumps(c.get("args") or {}, sort_keys=True),
                    )
                )

                def _find_player_pos(scene_payload: dict[str, Any]) -> tuple[float, float]:
                    entities = scene_payload.get("entities")
                    if isinstance(entities, list):
                        for e in entities:
                            if not isinstance(e, dict):
                                continue
                            pid = e.get("prefab_id")
                            tags = e.get("tags")
                            if pid == "player" or (isinstance(tags, list) and "player" in tags):
                                try:
                                    return float(e.get("x", 0.0)), float(e.get("y", 0.0))
                                except Exception:
                                    return 0.0, 0.0
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

                    scene_payload = json.loads(scene_path.read_text(encoding="utf-8"))
                    if not isinstance(scene_payload, dict):
                        raise ValueError(f"scene JSON root must be an object: {scene_path_raw}")

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
                    pos = _find_player_pos(scene_payload)
                    if anchor == "primary":
                        raise ValueError(f"macro-audit unsupported anchor=primary for {macro_id}")

                    # SceneController-based preview.
                    sc = SceneController(object())  # type: ignore[arg-type]
                    sc.current_scene_path = scene_path_raw
                    sc._loaded_scene_source_data = scene_payload

                    preview: dict[str, Any] | None = None
                    if macro_id == "macro.objective_zone":
                        toast_seconds_raw = merged_args.get("toast_seconds")
                        toast_seconds_val = float(toast_seconds_raw) if isinstance(toast_seconds_raw, (int, float)) else None
                        preview = sc.debug_preview_macro_objective_zone(
                            center_x=float(pos[0]),
                            center_y=float(pos[1]),
                            zone_id=str(merged_args.get("zone_id") or ""),
                            set_flag=str(merged_args.get("set_flag") or ""),
                            radius=float(merged_args.get("radius") or 0.0),
                            toast=str(merged_args.get("toast") or "").strip() or None,
                            require_flags=merged_args.get("require_flags") if isinstance(merged_args.get("require_flags"), list) else None,
                            forbid_flags=merged_args.get("forbid_flags") if isinstance(merged_args.get("forbid_flags"), list) else None,
                            toast_seconds=toast_seconds_val,
                        )
                    elif macro_id == "macro.door_transition":
                        preview = sc.debug_preview_macro_door_transition(
                            center_x=float(pos[0]),
                            center_y=float(pos[1]),
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
            except Exception as exc:  # noqa: BLE001
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
                    loaded = json.loads(world_file.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        room_world_data = loaded

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

                def _spawn_points(scene_payload: dict[str, Any]) -> dict[str, tuple[float, float]]:
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
                        try:
                            out[sid.strip()] = (float(ent.get("x", 0.0)), float(ent.get("y", 0.0)))
                        except Exception:
                            out[sid.strip()] = (0.0, 0.0)
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
                    try:
                        fp = resolve_path(from_scene)
                        if fp.exists():
                            raw = json.loads(fp.read_text(encoding="utf-8"))
                            if isinstance(raw, dict):
                                from_payload = raw
                    except Exception:
                        from_payload = {}
                    try:
                        tp = resolve_path(to_scene)
                        if tp.exists():
                            raw = json.loads(tp.read_text(encoding="utf-8"))
                            if isinstance(raw, dict):
                                to_payload = raw
                    except Exception:
                        to_payload = {}

                    from_spawns = _spawn_points(from_payload)
                    to_spawns = _spawn_points(to_payload)

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

                    from_entity_id = legacy_mod._default_transition_entity_id(from_scene, to_key, from_x, from_y)
                    changed, err = legacy_mod._ensure_scene_transition_entity(
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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

        # Step 13: encounter-audit (compact report artifact)
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
            except Exception as exc:  # noqa: BLE001
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

        # Step 14: list-scenes
        if failure_seen:
            _skipped_step("list-scenes")
        else:
            try:
                with suppress_stdout():
                    scenes_payload = _inventory_list_scenes()
                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001
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

        # Step 15: list-worlds
        if failure_seen:
            _skipped_step("list-worlds")
        else:
            try:
                with suppress_stdout():
                    worlds_payload = _inventory_list_worlds()
                code = 0
                error = ""
            except Exception as exc:  # noqa: BLE001
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

    # Ensure stable shape: include skipped steps even if failure happened before they were processed.
    seen_names = {s.get("name") for s in steps}
    for name in expected_steps:
        if name not in seen_names:
            _skipped_step(name)

    overall_ok = all(bool(s.get("ok")) for s in steps)

    if artifacts_dir is not None:
        artifacts_written["verify_all_summary"] = _normalize_path_for_json(
            artifacts_dir / "verify_all_summary.json", repo_root=repo_root
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
