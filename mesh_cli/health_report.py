from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.persistence_io import dumps_json_deterministic, read_json, write_json_atomic

_SCANNED_DIRS: tuple[str, ...] = ("engine", "mesh_cli", "tooling")
_HOTSPOT_LIMIT = 10


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_artifacts_dir(repo_root: Path, raw: str) -> Path:
    path = Path(str(raw or "artifacts"))
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _read_int_file(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return None


def _count_mypy_baseline_errors(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return sum(1 for line in lines if ": error:" in line)


def _collect_hotspots(repo_root: Path, *, limit: int = _HOTSPOT_LIMIT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel_dir in _SCANNED_DIRS:
        base = (repo_root / rel_dir).resolve()
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            nonempty_lines = sum(1 for line in text.splitlines() if line.strip())
            rel_path = path.relative_to(repo_root).as_posix()
            rows.append({"path": rel_path, "nonempty_lines": int(nonempty_lines)})
    rows.sort(key=lambda row: (-int(row["nonempty_lines"]), str(row["path"])))
    return rows[: int(limit)]


def _read_exception_budget_signal(artifacts_dir: Path, repo_root: Path) -> dict[str, Any]:
    baseline_path = repo_root / "tooling" / "metrics" / "exception_budget_count.txt"
    baseline = _read_int_file(baseline_path)

    artifact_payload = _safe_read_json(artifacts_dir / "exception_budget.json")
    current: int | None = None
    ok: bool | None = None
    if artifact_payload is not None:
        raw_current = artifact_payload.get("current_count")
        if isinstance(raw_current, int):
            current = raw_current
        raw_ok = artifact_payload.get("ok")
        if isinstance(raw_ok, bool):
            ok = raw_ok
    return {"baseline": baseline, "current": current, "ok": ok}


def _read_verify_step_durations_signal(artifacts_dir: Path) -> dict[str, Any]:
    artifact_payload = _safe_read_json(artifacts_dir / "verify_step_durations.json")
    if artifact_payload is None:
        return {"total_ms": None, "steps": None}

    total_ms: int | None = None
    raw_total = artifact_payload.get("total_ms")
    if isinstance(raw_total, int):
        total_ms = raw_total

    raw_steps = artifact_payload.get("steps")
    if not isinstance(raw_steps, list):
        return {"total_ms": total_ms, "steps": None}

    steps: list[dict[str, Any]] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        ms = item.get("ms")
        ok = item.get("ok")
        if not isinstance(name, str):
            continue
        if not isinstance(ms, int):
            continue
        if not isinstance(ok, bool):
            continue
        steps.append({"name": name, "ms": ms, "ok": ok})
    return {"total_ms": total_ms, "steps": steps}


def build_health_report_payload(*, repo_root: Path, artifacts_dir: Path) -> dict[str, Any]:
    repo_root_posix = repo_root.resolve().as_posix()
    return {
        "schema_version": 1,
        "repo_root": repo_root_posix,
        "signals": {
            "exception_budget": _read_exception_budget_signal(artifacts_dir, repo_root),
            "verify_step_durations": _read_verify_step_durations_signal(artifacts_dir),
            "mypy_baseline": {
                "error_count": _count_mypy_baseline_errors(repo_root / "tooling" / "mypy_baseline.txt"),
            },
            "hotspots": _collect_hotspots(repo_root),
        },
    }


def _handle_health_report(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_module()
    artifacts_dir = _resolve_artifacts_dir(repo_root, str(getattr(args, "artifacts", "artifacts") or "artifacts"))
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    payload = build_health_report_payload(repo_root=repo_root, artifacts_dir=artifacts_dir)
    out_path = artifacts_dir / "health_report.json"
    write_json_atomic(out_path, payload, indent=2, sort_keys=True, trailing_newline=True)
    print(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True), end="")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "health-report",
        help="Aggregate deterministic repo health signals",
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Artifact output directory (default: artifacts)",
    )
    parser.set_defaults(func=_handle_health_report)


def handle(args: argparse.Namespace) -> int:
    return _handle_health_report(args)
