"""CLI command: ``mesh_cli baseline-update``

One-shot refresh of the committed CI baseline artifacts.

Runs verify-all → artifacts-validate → artifacts-diff --update-baseline
(or skips verify-all when ``--artifacts`` points at an existing dir).

Headless-safe — no engine or arcade imports at module level.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BASELINE_DIR = "tooling/metrics/ci_baseline_artifacts"

_REPO_ROOT = Path(__file__).resolve().parent.parent


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
    except Exception as exc:
        msg = f"[{label}] failed to launch: {exc}"
        return False, msg

    output = result.stdout
    if result.stderr:
        output += result.stderr

    ok = result.returncode == 0
    return ok, output


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

        # Summary
        lines.append("")
        lines.append("Baseline updated:")
        lines.append(f"  index.json -> {(baseline_dir / 'index.json').as_posix()}")
        lines.append(f"  verify_report.json -> {(baseline_dir / 'verify_report.json').as_posix()}")
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
