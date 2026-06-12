"""CLI command: ``mesh_cli baseline-update``

One-shot refresh of the committed CI baseline artifacts.

Runs verify-all → artifacts-validate → artifacts-diff --update-baseline
(or skips verify-all when ``--artifacts`` points at an existing dir).

Headless-safe — no engine or arcade imports at module level.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BASELINE_DIR = "tooling/metrics/ci_baseline_artifacts"
_BASELINE_META_FILENAME = "BASELINE_META.json"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VERSION_LINE_RE = re.compile(r'^(PUBLIC_API_SEMVER\s*=\s*")([^"]+)(".*)$', re.MULTILINE)


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def _run_cmd(argv: list[str], *, label: str) -> tuple[bool, str]:
    """Run *argv* as a subprocess, streaming stdout/stderr.

    Returns ``(ok, combined_output)``.
    """
    try:
        result = subprocess.run(
            argv,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        msg = f"[{label}] failed to launch: {exc}"
        return False, msg

    output = result.stdout
    if result.stderr:
        output += result.stderr

    ok = result.returncode == 0
    return ok, output


def _utc_now_iso() -> str:
    try:
        now = datetime.now(UTC).replace(microsecond=0)
        return now.isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return "1970-01-01T00:00:00Z"


def _get_source_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    text = str(result.stdout or "").strip()
    return text if text else "unknown"


def _read_package_version(repo_root: Path) -> str:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists() or not pyproject.is_file():
        return "unknown"
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return "unknown"
    if not isinstance(payload, dict):
        return "unknown"
    project = payload.get("project")
    if not isinstance(project, dict):
        return "unknown"
    version = project.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return "unknown"


def _read_public_api_semver(repo_root: Path) -> str:
    version_py = repo_root / "engine" / "public_api" / "version.py"
    if not version_py.exists() or not version_py.is_file():
        return "unknown"
    try:
        text = version_py.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = _VERSION_LINE_RE.search(text)
    if match is None:
        return "unknown"
    value = str(match.group(2)).strip()
    return value if value else "unknown"


def _build_baseline_meta(repo_root: Path) -> dict[str, Any]:
    run_id = str(os.getenv("GITHUB_RUN_ID", "") or "").strip() or None
    payload: dict[str, Any] = {
        "schema_version": 1,
        "created_utc": _utc_now_iso(),
        "source_commit": _get_source_commit(repo_root),
        "source_workflow_run_id": run_id,
        "package_version": _read_package_version(repo_root),
        "public_api_semver": _read_public_api_semver(repo_root),
    }
    return payload


def _write_baseline_meta(baseline_dir: Path, repo_root: Path) -> Path:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_baseline_meta(repo_root)
    target = baseline_dir / _BASELINE_META_FILENAME
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def baseline_update(
    *,
    baseline_dir: Path,
    artifacts_dir: Path | None = None,
    keep_temp: bool = False,
    no_verify_all: bool = False,
    run_cmd: Any = None,
) -> tuple[int, list[str]]:
    """Refresh the baseline.

    Parameters
    ----------
    baseline_dir:
        Target dir to write baseline files into.
    artifacts_dir:
        If given, use this existing artifacts dir (skip verify-all).
    keep_temp:
        If True and a temp dir was created, do not delete it.
    no_verify_all:
        If True and *artifacts_dir* is not given, fail immediately.
    run_cmd:
        Optional callable ``(argv, *, label) -> (ok, output)`` for testing.

    Returns ``(exit_code, output_lines)``.
    """
    if run_cmd is None:
        run_cmd = _run_cmd

    lines: list[str] = []
    temp_dir: Path | None = None
    created_temp = False

    try:
        # Determine artifacts source
        if artifacts_dir is not None:
            work_dir = artifacts_dir
            if not work_dir.exists() or not work_dir.is_dir():
                lines.append(f"error: artifacts directory not found: {work_dir.as_posix()}")
                return 2, lines
        elif no_verify_all:
            lines.append("error: --no-verify-all requires --artifacts <dir>")
            return 2, lines
        else:
            # Create temp dir
            temp_dir = Path(tempfile.mkdtemp(
                prefix="_baseline_tmp_",
                dir=str(_REPO_ROOT / "artifacts"),
            ))
            created_temp = True
            work_dir = temp_dir
            lines.append(f"temp artifacts dir: {work_dir.as_posix()}")

            # Step 1: verify-all
            lines.append("")
            lines.append("--- Step 1: verify-all --ci-bundle ---")
            python = sys.executable
            ok, output = run_cmd(
                [python, "-m", "mesh_cli", "verify-all",
                 "--artifacts", str(work_dir), "--ci-bundle"],
                label="verify-all",
            )
            if output.strip():
                lines.append(output.rstrip())
            if not ok:
                lines.append("error: verify-all failed")
                return 2, lines

        # Step 2: artifacts-validate
        lines.append("")
        lines.append("--- Step 2: artifacts-validate ---")
        python = sys.executable
        ok, output = run_cmd(
            [python, "-m", "mesh_cli", "artifacts-validate",
             "--artifacts", str(work_dir)],
            label="artifacts-validate",
        )
        if output.strip():
            lines.append(output.rstrip())
        if not ok:
            lines.append("error: artifacts-validate failed")
            return 2, lines

        # Step 3: update-baseline
        lines.append("")
        lines.append("--- Step 3: update-baseline ---")
        from mesh_cli.artifacts_diff import update_baseline

        code, msgs = update_baseline(baseline_dir, work_dir)
        for m in msgs:
            lines.append(m)
        if code != 0:
            lines.append("error: update-baseline failed")
            return 2, lines

        meta_path = _write_baseline_meta(baseline_dir, _REPO_ROOT)
        lines.append(f"updated: {meta_path.as_posix()}")

        # Summary
        lines.append("")
        lines.append("Baseline updated:")
        lines.append(f"  index.json -> {(baseline_dir / 'index.json').as_posix()}")
        lines.append(f"  verify_report.json -> {(baseline_dir / 'verify_report.json').as_posix()}")
        lines.append(f"  BASELINE_META.json -> {(baseline_dir / _BASELINE_META_FILENAME).as_posix()}")
        lines.append("")
        lines.append("Note: timing.total_ms is preserved as-is from the run.")
        lines.append("Set total_ms to 0 in verify_report.json to use the timing sentinel")
        lines.append("(skips timing diff in CI).")
        lines.append("")
        baseline_rel = baseline_dir.as_posix()
        lines.append(f"Next: git add {baseline_rel} && git commit -m 'Update CI baseline'")

        if created_temp and keep_temp:
            lines.append(f"temp dir kept: {work_dir.as_posix()}")

        return 0, lines

    finally:
        if created_temp and temp_dir is not None and not keep_temp:
            shutil.rmtree(str(temp_dir), ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def _handle_baseline_update(args: argparse.Namespace) -> int:
    baseline_raw = getattr(args, "baseline_dir", None) or _DEFAULT_BASELINE_DIR
    baseline_dir = Path(baseline_raw)
    if not baseline_dir.is_absolute():
        baseline_dir = _REPO_ROOT / baseline_dir

    artifacts_raw = getattr(args, "artifacts", None)
    artifacts_dir: Path | None = None
    if artifacts_raw:
        artifacts_dir = Path(artifacts_raw)
        if not artifacts_dir.is_absolute():
            artifacts_dir = _REPO_ROOT / artifacts_dir

    keep_temp = getattr(args, "keep_temp", False)
    no_verify_all = getattr(args, "no_verify_all", False)

    code, lines = baseline_update(
        baseline_dir=baseline_dir,
        artifacts_dir=artifacts_dir,
        keep_temp=keep_temp,
        no_verify_all=no_verify_all,
    )
    for line in lines:
        print(line)
    return code


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "baseline-update",
        help="Refresh the committed CI baseline artifacts in one shot",
    )
    parser.add_argument(
        "--baseline-dir",
        default=None,
        help=f"Target baseline directory (default: {_DEFAULT_BASELINE_DIR})",
    )
    parser.add_argument(
        "--artifacts",
        default=None,
        help="Use an existing artifacts dir instead of running verify-all",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        default=False,
        help="Keep the temp artifacts dir after update (for debugging)",
    )
    parser.add_argument(
        "--no-verify-all",
        action="store_true",
        default=False,
        help="Do not run verify-all; requires --artifacts",
    )
    parser.set_defaults(func=_handle_baseline_update)


def handle(args: argparse.Namespace) -> int:
    return _handle_baseline_update(args)
