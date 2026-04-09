"""Verify-report command: concise human-friendly post-verify diagnostics.

Reads existing verify artifacts and prints a deterministic, section-based
report to stdout.  Headless-safe — no engine or arcade imports.

Reuses helpers from ``debug_report`` where applicable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Parsing helpers (pure, no I/O)
# ---------------------------------------------------------------------------


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning *None* on missing/corrupt/non-dict."""
    if not path.exists() or not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _q(value: object) -> str:
    """Format a value for display: ``?`` if *None*, else ``str(value)``."""
    return "?" if value is None else str(value)


def _qbool(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "?"


# ---------------------------------------------------------------------------
# Section builders — each returns a list[str] of output lines.
# All are deterministic and tolerate *None* payloads gracefully.
# ---------------------------------------------------------------------------


def _section_header(artifacts_dir: Path) -> list[str]:
    return [
        f"Doctor Report (path={artifacts_dir.as_posix()})",
        "",
    ]


def _section_verify_summary(summary: dict[str, Any] | None) -> list[str]:
    lines = ["=== Verify Summary ==="]
    if summary is None:
        lines.append("  ok: ?  (verify_all_summary.json not found)")
        lines.append("  failing_steps: ?")
        lines.append("  artifacts_written: ?")
        return lines

    ok = summary.get("ok")
    lines.append(f"  ok: {_qbool(ok)}")

    steps = summary.get("steps")
    failing: list[str] = []
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and step.get("ok") is False:
                failing.append(str(step.get("name", "?")))
    if failing:
        lines.append(f"  failing_steps: {', '.join(failing)}")
    else:
        lines.append("  failing_steps: (none)")

    written = summary.get("artifacts", {})
    if isinstance(written, dict):
        written = written.get("written", {})
    if isinstance(written, dict):
        non_none = sorted(k for k, v in written.items() if v is not None)
        lines.append(f"  artifacts_written: {len(non_none)}")
        for key in non_none:
            lines.append(f"    - {key}")
    else:
        lines.append("  artifacts_written: ?")
    return lines


def _section_budgets(
    exception_budget: dict[str, Any] | None,
    step_budget_check: dict[str, Any] | None,
    trace_budget_check: dict[str, Any] | None,
) -> list[str]:
    lines = ["=== Budgets ==="]

    # Exception budget
    if exception_budget is not None:
        current = exception_budget.get("current_count")
        baseline = exception_budget.get("baseline_count")
        ok = exception_budget.get("ok")
        lines.append(f"  exception_budget: {_q(current)}/{_q(baseline)} ok={_qbool(ok)}")
    else:
        lines.append("  exception_budget: ?")

    # Step budget
    if step_budget_check is not None:
        ok = step_budget_check.get("ok")
        worst_name = "none"
        worst_delta: int | str = "?"
        offenders = step_budget_check.get("offenders")
        if isinstance(offenders, list) and offenders:
            top = offenders[0]
            if isinstance(top, dict):
                worst_name = str(top.get("name", "?"))
                delta_raw = top.get("delta_ms")
                worst_delta = int(delta_raw) if isinstance(delta_raw, (int, float)) else "?"
        lines.append(f"  verify_step_budget: ok={_qbool(ok)} worst={worst_name} delta_ms={_q(worst_delta)}")
    else:
        lines.append("  verify_step_budget: ?")

    # Authoring trace budget (optional)
    if trace_budget_check is not None:
        ok = trace_budget_check.get("ok")
        lines.append(f"  authoring_trace_budget: ok={_qbool(ok)}")
    # If absent, simply omit (optional artifact)

    return lines


def _section_timing(durations: dict[str, Any] | None) -> list[str]:
    lines = ["=== Timing ==="]
    if durations is None:
        lines.append("  verify_total_ms: ?")
        lines.append("  top 5 steps: ?")
        return lines

    total_ms = durations.get("total_ms")
    lines.append(f"  verify_total_ms: {_q(total_ms)}")

    steps = durations.get("steps")
    if isinstance(steps, list):
        parsed: list[tuple[int, str]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            name = step.get("name")
            ms = step.get("ms")
            if isinstance(name, str) and isinstance(ms, (int, float)):
                parsed.append((int(ms), str(name)))
        parsed.sort(key=lambda item: (-item[0], item[1]))
        top5 = parsed[:5]
        lines.append("  top 5 steps:")
        for ms, name in top5:
            lines.append(f"    {name}: {ms} ms")
    else:
        lines.append("  top 5 steps: ?")
    return lines


def _section_runtime_diagnostics(
    swallowed: dict[str, Any] | None,
    shadow: dict[str, Any] | None,
) -> list[str]:
    lines = ["=== Runtime Diagnostics ==="]

    # Swallowed exceptions
    if swallowed is not None:
        total = swallowed.get("total")
        distinct = swallowed.get("distinct")
        ok = swallowed.get("ok")
        lines.append(f"  swallowed_exceptions: total={_q(total)} distinct={_q(distinct)} ok={_qbool(ok)}")
        per_site = swallowed.get("per_site")
        if isinstance(per_site, list) and per_site:
            top5: list[tuple[int, str]] = []
            for row in per_site:
                if not isinstance(row, dict):
                    continue
                site = row.get("site")
                count = row.get("count")
                if isinstance(site, str) and isinstance(count, (int, float)):
                    top5.append((int(count), site))
            top5.sort(key=lambda item: (-item[0], item[1]))
            for count, site in top5[:5]:
                lines.append(f"    {site}: count={count}")
    else:
        lines.append("  swallowed_exceptions: ?")

    # Shadow backend
    if shadow is not None:
        selected = shadow.get("selected", "?")
        reason = shadow.get("reason", "?")
        fallbacks = shadow.get("fallbacks")
        fb_text = ", ".join(str(f) for f in fallbacks) if isinstance(fallbacks, list) and fallbacks else "(none)"
        lines.append(f"  shadow_backend: selected={selected} reason={reason} fallbacks=[{fb_text}]")
    else:
        lines.append("  shadow_backend: ?")

    return lines


def _section_authoring_trace(trace: dict[str, Any] | None) -> list[str]:
    """Authoring trace section — only emitted when the artifact exists."""
    if trace is None:
        return []
    lines = ["=== Authoring Trace ==="]
    enabled = trace.get("enabled")
    lines.append(f"  enabled: {_qbool(enabled)}")
    total_calls = trace.get("total_calls")
    lines.append(f"  total_calls: {_q(total_calls)}")

    functions = trace.get("functions")
    if isinstance(functions, list) and functions:
        parsed: list[tuple[int, str, int, float, str | None]] = []
        for entry in functions:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            calls = entry.get("calls")
            total_ms = entry.get("total_ms")
            if not isinstance(name, str):
                continue
            calls_int = int(calls) if isinstance(calls, (int, float)) else 0
            ms_int = int(total_ms) if isinstance(total_ms, (int, float)) else 0
            avg_ms = round(ms_int / calls_int, 2) if calls_int > 0 else 0.0
            last_err = entry.get("last_err")
            err_text = str(last_err) if last_err else None
            parsed.append((ms_int, name, calls_int, avg_ms, err_text))
        parsed.sort(key=lambda item: (-item[0], item[1]))
        top5 = parsed[:5]
        lines.append("  top 5 functions:")
        for ms, name, calls, avg, err in top5:
            line = f"    {name}: calls={calls} total_ms={ms} avg_ms={avg}"
            if err:
                line += f" last_err={err}"
            lines.append(line)
    return lines


def _section_footer(read_artifacts: list[str]) -> list[str]:
    lines = ["=== Artifacts Read ==="]
    if read_artifacts:
        for name in read_artifacts:
            lines.append(f"  - {name}")
    else:
        lines.append("  (none)")
    return lines


# ---------------------------------------------------------------------------
# Top-level report builder
# ---------------------------------------------------------------------------

# Artifact table: (dict key for tracking, filename, is_optional)
_ARTIFACT_TABLE: list[tuple[str, str, bool]] = [
    ("verify_all_summary", "verify_all_summary.json", False),
    ("exception_budget", "exception_budget.json", False),
    ("verify_step_durations", "verify_step_durations.json", False),
    ("verify_step_budget_check", "verify_step_budget_check.json", False),
    ("swallowed_exceptions", "swallowed_exceptions.json", False),
    ("shadow_backend", "shadow_backend.json", False),
    ("authoring_trace", "authoring_trace.json", True),
    ("authoring_trace_budget_check", "authoring_trace_budget_check.json", True),
]


def _load_artifacts(
    artifacts_dir: Path,
) -> tuple[dict[str, dict[str, Any] | None], list[str]]:
    """Read all artifacts from *artifacts_dir*.

    Returns ``(loaded, read_files)`` where *loaded* maps artifact key to
    parsed dict (or *None*) and *read_files* lists the filenames that
    were successfully loaded.
    """
    loaded: dict[str, dict[str, Any] | None] = {}
    read_ok: list[str] = []
    for key, filename, _optional in _ARTIFACT_TABLE:
        payload = _safe_read_json(artifacts_dir / filename)
        loaded[key] = payload
        if payload is not None:
            read_ok.append(filename)
    return loaded, read_ok


# --- payload section builders (return plain dicts) -----------------------


def _payload_verify_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    if summary is None:
        return {"ok": None, "failing_steps": [], "artifacts_written": []}

    ok = summary.get("ok")
    ok_val: bool | None = ok if isinstance(ok, bool) else None

    steps = summary.get("steps")
    failing: list[str] = []
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and step.get("ok") is False:
                failing.append(str(step.get("name", "?")))

    written = summary.get("artifacts", {})
    if isinstance(written, dict):
        written = written.get("written", {})
    written_keys: list[str] = []
    if isinstance(written, dict):
        written_keys = sorted(k for k, v in written.items() if v is not None)

    return {
        "ok": ok_val,
        "failing_steps": failing,
        "artifacts_written": written_keys,
    }


def _payload_budgets(
    exception_budget: dict[str, Any] | None,
    step_budget_check: dict[str, Any] | None,
    trace_budget_check: dict[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    # Exception budget
    if exception_budget is not None:
        result["exception_budget"] = {
            "ok": exception_budget.get("ok"),
            "current_count": exception_budget.get("current_count"),
            "baseline_count": exception_budget.get("baseline_count"),
        }
    else:
        result["exception_budget"] = None

    # Step budget
    if step_budget_check is not None:
        ok = step_budget_check.get("ok")
        offenders = step_budget_check.get("offenders")
        worst: dict[str, Any] | None = None
        if isinstance(offenders, list) and offenders:
            top = offenders[0]
            if isinstance(top, dict):
                worst = {
                    "name": str(top.get("name", "?")),
                    "delta_ms": int(top["delta_ms"]) if isinstance(top.get("delta_ms"), (int, float)) else None,
                }
        result["verify_step_budget"] = {"ok": ok, "worst_offender": worst}
    else:
        result["verify_step_budget"] = None

    # Authoring trace budget (optional — omit key when absent)
    if trace_budget_check is not None:
        result["authoring_trace_budget"] = {"ok": trace_budget_check.get("ok")}

    return result


def _payload_timing(durations: dict[str, Any] | None) -> dict[str, Any]:
    if durations is None:
        return {"total_ms": None, "top5": []}
    total_ms = durations.get("total_ms")
    steps = durations.get("steps")
    parsed: list[dict[str, Any]] = []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            name = step.get("name")
            ms = step.get("ms")
            if isinstance(name, str) and isinstance(ms, (int, float)):
                parsed.append({"name": name, "ms": int(ms)})
        parsed.sort(key=lambda item: (-item["ms"], item["name"]))
    return {"total_ms": total_ms, "top5": parsed[:5]}


def _payload_runtime_diagnostics(
    swallowed: dict[str, Any] | None,
    shadow: dict[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    # Swallowed exceptions
    if swallowed is not None:
        top5: list[dict[str, Any]] = []
        per_site = swallowed.get("per_site")
        if isinstance(per_site, list):
            for row in per_site:
                if not isinstance(row, dict):
                    continue
                site = row.get("site")
                count = row.get("count")
                if isinstance(site, str) and isinstance(count, (int, float)):
                    top5.append({"site": site, "count": int(count)})
            top5.sort(key=lambda item: (-item["count"], item["site"]))
            top5 = top5[:5]
        result["swallowed_exceptions"] = {
            "ok": swallowed.get("ok"),
            "total": swallowed.get("total"),
            "distinct": swallowed.get("distinct"),
            "top5_sites": top5,
        }
    else:
        result["swallowed_exceptions"] = None

    # Shadow backend
    if shadow is not None:
        fallbacks = shadow.get("fallbacks")
        result["shadow_backend"] = {
            "selected": shadow.get("selected", "?"),
            "reason": shadow.get("reason", "?"),
            "fallbacks": list(fallbacks) if isinstance(fallbacks, list) else [],
        }
    else:
        result["shadow_backend"] = None

    return result


def _payload_authoring_trace(trace: dict[str, Any] | None) -> dict[str, Any] | None:
    if trace is None:
        return None
    top5: list[dict[str, Any]] = []
    functions = trace.get("functions")
    if isinstance(functions, list):
        for entry in functions:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            calls = entry.get("calls")
            total_ms = entry.get("total_ms")
            if not isinstance(name, str):
                continue
            calls_int = int(calls) if isinstance(calls, (int, float)) else 0
            ms_int = int(total_ms) if isinstance(total_ms, (int, float)) else 0
            avg_ms = round(ms_int / calls_int, 2) if calls_int > 0 else 0.0
            last_err = entry.get("last_err")
            top5.append({
                "name": name,
                "calls": calls_int,
                "total_ms": ms_int,
                "avg_ms": avg_ms,
                "last_err": str(last_err) if last_err else None,
            })
        top5.sort(key=lambda item: (-item["total_ms"], item["name"]))
        top5 = top5[:5]
    return {
        "enabled": trace.get("enabled"),
        "total_calls": trace.get("total_calls"),
        "top5_functions": top5,
    }


# --- public payload builder -----------------------------------------------


def build_report_payload(artifacts_dir: Path) -> dict[str, Any]:
    """Build a deterministic JSON-serialisable report payload (schema v1).

    Returns a dict suitable for ``json.dumps(sort_keys=True)``.
    """
    loaded, read_files = _load_artifacts(artifacts_dir)

    return {
        "schema_version": 1,
        "artifacts_dir": artifacts_dir.as_posix(),
        "verify_summary": _payload_verify_summary(loaded["verify_all_summary"]),
        "budgets": _payload_budgets(
            loaded["exception_budget"],
            loaded["verify_step_budget_check"],
            loaded["authoring_trace_budget_check"],
        ),
        "timing": _payload_timing(loaded["verify_step_durations"]),
        "runtime_diagnostics": _payload_runtime_diagnostics(
            loaded["swallowed_exceptions"],
            loaded["shadow_backend"],
        ),
        "authoring_trace": _payload_authoring_trace(loaded["authoring_trace"]),
        "read_files": read_files,
    }


def build_report_lines(artifacts_dir: Path) -> list[str]:
    """Build the full doctor report as a list of lines (deterministic)."""
    loaded, read_ok = _load_artifacts(artifacts_dir)

    lines: list[str] = []
    lines.extend(_section_header(artifacts_dir))
    lines.extend(_section_verify_summary(loaded["verify_all_summary"]))
    lines.append("")
    lines.extend(
        _section_budgets(
            loaded["exception_budget"],
            loaded["verify_step_budget_check"],
            loaded["authoring_trace_budget_check"],
        )
    )
    lines.append("")
    lines.extend(_section_timing(loaded["verify_step_durations"]))
    lines.append("")
    lines.extend(
        _section_runtime_diagnostics(
            loaded["swallowed_exceptions"],
            loaded["shadow_backend"],
        )
    )
    trace_lines = _section_authoring_trace(loaded["authoring_trace"])
    if trace_lines:
        lines.append("")
        lines.extend(trace_lines)
    lines.append("")
    lines.extend(_section_footer(read_ok))
    return lines


def build_report_text(artifacts_dir: Path) -> str:
    """Build the full doctor report as a single string (deterministic).

    This is the primary reuse entry-point for callers that want the
    formatted report without going through the CLI.
    """
    return "\n".join(build_report_lines(artifacts_dir))


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def _handle_verify_report(args: argparse.Namespace) -> int:
    raw = str(getattr(args, "artifacts", "") or "").strip() or "artifacts"
    artifacts_dir = Path(raw)
    if not artifacts_dir.is_absolute():
        repo_root = Path(__file__).resolve().parent.parent
        artifacts_dir = (repo_root / artifacts_dir).resolve()

    if not artifacts_dir.exists() or not artifacts_dir.is_dir():
        print(f"error: artifacts directory not found: {artifacts_dir.as_posix()}", file=sys.stderr)
        return 2

    lines = build_report_lines(artifacts_dir)
    print("\n".join(lines))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "verify-report",
        help="Print a concise diagnostics report from verify artifacts",
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Artifact directory containing verify outputs (default: artifacts)",
    )
    parser.set_defaults(func=_handle_verify_report)


def handle(args: argparse.Namespace) -> int:
    return _handle_verify_report(args)
