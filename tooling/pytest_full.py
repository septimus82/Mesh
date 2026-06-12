from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from tooling.pytest_runner_common import (
    build_pytest_args,
    build_pytest_env,
    format_xdist,
    write_runner_log,
)


def _xdist_available() -> bool:
    return importlib.util.find_spec("xdist") is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xdist", action="store_true", help="Use pytest-xdist if available")
    parser.add_argument(
        "--timeout-s",
        type=int,
        default=900,
        help="Timeout in seconds for the full suite (default: 900).",
    )
    parser.add_argument(
        "--repo-root",
        help="Override repo root (default: project root).",
    )
    args = parser.parse_args(argv)

    env_repo_root = os.getenv("MESH_PYTEST_FULL_REPO_ROOT")
    repo_root = Path(
        args.repo_root or env_repo_root or Path(__file__).resolve().parents[1]
    ).resolve()

    # Clean output for log, capture fd to handle C-level output if any
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *build_pytest_args(
            [
                "-q",
                "-vv",
                "--color=no",
                "--capture=fd",
                "--durations=25",
                "--durations-min=1.0",
                "--maxfail=1",
                "-W",
                "error",
                "--strict-markers",
            ]
        ),
    ]

    xdist_enabled = False
    if args.xdist:
        if _xdist_available():
            cmd += ["-n", "auto"]
            xdist_enabled = True
        else:
            print("pytest-full: xdist not available, running serial")

    artifacts_dir = repo_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    log_path = artifacts_dir / "pytest_full.log"
    env = build_pytest_env(os.environ)
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    write_runner_log(
        log_path,
        {
            "repo_root": str(repo_root),
            "python": py_version,
            "PYTEST_ADDOPTS": "cleared",
            "xdist": format_xdist(xdist_enabled, None),
        },
        cmd,
    )

    timeout_s = int(args.timeout_s)
    print(f"pytest-full: log: {log_path}")
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        output = getattr(result, "stdout", "") or ""
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        print(f"pytest-full: TIMEOUT after {timeout_s}s")
        result = subprocess.CompletedProcess(cmd, returncode=1)

    with open(log_path, "a", encoding="utf-8", newline="\n") as handle:
        if output:
            handle.write(output)

    if result.returncode != 0:
        print(f"pytest-full: Tests FAILED with exit code {result.returncode}")
        print(f"Tail of {log_path}:")
        try:
            with open(log_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
            for line in lines[-20:]:
                print(line, end="")
        except Exception as exc:
            print(f"Error reading log: {exc}")
    else:
        print("pytest-full: Tests PASSED")

    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
