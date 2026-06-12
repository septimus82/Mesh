# ruff: noqa: F401

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.persistence_io import (
    dumps_json_deterministic,
    write_json_atomic,
    write_text_atomic,
)
from engine.provenance import get_provenance, provenance_to_dict
from engine.save_runtime.normalize import normalize_save_payload

from . import episode as episode_commands
from .replay_digest_projection import (
    DIGEST_PROJECTION_POLICY,
)
from .replay_digest_projection import (
    project_event_for_digest as _project_event_for_golden_digest,
)
from .replay_digest_projection import (
    project_events_for_digest as _project_events_for_golden_digest,
)
from .replay_digest_projection import (
    project_final_state_for_digest as _project_final_state_for_golden_digest,
)
from .replay_digest_projection import (
    project_world_digests_for_digest as _project_world_digests_for_golden_digest,
)

SCHEMA_VERSION = 1
GOLDEN_SCHEMA_VERSION = 1
PERF_SCHEMA_VERSION = 1
UPDATE_GOLDEN_SCHEMA_VERSION = 2
DEFAULT_SEED = 123
_PREVIEW_ITEMS = 3


@dataclass(frozen=True, slots=True)
class ReplayBudgets:
    max_total_ms: float | None = None
    max_tick_ms_p95: float | None = None
    max_tick_ms_max: float | None = None

    def to_dict(self) -> dict[str, float]:
        payload: dict[str, float] = {}
        if self.max_total_ms is not None:
            payload["max_total_ms"] = self.max_total_ms
        if self.max_tick_ms_p95 is not None:
            payload["max_tick_ms_p95"] = self.max_tick_ms_p95
        if self.max_tick_ms_max is not None:
            payload["max_tick_ms_max"] = self.max_tick_ms_max
        return payload


@dataclass(frozen=True, slots=True)
class ReplaySuiteCase:
    case_id: str
    mode: str
    scene_rel: str
    script_rel: str
    golden_rel: str
    scene_path: Path | None
    script_path: Path
    golden_path: Path
    budgets: ReplayBudgets | None = None


def register(subparsers: argparse._SubParsersAction) -> None:
    replays_parser = subparsers.add_parser(
        "replays",
        help="Replay suite commands",
        description="Run deterministic replay suite with golden ratchet",
    )
    replay_subparsers = replays_parser.add_subparsers(dest="replays_command", help="Replays subcommand")

    run_parser = replay_subparsers.add_parser(
        "run",
        help="Run replay suite and enforce golden digests",
        description=(
            "Runs episode replay-check cases from a suite file, compares outputs against "
            "golden digests, optionally updates goldens, and can enforce per-case perf budgets."
        ),
    )
    run_parser.add_argument("--suite", required=True, help="Path to replay suite JSON")
    run_parser.add_argument("--out-dir", required=True, help="Output directory for replay suite artifacts")
    run_parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Deterministic seed (default: {DEFAULT_SEED})")
    run_parser.add_argument(
        "--update-golden",
        action="store_true",
        help="Deprecated: use `replays update-golden --reason ...` (this flag now errors).",
    )
    run_parser.add_argument(
        "--budgets-only-on",
        choices=["all", "linux", "windows", "none"],
        default="all",
        help="Restrict budget enforcement to one platform kind (default: all)",
    )
    run_parser.add_argument("--json", action="store_true", dest="replays_json", help="Print suite report JSON to stdout")
    run_parser.add_argument("--quiet", action="store_true", help="Suppress non-essential stdout")

    update_parser = replay_subparsers.add_parser(
        "update-golden",
        help="Update replay golden files with deterministic diff reports",
        description=(
            "Runs replay suite cases and writes updated golden digests for all or one case. "
            "Writes deterministic diff reports for review."
        ),
    )
    update_parser.add_argument("--suite", required=True, help="Path to replay suite JSON")
    update_parser.add_argument("--out-dir", required=True, help="Existing output directory for replay update artifacts")
    update_parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Deterministic seed (default: {DEFAULT_SEED})")
    update_parser.add_argument("--case", dest="case_id", help="Optional replay case id to update")
    update_parser.add_argument(
        "--allow-unknown-mode",
        action="store_true",
        help="Allow unknown suite modes by skipping those cases in update-golden",
    )
    update_parser.add_argument("--reason", help="Required justification for changed golden files")
    update_parser.add_argument(
        "--allow-no-reason",
        action="store_true",
        help="Allow golden updates without --reason",
    )
    update_parser.add_argument(
        "--max-changed",
        type=int,
        help="Fail if more than N golden files would change",
    )
    update_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute update report without modifying golden files",
    )
    update_parser.add_argument("--json", action="store_true", dest="replays_json", help="Print update report JSON to stdout")
    update_parser.add_argument("--quiet", action="store_true", help="Suppress non-essential stdout")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "replays_command", None)
    if command == "run":
        return _handle_replays_run(args)
    if command == "update-golden":
        return _handle_replays_update_golden(args)
    print("[Mesh][Replays] Error: missing replays subcommand")
    return 2


def _handle_replays_run(args: argparse.Namespace) -> int:
    json_stdout = bool(getattr(args, "replays_json", False))
    quiet = bool(getattr(args, "quiet", False))
    seed = int(getattr(args, "seed", DEFAULT_SEED))
    update_golden = bool(getattr(args, "update_golden", False))
    budgets_only_on = str(getattr(args, "budgets_only_on", "all") or "all").strip().lower()
    if update_golden:
        print(
            "[Mesh][Replays] ERROR: 'replays run --update-golden' is disabled. "
            "Use 'mesh_cli replays update-golden --reason \"...\"' instead."
        )
        return 2

    try:
        repo_root = _get_repo_root()
        suite_path = _resolve_required_file(
            raw=str(getattr(args, "suite", "") or "").strip(),
            repo_root=repo_root,
            label="suite",
        )
        out_dir = _resolve_output_dir(
            raw=str(getattr(args, "out_dir", "") or "").strip(),
            repo_root=repo_root,
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        suite_cases, _ = _load_suite_cases(suite_path=suite_path, repo_root=repo_root)
        if not suite_cases:
            raise ValueError("suite contains no replay cases")

        budget_enforced = _should_enforce_budgets(budgets_only_on)
        case_reports: list[dict[str, Any]] = []
        failed = 0
        mismatched = 0
        budget_failed = 0
        budget_checked = 0
        budget_skipped = 0
        updated = 0

        for case in suite_cases:
            case_report, case_failed, case_mismatch, case_budget_failed, case_budget_checked, case_budget_skipped, case_updated = _run_suite_case(
                case=case,
                out_dir=out_dir,
                seed=seed,
                update_golden=update_golden,
                enforce_budgets=budget_enforced,
                skip_expected_compare=False,
            )
            case_reports.append(case_report)
            failed += int(case_failed)
            mismatched += int(case_mismatch)
            budget_failed += int(case_budget_failed)
            budget_checked += int(case_budget_checked)
            budget_skipped += int(case_budget_skipped)
            updated += int(case_updated)

        ok = failed == 0
        report = {
            "schema_version": SCHEMA_VERSION,
            "ok": ok,
            "suite": _rel_path(suite_path, repo_root),
            "out_dir": _rel_path(out_dir, repo_root),
            "seed": seed,
            "update_golden": update_golden,
            "budgets_only_on": budgets_only_on,
            "budget_enforced": budget_enforced,
            "summary": {
                "total": len(case_reports),
                "passed": len(case_reports) - failed,
                "failed": failed,
                "mismatched": mismatched,
                "budget_failed": budget_failed,
                "budget_checked": budget_checked,
                "budget_skipped": budget_skipped,
                "updated": updated,
            },
            "cases": case_reports,
            "artifacts": {
                "suite_report_json": "suite_report.json",
                "suite_report_txt": "suite_report.txt",
            },
            "provenance": provenance_to_dict(get_provenance(deterministic=True)),
        }
        _write_suite_reports(out_dir=out_dir, report=report)

        if json_stdout:
            sys.stdout.write(dumps_json_deterministic(report))
            sys.stdout.write("\n")
        elif not quiet:
            print(_format_suite_report_text(report), end="")

        return 0 if ok else 1
    except ValueError as exc:
        print(f"[Mesh][Replays] ERROR: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001  # REASON: replays CLI should collapse unexpected suite failures into a deterministic nonzero exit with context
        print(f"[Mesh][Replays] ERROR: {type(exc).__name__}: {exc}")
        return 1


def _handle_replays_update_golden(args: argparse.Namespace) -> int:
    json_stdout = bool(getattr(args, "replays_json", False))
    quiet = bool(getattr(args, "quiet", False))
    seed = int(getattr(args, "seed", DEFAULT_SEED))
    case_filter = str(getattr(args, "case_id", "") or "").strip()
    allow_unknown_mode = bool(getattr(args, "allow_unknown_mode", False))
    reason = str(getattr(args, "reason", "") or "").strip() or None
    allow_no_reason = bool(getattr(args, "allow_no_reason", False))
    max_changed = getattr(args, "max_changed", None)
    dry_run = bool(getattr(args, "dry_run", False))

    try:
        if max_changed is not None and int(max_changed) < 0:
            raise ValueError("--max-changed must be >= 0")

        repo_root = _get_repo_root()
        suite_path = _resolve_required_file(
            raw=str(getattr(args, "suite", "") or "").strip(),
            repo_root=repo_root,
            label="suite",
        )
        out_dir = _resolve_output_dir(
            raw=str(getattr(args, "out_dir", "") or "").strip(),
            repo_root=repo_root,
            require_exists=True,
        )
        suite_cases, skipped_unknown_modes = _load_suite_cases(
            suite_path=suite_path,
            repo_root=repo_root,
            allow_unknown_modes=allow_unknown_mode,
        )
        if not suite_cases:
            raise ValueError("suite contains no replay cases")

        if case_filter:
            suite_cases = [case for case in suite_cases if case.case_id == case_filter]
            if not suite_cases:
                raise ValueError(f"--case not found in suite: {case_filter}")

        budget_enforced = _should_enforce_budgets("all")
        case_reports: list[dict[str, Any]] = []
        hard_failed = 0
        budget_failed = 0
        changed_cases: list[str] = []
        unchanged_cases: list[str] = []
        pending_writes: list[dict[str, Any]] = []

        for case in suite_cases:
            old_golden_payload = _load_existing_golden_payload(case.golden_path)
            case_report, case_failed, case_mismatch, case_budget_failed, _, _, _ = _run_suite_case(
                case=case,
                out_dir=out_dir,
                seed=seed,
                update_golden=False,
                enforce_budgets=budget_enforced,
                skip_expected_compare=True,
            )
            if isinstance(case_report.get("actual"), dict):
                new_golden_payload = _build_golden_payload(case_report["actual"])
            else:
                new_golden_payload = {}

            golden_diff = _build_golden_diff_payload(
                old_payload=old_golden_payload,
                new_payload=new_golden_payload,
            )
            golden_diff["reason"] = reason

            normalized = _normalize_update_case_report(
                base_case_report=case_report,
                hard_failed=(case_failed - case_budget_failed) > 0 or case_mismatch > 0,
                budget_failed=case_budget_failed > 0,
                golden_diff=golden_diff,
            )
            case_reports.append(normalized)

            if normalized.get("hard_failed"):
                hard_failed += 1
            if normalized.get("budget_highlight"):
                budget_failed += 1
            if normalized.get("golden_changed"):
                changed_cases.append(case.case_id)
            else:
                unchanged_cases.append(case.case_id)
            pending_writes.append(
                {
                    "case": case,
                    "new_golden_payload": new_golden_payload,
                    "golden_diff": golden_diff,
                    "normalized": normalized,
                }
            )

        changed_cases_sorted = sorted(changed_cases)
        unchanged_cases_sorted = sorted(unchanged_cases)
        max_changed_int = int(max_changed) if max_changed is not None else None
        reason_required_failed = (not dry_run) and bool(changed_cases_sorted) and not reason and not allow_no_reason
        max_changed_failed = max_changed_int is not None and len(changed_cases_sorted) > max_changed_int
        policy_errors: list[str] = []
        if reason_required_failed:
            policy_errors.append(
                "golden changes detected; rerun with --reason \"<why>\" or pass --allow-no-reason"
            )
        if max_changed_failed:
            policy_errors.append(
                f"--max-changed={max_changed_int} exceeded by {len(changed_cases_sorted)} change(s): "
                f"{', '.join(changed_cases_sorted)}"
            )

        write_allowed = hard_failed == 0 and not policy_errors and not dry_run
        written_count = 0
        if write_allowed:
            for entry in pending_writes:
                case = entry["case"]
                normalized = entry["normalized"]
                golden_changed = bool(normalized.get("golden_changed"))
                if golden_changed:
                    case.golden_path.parent.mkdir(parents=True, exist_ok=True)
                    write_json_atomic(case.golden_path, entry["new_golden_payload"], indent=2, sort_keys=True, trailing_newline=True)
                    written_count += 1
                normalized["updated_golden"] = golden_changed
                _write_golden_diff(
                    case_out_dir=out_dir / case.case_id,
                    diff=entry["golden_diff"],
                    reason=reason,
                )
        else:
            for entry in pending_writes:
                entry["normalized"]["updated_golden"] = False

        report_ok = hard_failed == 0 and not policy_errors
        report = {
            "schema_version": UPDATE_GOLDEN_SCHEMA_VERSION,
            "ok": report_ok,
            "command": "replays update-golden",
            "suite": _rel_path(suite_path, repo_root),
            "out_dir": _rel_path(out_dir, repo_root),
            "seed": seed,
            "case_filter": case_filter or None,
            "allow_unknown_mode": allow_unknown_mode,
            "reason": reason,
            "allow_no_reason": allow_no_reason,
            "max_changed": max_changed_int,
            "dry_run": dry_run,
            "policy_errors": policy_errors,
            "summary": {
                "selected": len(case_reports),
                "updated": written_count,
                "would_change": len(changed_cases_sorted),
                "changed": len(changed_cases_sorted),
                "unchanged": len(unchanged_cases_sorted),
                "hard_failed": hard_failed,
                "budget_failed": budget_failed,
                "skipped_unknown_modes": len(skipped_unknown_modes),
            },
            "changed_cases": changed_cases_sorted,
            "unchanged_cases": unchanged_cases_sorted,
            "skipped_unknown_modes": skipped_unknown_modes,
            "cases": case_reports,
            "artifacts": {
                "update_report_json": "update_golden_report.json",
                "update_report_txt": "update_golden_report.txt",
            },
            "provenance": provenance_to_dict(get_provenance(deterministic=True)),
        }
        _write_update_reports(out_dir=out_dir, report=report)

        if json_stdout:
            sys.stdout.write(dumps_json_deterministic(report))
            sys.stdout.write("\n")
        elif not quiet:
            print(_format_update_report_text(report), end="")

        return 0 if report_ok else 1
    except ValueError as exc:
        print(f"[Mesh][Replays] ERROR: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001  # REASON: replay update CLI should collapse unexpected suite failures into a deterministic nonzero exit with context
        print(f"[Mesh][Replays] ERROR: {type(exc).__name__}: {exc}")
        return 1


def _run_episode_case(*, case: ReplaySuiteCase, case_out_dir: Path, seed: int) -> int:
    if case.scene_path is None:
        raise ValueError(f"episode case requires scene: {case.case_id}")
    return episode_commands.handle(
        argparse.Namespace(
            command="episode",
            episode_command="replay-check",
            scene=case.scene_path.as_posix(),
            script=case.script_path.as_posix(),
            out_dir=case_out_dir.as_posix(),
            seed=seed,
            quiet=True,
            episode_json=False,
        )
    )


def _run_campaign_case(*, case: ReplaySuiteCase, case_out_dir: Path, seed: int) -> int:
    from tooling.campaign_replay import (
        diff_traces,
        format_diff_text,
        load_campaign_script_from_path,
        run_campaign_replay,
    )

    try:
        _ = seed  # campaign replay scripts are deterministic and seedless today
        seed_ignored = True
        script_payload = load_campaign_script_from_path(case.script_path)

        run_1 = run_campaign_replay(script_payload)
        run_2 = run_campaign_replay(script_payload)

        trace_1 = run_1.to_trace_dict()
        trace_2 = run_2.to_trace_dict()
        diff = diff_traces(trace_1, trace_2)

        # Core campaign replay artifacts.
        write_json_atomic(
            case_out_dir / "run_1_digest_trace.json",
            trace_1,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )
        write_json_atomic(
            case_out_dir / "run_2_digest_trace.json",
            trace_2,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )
        write_json_atomic(
            case_out_dir / "digest_diff.json",
            diff,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )
        write_text_atomic(case_out_dir / "digest_diff.txt", format_diff_text(diff), encoding="utf-8")

        event_types_1 = [str(event_type) for event_type in trace_1.get("event_types", [])]
        event_types_2 = [str(event_type) for event_type in trace_2.get("event_types", [])]
        digests_obj = trace_1.get("digests", {})
        digest_items: list[dict[str, Any]] = []
        if isinstance(digests_obj, dict):
            for key, value in sorted(digests_obj.items(), key=lambda item: int(item[0])):
                digest_items.append({"tick": int(key), "digest": str(value)})

        run_1_ok = bool(diff.get("identical"))
        determinism = {
            "digests_match": bool(diff.get("identical")),
            "events_match": event_types_1 == event_types_2,
            "final_state_match": trace_1.get("final_flags") == trace_2.get("final_flags"),
        }
        overall_ok = run_1_ok and all(bool(value) for value in determinism.values())

        # Episode-like artifacts so suite collection stays shared.
        events_lines = [
            json.dumps({"event_type": event_type}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for event_type in event_types_1
        ]
        events_text = "\n".join(events_lines)
        if events_lines:
            events_text += "\n"
        write_text_atomic(case_out_dir / "events.ndjson", events_text, encoding="utf-8")

        write_json_atomic(
            case_out_dir / "digests.json",
            {"schema_version": 1, "digests": digest_items},
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )

        final_state_payload = {
            "schema_version": 1,
            "final_state": {
                "campaign_id": str(script_payload.get("campaign_id", "")),
                "final_flags": dict(trace_1.get("final_flags", {})) if isinstance(trace_1.get("final_flags"), dict) else {},
                "checkpoints": run_1.checkpoints,
                "milestones": run_1.milestone_log,
            },
            "snapshots": list(run_1.milestone_log),
        }
        write_json_atomic(
            case_out_dir / "final_state_bundle.json",
            final_state_payload,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )

        # Stable timing payload for budget checks.
        tick_ms_list = [0.0 for _ in digest_items]
        replay_report = {
            "schema_version": 1,
            "ok": overall_ok,
            "seed": seed,
            "seed_ignored": seed_ignored,
            "scene": case.scene_rel,
            "script": case.script_rel,
            "determinism": determinism,
            "run_1": {
                "ok": run_1_ok,
                "error": None if run_1_ok else diff.get("summary"),
                "event_count": len(event_types_1),
                "digest_count": len(digest_items),
                "snapshot_count": len(run_1.milestone_log),
                "save_actions": 0,
                "restore_actions": 0,
                "timing": {
                    "total_ms": 0.0,
                    "tick_ms_count": len(tick_ms_list),
                    "tick_ms_list": tick_ms_list,
                    "tick_ms_p50": 0.0,
                    "tick_ms_p95": 0.0,
                    "tick_ms_max": 0.0,
                },
            },
            "run_2": {
                "ok": bool(diff.get("identical")),
                "error": None if diff.get("identical") else diff.get("summary"),
                "event_count": len(event_types_2),
                "digest_count": len(trace_2.get("digests", {})) if isinstance(trace_2.get("digests"), dict) else 0,
                "snapshot_count": len(run_2.milestone_log),
                "save_actions": 0,
                "restore_actions": 0,
                "timing": {
                    "total_ms": 0.0,
                    "tick_ms_count": 0,
                    "tick_ms_list": [],
                    "tick_ms_p50": 0.0,
                    "tick_ms_p95": 0.0,
                    "tick_ms_max": 0.0,
                },
            },
            "artifacts": {
                "report_json": "replay_report.json",
                "report_txt": "replay_report.txt",
                "events_ndjson": "events.ndjson",
                "digests_json": "digests.json",
                "final_state_bundle_json": "final_state_bundle.json",
                "campaign_run_1_trace_json": "run_1_digest_trace.json",
                "campaign_run_2_trace_json": "run_2_digest_trace.json",
                "campaign_diff_json": "digest_diff.json",
                "campaign_diff_txt": "digest_diff.txt",
            },
        }
        write_json_atomic(
            case_out_dir / "replay_report.json",
            replay_report,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )
        write_text_atomic(
            case_out_dir / "replay_report.txt",
            _format_campaign_replay_report_text(replay_report),
            encoding="utf-8",
        )
        return 0 if overall_ok else 1
    except Exception:
        return 1


def _format_campaign_replay_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Mesh Campaign Replay")
    lines.append(f"Result: {'OK' if report.get('ok') else 'FAILED'}")
    lines.append(f"Scene: {report.get('scene')}")
    lines.append(f"Script: {report.get('script')}")
    lines.append(f"Seed Ignored: {bool(report.get('seed_ignored', False))}")
    determinism = report.get("determinism", {})
    lines.append(f"Digests Match: {determinism.get('digests_match')}")
    lines.append(f"Events Match: {determinism.get('events_match')}")
    lines.append(f"Final State Match: {determinism.get('final_state_match')}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _run_suite_case(
    *,
    case: ReplaySuiteCase,
    out_dir: Path,
    seed: int,
    update_golden: bool,
    enforce_budgets: bool,
    skip_expected_compare: bool = False,
) -> tuple[dict[str, Any], int, int, int, int, int, int]:
    case_out_dir = out_dir / case.case_id
    if case_out_dir.exists():
        shutil.rmtree(case_out_dir)
    case_out_dir.mkdir(parents=True, exist_ok=True)

    if case.mode == "campaign":
        run_code = _run_campaign_case(case=case, case_out_dir=case_out_dir, seed=seed)
    else:
        run_code = _run_episode_case(case=case, case_out_dir=case_out_dir, seed=seed)

    budget_placeholder: dict[str, Any] = {
        "ok": True,
        "skipped": case.budgets is None,
        "reason": "no budgets configured" if case.budgets is None else None,
        "enforced": False,
        "limits": case.budgets.to_dict() if case.budgets is not None else {},
        "observed": {},
        "violations": [],
    }
    case_report: dict[str, Any] = {
        "id": case.case_id,
        "mode": case.mode,
        "scene": case.scene_rel,
        "script": case.script_rel,
        "golden": case.golden_rel,
        "out_dir": case.case_id,
        "run_ok": run_code == 0,
        "match": False,
        "ok": False,
        "updated_golden": False,
        "error": None,
        "mismatches": [],
        "actual": None,
        "expected": None,
        "budget": budget_placeholder,
        "artifacts": {
            "replay_report_json": f"{case.case_id}/replay_report.json",
            "replay_report_txt": f"{case.case_id}/replay_report.txt",
            "events_ndjson": f"{case.case_id}/events.ndjson",
            "digests_json": f"{case.case_id}/digests.json",
            "final_state_bundle_json": f"{case.case_id}/final_state_bundle.json",
            "performance_json": f"{case.case_id}/performance.json",
        },
    }
    case_failed = 0
    case_mismatch = 0
    case_budget_failed = 0
    case_budget_checked = 0
    case_budget_skipped = 0
    case_updated = 0

    if run_code != 0:
        case_report["error"] = f"replay-check failed (exit={run_code})"
        _write_case_performance_artifact(case_out_dir=case_out_dir, case=case, performance={}, budget=budget_placeholder)
        return case_report, 1, 0, 0, 0, 1, 0

    try:
        actual = _collect_case_actual(case=case, case_out_dir=case_out_dir)
    except ValueError as exc:
        case_report["error"] = str(exc)
        _write_case_performance_artifact(case_out_dir=case_out_dir, case=case, performance={}, budget=budget_placeholder)
        return case_report, 1, 0, 0, 0, 1, 0
    case_report["actual"] = actual
    if case.mode == "campaign":
        case_report["seed_ignored"] = bool(actual.get("seed_ignored", False))

    budget_result = _evaluate_case_budget(
        budgets=case.budgets,
        performance=actual.get("performance", {}),
        enforce_budgets=enforce_budgets,
    )
    case_report["budget"] = budget_result
    if budget_result.get("skipped"):
        case_budget_skipped = 1
    else:
        case_budget_checked = 1
        if not budget_result.get("ok", False):
            case_budget_failed = 1
            case_failed = 1

    _write_case_performance_artifact(
        case_out_dir=case_out_dir,
        case=case,
        performance=actual.get("performance", {}),
        budget=budget_result,
    )

    if skip_expected_compare:
        case_report["match"] = True
        if case_budget_failed:
            case_report["error"] = "budget exceeded"
            case_report["ok"] = False
        else:
            case_report["error"] = None
            case_report["ok"] = bool(case_report["run_ok"])
        return case_report, case_failed, 0, case_budget_failed, case_budget_checked, case_budget_skipped, 0

    if update_golden:
        case.golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_payload = _build_golden_payload(actual)
        write_json_atomic(case.golden_path, golden_payload, indent=2, sort_keys=True, trailing_newline=True)
        case_report["updated_golden"] = True
        case_updated = 1

    if not case.golden_path.exists():
        case_report["error"] = f"golden file not found: {case.golden_rel}"
        case_report["mismatches"] = [{"field": "golden", "expected": "file exists", "actual": "missing"}]
        case_report["ok"] = False
        return case_report, 1, 1, case_budget_failed, case_budget_checked, case_budget_skipped, case_updated

    try:
        expected_payload = _load_json_artifact(case.golden_path, label=case.golden_rel)
    except ValueError as exc:
        case_report["error"] = str(exc)
        case_report["ok"] = False
        return case_report, 1, 1, case_budget_failed, case_budget_checked, case_budget_skipped, case_updated
    if not isinstance(expected_payload, dict):
        case_report["error"] = f"golden file must be a JSON object: {case.golden_rel}"
        case_report["ok"] = False
        return case_report, 1, 1, case_budget_failed, case_budget_checked, case_budget_skipped, case_updated

    case_report["expected"] = _project_expected(expected_payload)
    mismatches = _compare_expected_vs_actual(expected_payload, actual)
    case_report["mismatches"] = mismatches
    case_report["match"] = not mismatches

    if mismatches:
        case_mismatch = 1
        case_failed = 1

    if case_mismatch and case_budget_failed:
        case_report["error"] = f"golden mismatch ({len(mismatches)} field(s)); budget exceeded"
    elif case_mismatch:
        case_report["error"] = f"golden mismatch ({len(mismatches)} field(s))"
    elif case_budget_failed:
        case_report["error"] = "budget exceeded"
    else:
        case_report["error"] = None

    case_report["ok"] = case_report["run_ok"] and case_report["match"] and bool(case_report["budget"].get("ok", True))
    return case_report, case_failed, case_mismatch, case_budget_failed, case_budget_checked, case_budget_skipped, case_updated


def _collect_case_actual(*, case: ReplaySuiteCase, case_out_dir: Path) -> dict[str, Any]:
    replay_report_path = case_out_dir / "replay_report.json"
    events_path = case_out_dir / "events.ndjson"
    digests_path = case_out_dir / "digests.json"
    final_state_path = case_out_dir / "final_state_bundle.json"
    timings_path = case_out_dir / "timings.json"

    replay_report = _load_json_artifact(replay_report_path, label=replay_report_path.name)
    if not isinstance(replay_report, dict):
        raise ValueError(f"invalid replay report JSON: {replay_report_path.name}")
    events = _read_events_ndjson(events_path)

    digests_payload = _load_json_artifact(digests_path, label=digests_path.name)
    if not isinstance(digests_payload, dict):
        raise ValueError(f"invalid digests JSON: {digests_path.name}")
    digests_raw = digests_payload.get("digests", [])
    if not isinstance(digests_raw, list):
        raise ValueError(f"invalid digests JSON: digests must be an array in {digests_path.name}")

    final_state_payload = _load_json_artifact(final_state_path, label=final_state_path.name)
    if not isinstance(final_state_payload, dict):
        raise ValueError(f"invalid final state JSON: {final_state_path.name}")
    final_state_payload, _ = normalize_save_payload(
        final_state_payload,
        source=final_state_path.name,
    )
    snapshots_raw = final_state_payload.get("snapshots", [])
    if not isinstance(snapshots_raw, list):
        snapshots_raw = []

    run_1 = replay_report.get("run_1", {})
    replay_report_timing: dict[str, Any] = {}
    if isinstance(run_1, dict):
        candidate = run_1.get("timing", {})
        if isinstance(candidate, dict):
            replay_report_timing = candidate

    timing_source = replay_report_timing
    if timings_path.exists():
        timings_payload = _load_json_artifact(timings_path, label=timings_path.name)
        if not isinstance(timings_payload, dict):
            raise ValueError(f"invalid timings JSON: {timings_path.name}")
        raw_timing = timings_payload.get("timing", {})
        if not isinstance(raw_timing, dict):
            raise ValueError(f"invalid timings JSON: timing must be an object in {timings_path.name}")
        timing_source = raw_timing

    performance = _extract_performance_metrics(timing_source)

    event_types = [_event_type_label(event) for event in events]
    digest_values = [_digest_label(entry) for entry in digests_raw]
    events_for_digest = [_project_event_for_golden_digest(event) for event in events]
    world_digests_for_digest = _project_world_digests_for_golden_digest(digests_raw)
    final_state_for_digest = _project_final_state_for_golden_digest(final_state_payload)

    return {
        "schema_version": GOLDEN_SCHEMA_VERSION,
        "id": case.case_id,
        "scene": case.scene_rel,
        "script": case.script_rel,
        "seed_ignored": bool(replay_report.get("seed_ignored", False)),
        "expected_event_digest": _sha256_payload(events_for_digest),
        "expected_world_digest": _sha256_payload(world_digests_for_digest),
        "expected_final_state_digest": _sha256_payload(final_state_for_digest),
        "counts": {
            "event_count": len(events),
            "world_digest_count": len(digests_raw),
            "snapshot_count": len(snapshots_raw),
        },
        "sample": {
            "events_first": event_types[:_PREVIEW_ITEMS],
            "events_last": event_types[-_PREVIEW_ITEMS:] if event_types else [],
            "world_digests_first": digest_values[:_PREVIEW_ITEMS],
            "world_digests_last": digest_values[-_PREVIEW_ITEMS:] if digest_values else [],
        },
        "run_ok": bool(replay_report.get("ok")),
        "run_determinism": dict(replay_report.get("determinism", {}))
        if isinstance(replay_report.get("determinism"), dict)
        else {},
        "performance": performance,
    }


def _build_golden_payload(actual: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": GOLDEN_SCHEMA_VERSION,
        "id": actual.get("id"),
        "scene": actual.get("scene"),
        "script": actual.get("script"),
        "expected_event_digest": actual.get("expected_event_digest"),
        "expected_world_digest": actual.get("expected_world_digest"),
        "expected_final_state_digest": actual.get("expected_final_state_digest"),
        "counts": dict(actual.get("counts", {})) if isinstance(actual.get("counts"), dict) else {},
        "sample": dict(actual.get("sample", {})) if isinstance(actual.get("sample"), dict) else {},
    }
    run_determinism = actual.get("run_determinism")
    if isinstance(run_determinism, dict):
        payload["run_determinism"] = dict(run_determinism)
    if "run_ok" in actual:
        payload["run_ok"] = bool(actual.get("run_ok"))
    return payload


def _load_existing_golden_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = _load_json_artifact(path, label=path.name)
    if not isinstance(payload, dict):
        raise ValueError(f"golden file must be a JSON object: {path.name}")
    return payload


def _build_golden_diff_payload(*, old_payload: dict[str, Any] | None, new_payload: dict[str, Any]) -> dict[str, Any]:
    old = _project_expected(old_payload) if isinstance(old_payload, dict) else _project_expected({})
    new = _project_expected(new_payload)

    changed_fields: list[str] = []
    for field in ("expected_event_digest", "expected_world_digest", "expected_final_state_digest", "counts", "sample"):
        if old.get(field) != new.get(field):
            changed_fields.append(field)
    changed_fields_sorted = sorted(changed_fields)

    mismatch_index = _first_list_mismatch(
        old_payload.get("world_digest_sequence") if isinstance(old_payload, dict) else None,
        new_payload.get("world_digest_sequence") if isinstance(new_payload, dict) else None,
    )

    return {
        "changed": bool(changed_fields),
        "changed_fields": changed_fields_sorted,
        "old": old,
        "new": new,
        "world_digest_first_mismatch_index": mismatch_index,
        "world_digest_first_mismatch_available": mismatch_index is not None,
    }


def _first_list_mismatch(lhs: Any, rhs: Any) -> int | None:
    if not isinstance(lhs, list) or not isinstance(rhs, list):
        return None
    limit = min(len(lhs), len(rhs))
    for index in range(limit):
        if lhs[index] != rhs[index]:
            return index
    if len(lhs) != len(rhs):
        return limit
    return None


def _write_golden_diff(*, case_out_dir: Path, diff: dict[str, Any], reason: str | None) -> None:
    write_text_atomic(case_out_dir / "golden_diff.txt", _format_golden_diff_text(diff, reason=reason), encoding="utf-8")


def _format_golden_diff_text(diff: dict[str, Any], *, reason: str | None) -> str:
    old = diff.get("old", {}) if isinstance(diff.get("old"), dict) else {}
    new = diff.get("new", {}) if isinstance(diff.get("new"), dict) else {}
    lines: list[str] = []
    lines.append("Mesh Replay Golden Diff")
    lines.append(f"Reason: {reason or 'none'}")
    lines.append(f"Changed: {bool(diff.get('changed'))}")
    lines.append(f"Changed Fields: {', '.join(diff.get('changed_fields', [])) if diff.get('changed_fields') else 'none'}")
    lines.append(f"Event Digest: {old.get('expected_event_digest')} -> {new.get('expected_event_digest')}")
    lines.append(f"World Digest: {old.get('expected_world_digest')} -> {new.get('expected_world_digest')}")
    lines.append(f"Final State Digest: {old.get('expected_final_state_digest')} -> {new.get('expected_final_state_digest')}")
    if diff.get("world_digest_first_mismatch_available"):
        lines.append(f"World Digest First Mismatch Index: {diff.get('world_digest_first_mismatch_index')}")
    else:
        lines.append("World Digest First Mismatch Index: unavailable")
    old_counts = old.get("counts", {}) if isinstance(old.get("counts"), dict) else {}
    new_counts = new.get("counts", {}) if isinstance(new.get("counts"), dict) else {}
    for key in ("event_count", "world_digest_count", "snapshot_count"):
        lines.append(f"Count {key}: {old_counts.get(key)} -> {new_counts.get(key)}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _normalize_update_case_report(
    *,
    base_case_report: dict[str, Any],
    hard_failed: bool,
    budget_failed: bool,
    golden_diff: dict[str, Any],
) -> dict[str, Any]:
    report = dict(base_case_report)
    report["hard_failed"] = bool(hard_failed)
    report["budget_highlight"] = bool(budget_failed)
    report["golden_changed"] = bool(golden_diff.get("changed"))
    report["golden_diff"] = f"{str(report.get('id', 'unknown'))}/golden_diff.txt"
    report["golden_diff_payload"] = golden_diff
    artifacts = dict(report.get("artifacts", {})) if isinstance(report.get("artifacts"), dict) else {}
    artifacts["golden_diff_txt"] = report["golden_diff"]
    report["artifacts"] = artifacts

    if report["hard_failed"]:
        report["ok"] = False
    else:
        report["ok"] = True
        if budget_failed:
            report["warning"] = "budget exceeded"
            if str(report.get("error", "")).strip().startswith("budget exceeded"):
                report["error"] = None
        else:
            report["warning"] = None
            report["error"] = None
    return report


def _extract_performance_metrics(timing_payload: dict[str, Any]) -> dict[str, Any]:
    tick_ms_list_raw = timing_payload.get("tick_ms_list", [])
    tick_ms_list: list[float] = []
    if isinstance(tick_ms_list_raw, list):
        for value in tick_ms_list_raw:
            try:
                tick_ms_list.append(_round_ms(float(value)))
            except (TypeError, ValueError):
                continue
    total_ms = _number_from_payload(timing_payload, "total_ms")
    tick_ms_p50 = _number_from_payload(timing_payload, "tick_ms_p50")
    tick_ms_p95 = _number_from_payload(timing_payload, "tick_ms_p95")
    tick_ms_max = _number_from_payload(timing_payload, "tick_ms_max")
    tick_ms_count = _int_from_payload(timing_payload, "tick_ms_count")
    if tick_ms_count <= 0:
        tick_ms_count = len(tick_ms_list)

    return {
        "total_ms": total_ms,
        "tick_ms_count": tick_ms_count,
        "tick_ms_list": tick_ms_list,
        "tick_ms_p50": tick_ms_p50,
        "tick_ms_p95": tick_ms_p95,
        "tick_ms_max": tick_ms_max,
    }


def _evaluate_case_budget(
    *,
    budgets: ReplayBudgets | None,
    performance: Any,
    enforce_budgets: bool,
) -> dict[str, Any]:
    if budgets is None:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no budgets configured",
            "enforced": False,
            "limits": {},
            "observed": {},
            "violations": [],
        }

    limits = budgets.to_dict()
    observed: dict[str, float | None] = {}
    if isinstance(performance, dict):
        observed["total_ms"] = _number_from_payload(performance, "total_ms")
        observed["tick_ms_p95"] = _number_from_payload(performance, "tick_ms_p95")
        observed["tick_ms_max"] = _number_from_payload(performance, "tick_ms_max")
    else:
        observed["total_ms"] = None
        observed["tick_ms_p95"] = None
        observed["tick_ms_max"] = None

    if not enforce_budgets:
        return {
            "ok": True,
            "skipped": True,
            "reason": "budget enforcement disabled on this platform",
            "enforced": False,
            "limits": limits,
            "observed": observed,
            "violations": [],
        }

    comparisons: list[tuple[str, str, float | None, float | None]] = [
        ("total_ms", "max_total_ms", observed.get("total_ms"), budgets.max_total_ms),
        ("tick_ms_p95", "max_tick_ms_p95", observed.get("tick_ms_p95"), budgets.max_tick_ms_p95),
        ("tick_ms_max", "max_tick_ms_max", observed.get("tick_ms_max"), budgets.max_tick_ms_max),
    ]
    violations: list[dict[str, Any]] = []
    for metric_name, limit_name, observed_value, limit_value in comparisons:
        if limit_value is None:
            continue
        if observed_value is None:
            violations.append(
                {
                    "metric": metric_name,
                    "threshold": limit_value,
                    "observed": None,
                    "reason": "metric unavailable",
                }
            )
            continue
        if observed_value > limit_value:
            violations.append(
                {
                    "metric": metric_name,
                    "threshold": limit_value,
                    "observed": observed_value,
                    "reason": f"{metric_name} exceeds {limit_name}",
                }
            )

    return {
        "ok": not violations,
        "skipped": False,
        "reason": None if not violations else f"{len(violations)} budget threshold(s) exceeded",
        "enforced": True,
        "limits": limits,
        "observed": observed,
        "violations": violations,
    }


def _write_case_performance_artifact(
    *,
    case_out_dir: Path,
    case: ReplaySuiteCase,
    performance: Any,
    budget: dict[str, Any],
) -> None:
    payload = {
        "schema_version": PERF_SCHEMA_VERSION,
        "id": case.case_id,
        "scene": case.scene_rel,
        "script": case.script_rel,
        "performance": performance if isinstance(performance, dict) else {},
        "budget": budget,
    }
    write_json_atomic(case_out_dir / "performance.json", payload, indent=2, sort_keys=True, trailing_newline=True)


def _project_expected(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": int(payload.get("schema_version", 0) or 0),
        "expected_event_digest": str(payload.get("expected_event_digest", "")),
        "expected_world_digest": str(payload.get("expected_world_digest", "")),
        "expected_final_state_digest": str(payload.get("expected_final_state_digest", "")),
        "counts": dict(payload.get("counts", {})) if isinstance(payload.get("counts"), dict) else {},
        "sample": dict(payload.get("sample", {})) if isinstance(payload.get("sample"), dict) else {},
    }


def _compare_expected_vs_actual(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    checks: list[tuple[str, Any, Any]] = [
        ("expected_event_digest", expected.get("expected_event_digest"), actual.get("expected_event_digest")),
        ("expected_world_digest", expected.get("expected_world_digest"), actual.get("expected_world_digest")),
        ("expected_final_state_digest", expected.get("expected_final_state_digest"), actual.get("expected_final_state_digest")),
    ]

    expected_counts = expected.get("counts", {})
    actual_counts = actual.get("counts", {})
    if isinstance(expected_counts, dict) and isinstance(actual_counts, dict):
        for key in ("event_count", "world_digest_count", "snapshot_count"):
            checks.append((f"counts.{key}", expected_counts.get(key), actual_counts.get(key)))

    expected_sample = expected.get("sample", {})
    actual_sample = actual.get("sample", {})
    if isinstance(expected_sample, dict) and isinstance(actual_sample, dict):
        for key in ("events_first", "events_last", "world_digests_first", "world_digests_last"):
            checks.append((f"sample.{key}", expected_sample.get(key), actual_sample.get(key)))

    for field, expected_value, actual_value in sorted(checks, key=lambda item: item[0]):
        if expected_value != actual_value:
            mismatches.append(
                {
                    "field": field,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )
    return mismatches


def _load_suite_cases(
    *,
    suite_path: Path,
    repo_root: Path,
    allow_unknown_modes: bool = False,
) -> tuple[list[ReplaySuiteCase], list[dict[str, str]]]:
    payload = _load_json_file(suite_path)
    if not isinstance(payload, list):
        raise ValueError(f"suite must be a JSON array: {_rel_path(suite_path, repo_root)}")

    out: list[ReplaySuiteCase] = []
    skipped_unknown_modes: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValueError(f"suite[{index}] must be an object")
        case_id = str(entry.get("id", "")).strip()
        if not case_id:
            raise ValueError(f"suite[{index}].id is required")
        if case_id in seen_ids:
            raise ValueError(f"duplicate suite case id: {case_id}")
        seen_ids.add(case_id)

        if not case_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"suite[{index}].id must be alphanumeric plus '_' or '-': {case_id}")

        mode = str(entry.get("mode", "episode") or "episode").strip().lower()
        if mode not in {"episode", "campaign"}:
            if not allow_unknown_modes:
                raise ValueError(f"suite[{index}].mode must be 'episode' or 'campaign'")
            skipped_unknown_modes.append(
                {
                    "id": case_id,
                    "mode": mode or "<empty>",
                }
            )
            continue

        scene_path: Path | None = None
        scene_rel = "<campaign>"
        if mode == "episode":
            scene_path = _resolve_required_file(
                raw=str(entry.get("scene", "") or "").strip(),
                repo_root=repo_root,
                label=f"suite[{index}].scene",
            )
            scene_rel = _rel_path(scene_path, repo_root)
        elif str(entry.get("scene", "") or "").strip():
            optional_scene = _resolve_required_file(
                raw=str(entry.get("scene", "") or "").strip(),
                repo_root=repo_root,
                label=f"suite[{index}].scene",
            )
            scene_rel = _rel_path(optional_scene, repo_root)

        script_path = _resolve_required_file(
            raw=str(entry.get("script", "") or "").strip(),
            repo_root=repo_root,
            label=f"suite[{index}].script",
        )
        golden_path = _resolve_path(
            raw=str(entry.get("golden", "") or "").strip(),
            repo_root=repo_root,
            label=f"suite[{index}].golden",
        )
        budgets = _parse_case_budgets(entry.get("budgets"), index=index)

        out.append(
            ReplaySuiteCase(
                case_id=case_id,
                mode=mode,
                scene_rel=scene_rel,
                script_rel=_rel_path(script_path, repo_root),
                golden_rel=_rel_path(golden_path, repo_root),
                scene_path=scene_path,
                script_path=script_path,
                golden_path=golden_path,
                budgets=budgets,
            )
        )
    return out, sorted(skipped_unknown_modes, key=lambda item: (item.get("id", ""), item.get("mode", "")))


def _parse_case_budgets(raw: Any, *, index: int) -> ReplayBudgets | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"suite[{index}].budgets must be an object")

    max_total_ms = _parse_budget_number(raw, "max_total_ms", index=index)
    max_tick_ms_p95 = _parse_budget_number(raw, "max_tick_ms_p95", index=index)
    max_tick_ms_max = _parse_budget_number(raw, "max_tick_ms_max", index=index)

    if max_total_ms is None and max_tick_ms_p95 is None and max_tick_ms_max is None:
        raise ValueError(f"suite[{index}].budgets must define at least one threshold")
    return ReplayBudgets(
        max_total_ms=max_total_ms,
        max_tick_ms_p95=max_tick_ms_p95,
        max_tick_ms_max=max_tick_ms_max,
    )


def _parse_budget_number(raw: dict[str, Any], key: str, *, index: int) -> float | None:
    if key not in raw or raw.get(key) is None:
        return None
    value = raw[key]
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"suite[{index}].budgets.{key} must be numeric") from exc
    if number <= 0:
        raise ValueError(f"suite[{index}].budgets.{key} must be > 0")
    return _round_ms(number)


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {path.as_posix()}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at {path.as_posix()}: {exc}") from exc


def _load_json_artifact(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {label}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at {label}: {exc}") from exc


def _read_events_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing events artifact: {path.name}")
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid NDJSON line {index + 1} in {path.name}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"events NDJSON line {index + 1} in {path.name} must be an object")
        events.append(payload)
    return events


def _sha256_payload(payload: Any) -> str:
    canonical = dumps_json_deterministic(payload, trailing_newline=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_type_label(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "")).strip()
    if event_type:
        return event_type
    return dumps_json_deterministic(event, trailing_newline=False)


def _digest_label(entry: Any) -> str:
    if isinstance(entry, dict):
        digest = str(entry.get("digest", "")).strip()
        if digest:
            return digest
    return dumps_json_deterministic(entry, trailing_newline=False)


def _write_suite_reports(*, out_dir: Path, report: dict[str, Any]) -> None:
    write_json_atomic(out_dir / "suite_report.json", report, indent=2, sort_keys=True, trailing_newline=True)
    write_text_atomic(out_dir / "suite_report.txt", _format_suite_report_text(report), encoding="utf-8")


def _write_update_reports(*, out_dir: Path, report: dict[str, Any]) -> None:
    write_json_atomic(out_dir / "update_golden_report.json", report, indent=2, sort_keys=True, trailing_newline=True)
    write_text_atomic(out_dir / "update_golden_report.txt", _format_update_report_text(report), encoding="utf-8")


def _format_update_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Mesh Replay Golden Update")
    lines.append(f"Result: {'OK' if report.get('ok') else 'FAILED'}")
    lines.append(f"Suite: {report.get('suite')}")
    lines.append(f"Out Dir: {report.get('out_dir')}")
    lines.append(f"Seed: {report.get('seed')}")
    lines.append(f"Case Filter: {report.get('case_filter')}")
    lines.append(f"Dry Run: {report.get('dry_run')}")
    lines.append(f"Reason: {report.get('reason') or 'none'}")
    lines.append(f"Allow No Reason: {report.get('allow_no_reason')}")
    lines.append(f"Max Changed: {report.get('max_changed')}")
    lines.append("")
    summary = report.get("summary", {})
    lines.append(
        "Summary: "
        f"selected={summary.get('selected')} "
        f"updated={summary.get('updated')} "
        f"would_change={summary.get('would_change')} "
        f"changed={summary.get('changed')} "
        f"unchanged={summary.get('unchanged')} "
        f"hard_failed={summary.get('hard_failed')} "
        f"budget_failed={summary.get('budget_failed')} "
        f"skipped_unknown_modes={summary.get('skipped_unknown_modes')}"
    )
    lines.append(f"Changed Cases: {', '.join(report.get('changed_cases', [])) or 'none'}")
    lines.append(f"Unchanged Cases: {', '.join(report.get('unchanged_cases', [])) or 'none'}")
    lines.append("")
    lines.append("Cases:")
    for case in report.get("cases", []):
        case_id = str(case.get("id", ""))
        mode = str(case.get("mode", "episode"))
        if case.get("hard_failed"):
            lines.append(f"- {case_id} [{mode}]: FAILED ({case.get('error')})")
        else:
            lines.append(
                f"- {case_id} [{mode}]: {('UPDATED' if case.get('updated_golden') else 'CHECKED')} "
                f"(changed={case.get('golden_changed')} budget_highlight={case.get('budget_highlight')})"
            )
            if case.get("warning"):
                lines.append(f"  * warning: {case.get('warning')}")
        lines.append(f"  * diff: {case.get('golden_diff')}")
    policy_errors = report.get("policy_errors", [])
    if isinstance(policy_errors, list) and policy_errors:
        lines.append("")
        lines.append("Policy Errors:")
        for entry in policy_errors:
            lines.append(f"- {entry}")
    skipped_unknown_modes = report.get("skipped_unknown_modes", [])
    if isinstance(skipped_unknown_modes, list) and skipped_unknown_modes:
        lines.append("")
        lines.append("Skipped Unknown Modes:")
        for entry in skipped_unknown_modes:
            if not isinstance(entry, dict):
                continue
            lines.append(f"- {entry.get('id')}: mode={entry.get('mode')}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _format_suite_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Mesh Replay Suite")
    lines.append(f"Result: {'OK' if report.get('ok') else 'FAILED'}")
    lines.append(f"Suite: {report.get('suite')}")
    lines.append(f"Out Dir: {report.get('out_dir')}")
    lines.append(f"Seed: {report.get('seed')}")
    lines.append(f"Update Golden: {report.get('update_golden')}")
    lines.append(f"Budgets: only_on={report.get('budgets_only_on')} enforced={report.get('budget_enforced')}")
    lines.append("")
    summary = report.get("summary", {})
    lines.append(
        "Summary: "
        f"total={summary.get('total')} "
        f"passed={summary.get('passed')} "
        f"failed={summary.get('failed')} "
        f"mismatched={summary.get('mismatched')} "
        f"budget_failed={summary.get('budget_failed')} "
        f"updated={summary.get('updated')}"
    )
    lines.append("")
    lines.append("Cases:")
    for case in report.get("cases", []):
        case_id = str(case.get("id", ""))
        mode = str(case.get("mode", "episode"))
        budget = case.get("budget", {}) if isinstance(case.get("budget"), dict) else {}
        if case.get("ok"):
            counts = case.get("actual", {}).get("counts", {}) if isinstance(case.get("actual"), dict) else {}
            perf = case.get("actual", {}).get("performance", {}) if isinstance(case.get("actual"), dict) else {}
            lines.append(
                f"- {case_id} [{mode}]: OK "
                f"(events={counts.get('event_count')} digests={counts.get('world_digest_count')} "
                f"snapshots={counts.get('snapshot_count')} total_ms={perf.get('total_ms')} p95_ms={perf.get('tick_ms_p95')} max_ms={perf.get('tick_ms_max')})"
            )
            if budget.get("skipped"):
                lines.append(f"  * budget: SKIPPED ({budget.get('reason')})")
        else:
            lines.append(f"- {case_id} [{mode}]: FAILED ({case.get('error')})")
            mismatches = case.get("mismatches", [])
            if isinstance(mismatches, list):
                for mismatch in mismatches[:3]:
                    if not isinstance(mismatch, dict):
                        continue
                    lines.append(f"  * {mismatch.get('field')}: expected={mismatch.get('expected')} actual={mismatch.get('actual')}")
            violations = budget.get("violations", [])
            if isinstance(violations, list):
                for violation in violations:
                    if not isinstance(violation, dict):
                        continue
                    lines.append(
                        f"  * budget {violation.get('metric')}: "
                        f"threshold={violation.get('threshold')} observed={violation.get('observed')}"
                    )
    lines.append("")
    return "\n".join(lines) + "\n"


def _number_from_payload(payload: Any, key: str) -> float | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if value is None:
        return None
    try:
        return _round_ms(float(value))
    except (TypeError, ValueError):
        return None


def _int_from_payload(payload: Any, key: str) -> int:
    if not isinstance(payload, dict):
        return 0
    value = payload.get(key)
    if value is None:
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _round_ms(value: float, *, decimals: int = 3) -> float:
    return float(f"{float(value):.{decimals}f}")


def _should_enforce_budgets(selector: str) -> bool:
    selector_norm = selector.strip().lower()
    if selector_norm == "none":
        return False
    if selector_norm == "all":
        return True

    platform_name = _platform_name()
    if selector_norm == "linux":
        return platform_name == "linux"
    if selector_norm == "windows":
        return platform_name == "windows"
    return True


def _platform_name() -> str:
    raw = sys.platform.lower()
    if raw.startswith("linux"):
        return "linux"
    if raw.startswith("win"):
        return "windows"
    return "other"


def _get_repo_root() -> Path:
    try:
        from engine.repo_root import get_repo_root

        return get_repo_root(start=Path.cwd(), strict=True)
    except Exception:
        return Path.cwd().resolve()


def _resolve_required_file(*, raw: str, repo_root: Path, label: str) -> Path:
    path = _resolve_path(raw=raw, repo_root=repo_root, label=label)
    if not path.exists() or not path.is_file():
        raise ValueError(f"{label} not found: {raw}")
    return path


def _resolve_output_dir(*, raw: str, repo_root: Path, require_exists: bool = False) -> Path:
    if not raw:
        raise ValueError("--out-dir is required")
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    resolved = path.resolve()
    if require_exists and (not resolved.exists() or not resolved.is_dir()):
        raise ValueError("--out-dir must exist and be a directory")
    return resolved


def _resolve_path(*, raw: str, repo_root: Path, label: str) -> Path:
    if not raw:
        raise ValueError(f"{label} is required")
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _rel_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.name
