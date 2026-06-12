from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tooling.pytest_runner_common import (
    build_pytest_args,
    build_pytest_env,
    format_xdist,
    write_runner_log,
)


@dataclass(frozen=True)
class TierDef:
    pytest_mark: str | None
    verify_all: bool
    compileall: bool


TIERS: dict[str, TierDef] = {
    "tier0": TierDef(pytest_mark="fast", verify_all=False, compileall=True),
    "tier1": TierDef(pytest_mark="fast or integration", verify_all=True, compileall=False),
    "tier2": TierDef(pytest_mark=None, verify_all=False, compileall=False),
}


def _xdist_available() -> bool:
    return importlib.util.find_spec("xdist") is not None


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, env=env)
    return int(result.returncode)


def _pytest_cmd(
    *, mark_expr: str | None, extra_args: list[str], xdist_jobs: str | None
) -> list[str]:
    pytest_args = [
        "-q",
        "-W",
        "error",
        "--strict-markers",
    ]
    if mark_expr:
        pytest_args += ["-m", mark_expr]
    if xdist_jobs:
        pytest_args += ["-n", xdist_jobs]
    pytest_args += extra_args
    return [sys.executable, "-m", "pytest", *build_pytest_args(pytest_args)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tier", choices=sorted(TIERS.keys()))
    parser.add_argument("--xdist", action="store_true", help="Use pytest-xdist if available")
    parser.add_argument(
        "--jobs",
        help="xdist job count (default: auto). Requires --xdist.",
    )
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    tier_cfg = TIERS[args.tier]

    extra_args = args.pytest_args
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    xdist_jobs: str | None = None
    if args.xdist or args.jobs:
        if _xdist_available():
            xdist_jobs = args.jobs or "auto"
        else:
            print("test-tiers: xdist not available, running serial")

    if tier_cfg.compileall:
        rc = _run([sys.executable, "-m", "compileall", "-q", "engine", "mesh_cli", "tooling", "tests"], cwd=repo_root)
        if rc != 0:
            return rc

    pytest_cmd = _pytest_cmd(
        mark_expr=tier_cfg.pytest_mark,
        extra_args=extra_args,
        xdist_jobs=xdist_jobs,
    )
    log_path = repo_root / "artifacts" / f"pytest_{args.tier}.log"
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    write_runner_log(
        log_path,
        {
            "repo_root": str(repo_root),
            "python": py_version,
            "PYTEST_ADDOPTS": "cleared",
            "xdist": format_xdist(xdist_jobs is not None, xdist_jobs),
            "tier": args.tier,
        },
        pytest_cmd,
    )
    print(f"test-tiers: wrote log: {log_path}")
    rc = _run(pytest_cmd, cwd=repo_root, env=build_pytest_env())
    if rc != 0:
        return rc

    if tier_cfg.verify_all:
        rc = _run([sys.executable, "-m", "mesh_cli", "verify-all", "--artifacts", "artifacts"], cwd=repo_root)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
