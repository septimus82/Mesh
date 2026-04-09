from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.persistence_io import dumps_json_deterministic, read_json, write_json_atomic


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_artifacts_dir(repo_root: Path, raw: str) -> Path:
    path = Path(str(raw or "artifacts"))
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)
    return None


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _as_text_bool(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "?"


def _as_text_int(value: int | None) -> str:
    return str(value) if value is not None else "?"


def _normalize_summary_lines(value: object) -> list[str]:
    if isinstance(value, str):
        lines = [line.rstrip() for line in value.splitlines() if line.strip()]
        return lines
    if isinstance(value, list):
        lines = [str(line).rstrip() for line in value if str(line).strip()]
        return lines
    return []


def _read_verify_snapshot(artifacts_dir: Path) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "exception_current": None,
        "exception_baseline": None,
        "exception_ok": None,
        "verify_total_ms": None,
        "step_budget_ok": None,
        "worst_step": None,
        "worst_delta_ms": None,
    }

    exception_payload = _safe_read_json(artifacts_dir / "exception_budget.json")
    if exception_payload is not None:
        snapshot["exception_current"] = _as_int(exception_payload.get("current_count"))
        snapshot["exception_baseline"] = _as_int(exception_payload.get("baseline_count"))
        snapshot["exception_ok"] = _as_bool(exception_payload.get("ok"))

    durations_payload = _safe_read_json(artifacts_dir / "verify_step_durations.json")
    if durations_payload is not None:
        snapshot["verify_total_ms"] = _as_int(durations_payload.get("total_ms"))

    budget_payload = _safe_read_json(artifacts_dir / "verify_step_budget_check.json")
    if budget_payload is not None:
        budget_ok = _as_bool(budget_payload.get("ok"))
        snapshot["step_budget_ok"] = budget_ok
        if budget_ok is True:
            snapshot["worst_step"] = "none"
            snapshot["worst_delta_ms"] = None
        elif budget_ok is False:
            offenders = budget_payload.get("offenders")
            parsed: list[tuple[int, str]] = []
            if isinstance(offenders, list):
                for row in offenders:
                    if not isinstance(row, dict):
                        continue
                    name = row.get("name")
                    delta_ms = _as_int(row.get("delta_ms"))
                    if isinstance(name, str) and delta_ms is not None:
                        parsed.append((delta_ms, name))
            if parsed:
                parsed.sort(key=lambda item: (-item[0], item[1]))
                best_delta, best_name = parsed[0]
                snapshot["worst_step"] = best_name
                snapshot["worst_delta_ms"] = best_delta
    return snapshot


def _read_shadow_backend(artifacts_dir: Path) -> dict[str, object] | None:
    payload = _safe_read_json(artifacts_dir / "shadow_backend.json")
    if payload is None:
        return None
    fallbacks_value = payload.get("fallbacks")
    fallbacks: list[str]
    if isinstance(fallbacks_value, list):
        fallbacks = [str(item) for item in fallbacks_value]
    else:
        fallbacks = []
    return {
        "selected": str(payload.get("selected", "?")),
        "reason": str(payload.get("reason", "?")),
        "fallbacks": fallbacks,
    }


def _build_swallowed_summary_lines(payload: dict[str, Any]) -> list[str]:
    summary_lines = _normalize_summary_lines(payload.get("summary_lines"))
    if summary_lines:
        return summary_lines

    summary_lines = _normalize_summary_lines(payload.get("summary"))
    if summary_lines:
        return summary_lines

    per_site = payload.get("per_site")
    if isinstance(per_site, dict):
        rows: list[tuple[int, str]] = []
        for site, count in per_site.items():
            site_name = str(site)
            parsed = _as_int(count)
            if parsed is None:
                continue
            rows.append((parsed, site_name))
        rows.sort(key=lambda item: (-item[0], item[1]))
        return [f"{site}: count={count}" for count, site in rows]

    if isinstance(per_site, list):
        rows_list: list[tuple[int, str]] = []
        for row in per_site:
            if not isinstance(row, dict):
                continue
            site = row.get("site")
            count = _as_int(row.get("count"))
            if not isinstance(site, str) or count is None:
                continue
            rows_list.append((count, site))
        rows_list.sort(key=lambda item: (-item[0], item[1]))
        return [f"{site}: count={count}" for count, site in rows_list]

    sites = payload.get("sites")
    if isinstance(sites, list):
        rows2: list[tuple[int, str]] = []
        for row in sites:
            if not isinstance(row, dict):
                continue
            site = row.get("site")
            count = _as_int(row.get("count"))
            if not isinstance(site, str) or count is None:
                continue
            rows2.append((count, site))
        rows2.sort(key=lambda item: (-item[0], item[1]))
        return [f"{site}: count={count}" for count, site in rows2]
    return []


def _read_swallowed_exceptions(artifacts_dir: Path) -> dict[str, object] | None:
    payload = _safe_read_json(artifacts_dir / "swallowed_exceptions.json")
    if payload is None:
        return None

    total = _as_int(payload.get("total"))
    if total is None:
        total = _as_int(payload.get("total_count"))
    if total is None:
        total = _as_int(payload.get("total_swallowed_count"))

    distinct = _as_int(payload.get("distinct"))
    if distinct is None:
        distinct = _as_int(payload.get("distinct_count"))
    if distinct is None:
        distinct = _as_int(payload.get("distinct_sites"))

    summary_lines = _build_swallowed_summary_lines(payload)
    return {
        "total": total,
        "distinct": distinct,
        "summary_lines": summary_lines,
    }


def build_debug_report_payload(*, artifacts_dir: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "verify_snapshot": _read_verify_snapshot(artifacts_dir),
        "shadow_backend": _read_shadow_backend(artifacts_dir),
        "swallowed_exceptions": _read_swallowed_exceptions(artifacts_dir),
    }


def _format_debug_report_lines(payload: dict[str, object]) -> list[str]:
    verify = payload.get("verify_snapshot")
    if not isinstance(verify, dict):
        verify = {}
    shadow = payload.get("shadow_backend")
    shadow_dict = shadow if isinstance(shadow, dict) else None
    swallowed = payload.get("swallowed_exceptions")
    swallowed_dict = swallowed if isinstance(swallowed, dict) else None

    lines: list[str] = [
        "Verify Health Snapshot",
        (
            "exception_budget: "
            f"{_as_text_int(_as_int(verify.get('exception_current')))}"
            f"/{_as_text_int(_as_int(verify.get('exception_baseline')))}"
            f" ok={_as_text_bool(_as_bool(verify.get('exception_ok')))}"
        ),
        f"verify_total_ms: {_as_text_int(_as_int(verify.get('verify_total_ms')))}",
        f"step_budget_ok: {_as_text_bool(_as_bool(verify.get('step_budget_ok')))}",
    ]

    worst_step = verify.get("worst_step")
    worst_step_text = str(worst_step) if isinstance(worst_step, str) else "?"
    worst_delta_ms = _as_int(verify.get("worst_delta_ms"))
    lines.append(f"worst_step: {worst_step_text} delta_ms={_as_text_int(worst_delta_ms)}")
    lines.append("")

    lines.append("Shadow Backend")
    if shadow_dict is None:
        lines.append("selected: ?")
        lines.append("reason: ?")
        lines.append("fallbacks: ?")
    else:
        selected = str(shadow_dict.get("selected", "?"))
        reason = str(shadow_dict.get("reason", "?"))
        fallback_values = shadow_dict.get("fallbacks")
        if isinstance(fallback_values, list) and fallback_values:
            fallbacks_text = ", ".join(str(item) for item in fallback_values)
        else:
            fallbacks_text = "?"
        lines.append(f"selected: {selected}")
        lines.append(f"reason: {reason}")
        lines.append(f"fallbacks: {fallbacks_text}")
    lines.append("")

    lines.append("Swallowed Exceptions")
    if swallowed_dict is None:
        lines.append("total=? distinct=?")
        lines.append("(unavailable)")
    else:
        lines.append(
            "total="
            f"{_as_text_int(_as_int(swallowed_dict.get('total')))} "
            f"distinct={_as_text_int(_as_int(swallowed_dict.get('distinct')))}"
        )
        summary_lines = swallowed_dict.get("summary_lines")
        if isinstance(summary_lines, list) and summary_lines:
            lines.extend(str(line) for line in summary_lines)
        else:
            lines.append("(unavailable)")
    return lines


def _handle_debug_report(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_module()
    artifacts_dir = _resolve_artifacts_dir(repo_root, str(getattr(args, "artifacts", "artifacts") or "artifacts"))
    payload = build_debug_report_payload(artifacts_dir=artifacts_dir)
    print("\n".join(_format_debug_report_lines(payload)))

    raw_json_out = str(getattr(args, "json_out", "") or "").strip()
    if raw_json_out:
        json_out = Path(raw_json_out)
        if not json_out.is_absolute():
            json_out = (repo_root / json_out).resolve()
        json_out.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(json_out, payload, indent=2, sort_keys=True, trailing_newline=True)
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "debug-report",
        help="Print deterministic debug diagnostics from verify artifacts",
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Artifact directory containing verify outputs (default: artifacts)",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional JSON output path",
    )
    parser.set_defaults(func=_handle_debug_report)


def handle(args: argparse.Namespace) -> int:
    return _handle_debug_report(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh debug-report")
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args(argv)
    return _handle_debug_report(args)
