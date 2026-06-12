from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

from engine import json_io
from tooling.pytest_runner_common import (
    build_pytest_args,
    build_pytest_env,
    format_xdist,
    write_runner_log,
)

DEFAULT_DURATIONS_PATH = Path(".mesh/metrics/pytest_durations_fast.json")
_DURATION_RE = re.compile(r"^\s*([0-9.]+)s\s+\w+\s+(.+)$")


def parse_durations_output(output: str) -> list[dict[str, float | str]]:
    results: list[dict[str, float | str]] = []
    in_section = False
    for line in output.splitlines():
        if not in_section:
            if "slowest" in line and "durations" in line:
                in_section = True
            continue
        if not line.strip():
            if results:
                break
            continue
        if line.startswith("="):
            if results:
                break
            continue
        match = _DURATION_RE.match(line)
        if not match:
            continue
        results.append({"nodeid": match.group(2).strip(), "seconds": float(match.group(1))})
    return results


def _xdist_available() -> bool:
    return importlib.util.find_spec("xdist") is not None


def _write_durations(path: Path, output: str) -> None:
    data = parse_durations_output(output)
    json_io.write_json_atomic(path, data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--durations", type=int, default=25)
    parser.add_argument(
        "--write-durations",
        nargs="?",
        const=str(DEFAULT_DURATIONS_PATH),
        default=None,
        help="Write durations JSON; optional path (default .mesh/metrics/pytest_durations_fast.json)",
    )
    parser.add_argument("--xdist", action="store_true", help="Use pytest-xdist if available")
    parser.add_argument(
        "--repo-root",
        help="Override repo root (default: project root).",
    )
    args = parser.parse_args(argv)

    env_repo_root = os.getenv("MESH_PYTEST_FAST_REPO_ROOT")
    repo_root = Path(
        args.repo_root or env_repo_root or Path(__file__).resolve().parents[1]
    ).resolve()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *build_pytest_args(
            [
                "-q",
                "-W",
                "error",
                "--strict-markers",
                "--durations",
                str(args.durations),
                "-m",
                "fast",
            ]
        ),
    ]
    xdist_enabled = False
    if args.xdist:
        if _xdist_available():
            cmd += ["-n", "auto"]
            xdist_enabled = True
        else:
            print("pytest-fast: xdist not available, running serial")

    env = build_pytest_env(os.environ)
    log_path = repo_root / "artifacts" / "pytest_fast.log"
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
    print(f"pytest-fast: wrote log: {log_path}")
    if args.write_durations is not None:
        durations_path = Path(args.write_durations)
        if not durations_path.is_absolute():
            durations_path = repo_root / durations_path
        print(f"pytest-fast: durations path: {durations_path}")
    if args.write_durations is None:
        result = subprocess.run(cmd, cwd=repo_root, text=True, env=env)
        return int(result.returncode)

    result = subprocess.run(
        cmd,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    write_path = Path(args.write_durations)
    if not write_path.is_absolute():
        write_path = repo_root / write_path
    _write_durations(write_path, result.stdout or "")
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
