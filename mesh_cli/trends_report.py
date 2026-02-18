from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_DEFAULT_TREND_FILE = "tooling/metrics/weekly_trends.json"


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
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _as_int_or_unknown(value: object) -> int | str:
    if isinstance(value, bool):
        return "?"
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)
    return "?"


def _value_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "?"


def _state_delta(previous: object, current: object) -> str:
    prev_text = _value_text(previous)
    cur_text = _value_text(current)
    if prev_text == "?" or cur_text == "?":
        return "?"
    if prev_text == cur_text:
        return "unchanged"
    return f"{prev_text} -> {cur_text}"


def _int_delta(previous: object, current: object) -> int | str:
    p = _as_int_or_unknown(previous)
    c = _as_int_or_unknown(current)
    if isinstance(p, int) and isinstance(c, int):
        return c - p
    return "?"


def _read_entries(path: Path) -> list[dict[str, Any]]:
    payload = _safe_read_json(path)
    if not isinstance(payload, dict):
        return []
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in entries:
        if isinstance(row, dict):
            rows.append(dict(row))
    return rows


def build_trends_report_payload(trend_file: Path, *, last: int = 8) -> dict[str, Any]:
    entries = _read_entries(trend_file)
    last_n = max(1, int(last))
    latest = entries[-1] if entries else {}
    previous = entries[-2] if len(entries) >= 2 else {}

    latest_block = {
        "timestamp_utc": _value_text(latest.get("timestamp_utc")),
        "package_version": _value_text(latest.get("package_version")),
        "public_api_semver": _value_text(latest.get("public_api_semver")),
        "verify_ok": _value_text(latest.get("verify_ok")),
        "verify_total_ms": _as_int_or_unknown(latest.get("verify_total_ms")),
        "mypy_budget_ok": _value_text(latest.get("mypy_budget_ok")),
        "exception_budget_ok": _value_text(latest.get("exception_budget_ok")),
        "swallowed_total": _as_int_or_unknown(latest.get("swallowed_total")),
        "shadow_backend_selected": _value_text(latest.get("shadow_backend_selected")),
    }

    deltas = {
        "verify_total_ms": _int_delta(previous.get("verify_total_ms"), latest.get("verify_total_ms")),
        "swallowed_total": _int_delta(previous.get("swallowed_total"), latest.get("swallowed_total")),
        "verify_ok": _state_delta(previous.get("verify_ok"), latest.get("verify_ok")),
        "mypy_budget_ok": _state_delta(previous.get("mypy_budget_ok"), latest.get("mypy_budget_ok")),
        "exception_budget_ok": _state_delta(previous.get("exception_budget_ok"), latest.get("exception_budget_ok")),
        "shadow_backend_selected": _state_delta(
            previous.get("shadow_backend_selected"),
            latest.get("shadow_backend_selected"),
        ),
    }

    history_rows = []
    for row in entries[-last_n:]:
        history_rows.append(
            {
                "timestamp_utc": _value_text(row.get("timestamp_utc")),
                "verify_total_ms": _as_int_or_unknown(row.get("verify_total_ms")),
                "swallowed_total": _as_int_or_unknown(row.get("swallowed_total")),
            }
        )

    return {
        "schema_version": 1,
        "trend_file": trend_file.as_posix(),
        "entries_count": len(entries),
        "latest": latest_block,
        "deltas": deltas,
        "history": {
            "last_n": last_n,
            "rows": history_rows,
        },
    }


def format_markdown(payload: dict[str, Any]) -> str:
    latest = payload.get("latest", {}) if isinstance(payload.get("latest"), dict) else {}
    deltas = payload.get("deltas", {}) if isinstance(payload.get("deltas"), dict) else {}
    history = payload.get("history", {}) if isinstance(payload.get("history"), dict) else {}
    rows = history.get("rows", []) if isinstance(history.get("rows"), list) else []
    last_n = history.get("last_n")

    lines = [
        "## Trends delta panel",
        "",
        f"- trend_file: {_value_text(payload.get('trend_file'))}",
        f"- entries: {_value_text(payload.get('entries_count'))}",
        f"- latest_timestamp_utc: {_value_text(latest.get('timestamp_utc'))}",
        "",
        "### Latest",
        f"- package_version: {_value_text(latest.get('package_version'))}",
        f"- public_api_semver: {_value_text(latest.get('public_api_semver'))}",
        f"- verify_ok: {_value_text(latest.get('verify_ok'))}",
        f"- verify_total_ms: {_value_text(latest.get('verify_total_ms'))}",
        f"- mypy_budget_ok: {_value_text(latest.get('mypy_budget_ok'))}",
        f"- exception_budget_ok: {_value_text(latest.get('exception_budget_ok'))}",
        f"- swallowed_total: {_value_text(latest.get('swallowed_total'))}",
        f"- shadow_backend_selected: {_value_text(latest.get('shadow_backend_selected'))}",
        "",
        "### Delta vs previous",
        f"- verify_total_ms: {_value_text(deltas.get('verify_total_ms'))}",
        f"- swallowed_total: {_value_text(deltas.get('swallowed_total'))}",
        f"- verify_ok: {_value_text(deltas.get('verify_ok'))}",
        f"- mypy_budget_ok: {_value_text(deltas.get('mypy_budget_ok'))}",
        f"- exception_budget_ok: {_value_text(deltas.get('exception_budget_ok'))}",
        f"- shadow_backend_selected: {_value_text(deltas.get('shadow_backend_selected'))}",
        "",
        f"### Last {_value_text(last_n)}",
        "| timestamp_utc | verify_total_ms | swallowed_total |",
        "| --- | ---: | ---: |",
    ]
    if rows:
        for row in rows:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| {_value_text(row.get('timestamp_utc'))} | "
                f"{_value_text(row.get('verify_total_ms'))} | "
                f"{_value_text(row.get('swallowed_total'))} |"
            )
    else:
        lines.append("| ? | ? | ? |")
    return "\n".join(lines).rstrip() + "\n"


def _handle_trends_report(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_module()
    trend_raw = str(getattr(args, "trend_file", _DEFAULT_TREND_FILE) or _DEFAULT_TREND_FILE).strip()
    trend_file = _resolve_path(repo_root, trend_raw)
    if not trend_file.exists() or not trend_file.is_file():
        print(f"error: trend file not found: {trend_file.as_posix()}", file=sys.stderr)
        return 2

    last_n = int(getattr(args, "last", 8) or 8)
    fmt = str(getattr(args, "format", "markdown") or "markdown").strip().lower()
    out_raw = str(getattr(args, "out", "") or "").strip()
    out_path = _resolve_path(repo_root, out_raw) if out_raw else None

    payload = build_trends_report_payload(trend_file, last=last_n)
    text = json.dumps(payload, indent=2, sort_keys=True) if fmt == "json" else format_markdown(payload)

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
    sys.stdout.write(text + ("" if text.endswith("\n") else "\n"))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "trends-report",
        help="Render weekly trends latest/delta panel",
    )
    parser.add_argument("--trend-file", default=_DEFAULT_TREND_FILE, help=f"Trend input file (default: {_DEFAULT_TREND_FILE})")
    parser.add_argument("--last", type=int, default=8, help="History length for the table")
    parser.add_argument("--out", default="", help="Optional output file path")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.set_defaults(func=_handle_trends_report)


def handle(args: argparse.Namespace) -> int:
    return _handle_trends_report(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh trends-report")
    parser.add_argument("--trend-file", default=_DEFAULT_TREND_FILE)
    parser.add_argument("--last", type=int, default=8)
    parser.add_argument("--out", default="")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args(argv)
    return _handle_trends_report(args)
