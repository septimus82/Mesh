"""The canonical test lanes, for local runs and CI alike (H6, #422).

    python -m tooling.test_tiers <tier> [-- extra pytest args]

* ``tier0``/``tier1``/``tier2``: fast, fast + integration (+ verify-all), everything the default run selects.
* ``extended``: the tests the default run deselects (``slow``/``e2e``) and that need no GL context. CI's extended
  workflow runs it; the default suite never does.
* ``gpu``: every test that needs a real GL context, found by capability (the ``gl`` marker tests/conftest.py gives
  each test whose skipif names MESH_GL_SMOKE), not by file name. Run with MESH_GL_SMOKE=1 and MESH_REQUIRE_GL=1, so a
  GL test skipped for want of GL fails instead of passing quietly.
* ``acceptance``: the creator-workflow GL tests (``ACCEPTANCE``): save and reopen, dialogue, new-game isolation,
  creator editing, background rendering. A subset of ``gpu``.

Every lane writes a JUnit report and ``pytest_<tier>_summary.json`` under artifacts/, and fails when it selects or
runs no test, besides failing on any failed test (pytest's own exit code).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass, field
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
    paths: tuple[str, ...] = ()  # test files to run (default: all of tests/)
    env: tuple[tuple[str, str], ...] = ()
    pytest_args: tuple[str, ...] = ()
    # The lane fails when it selects fewer: a marker or rule change that drops tests is caught, not reported as green.
    # Lower it only on purpose, when tests are removed.
    min_selected: int = 0


# Creator-workflow acceptance, required on every PR (CI's acceptance (<os>) jobs): what a person making a game relies
# on most, in a real (hidden) GL window. Measured on CI's Mesa (#422 H6): about 77 s on Linux, 131 s on Windows.
# tests/test_dialogue_reopen_gpu.py (dialogue edits persist across reopen) is left to the gpu lane (every merge and
# nightly): 196 s / 369 s alone, it would lengthen required PR feedback by about two minutes.
ACCEPTANCE = (
    "tests/test_saved_world_gpu.py",            # save, reopen, play: the saved world comes back
    "tests/test_new_game_isolation_gpu.py",     # a new game starts clean, not with the editor's state
    "tests/test_studio_workflow_polish_gpu.py",  # creator field editing in Mesh Studio
    "tests/test_background_layers_render_contract.py",  # background layers reach the screen
)
GL_ENV = (("MESH_GL_SMOKE", "1"), ("MESH_REQUIRE_GL", "1"))

TIERS: dict[str, TierDef] = {
    "tier0": TierDef(pytest_mark="fast", verify_all=False, compileall=True),
    "tier1": TierDef(pytest_mark="fast or integration", verify_all=True, compileall=False),
    "tier2": TierDef(pytest_mark=None, verify_all=False, compileall=False),
    # The installed-product tests are slow but already run, isolated, in CI's required installed (<os>) jobs.
    "extended": TierDef(pytest_mark="(slow or e2e) and not gl", verify_all=False, compileall=False,
                        pytest_args=("--ignore=tests/test_wheel_bundles_engine_data.py",), min_selected=162),
    # Rendering, in hidden windows (nothing shown on the desktop, no input), wherever a GL context exists.
    "gpu": TierDef(pytest_mark="gl", verify_all=False, compileall=False, env=GL_ENV, min_selected=256),
    "acceptance": TierDef(pytest_mark="gl", verify_all=False, compileall=False, paths=ACCEPTANCE, env=GL_ENV,
                          min_selected=22),
}


@dataclass
class LaneRun:
    """What a lane selected and what actually ran (from its JUnit report)."""

    selected: int = 0
    passed: int = 0
    failed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0


def summarize_junit(path: Path) -> LaneRun:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))

    def name(case: ET.Element) -> str:
        return f"{case.get('classname')}::{case.get('name')}"

    failed = [c for c in cases if c.find("failure") is not None]
    errors = [c for c in cases if c.find("error") is not None]
    skips = [s for s in (c.find("skipped") for c in cases) if s is not None]
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return LaneRun(
        selected=len(cases),
        passed=len(cases) - len(failed) - len(errors) - len(skips),
        failed=sorted(name(c) for c in failed),
        errors=sorted(name(c) for c in errors),
        skipped=len(skips),
        skip_reasons=dict(Counter((s.get("message") or "").strip()[:160] for s in skips).most_common()),
        seconds=round(sum(float(s.get("time") or 0) for s in suites), 1),
    )


def lane_problems(run: LaneRun | None, *, gl_renderer: str | None, gl_tier: bool, min_selected: int = 0) -> list[str]:
    """Why a lane's run doesn't count, even when pytest itself passed: it selected or ran nothing, fewer tests than
    it should, or (a GPU lane) it had no GL context."""
    problems = []
    if run is None or not run.selected:
        problems.append("the lane selected no test")
    elif run.passed + len(run.failed) + len(run.errors) == 0:
        problems.append("the lane ran no test (every selected test was skipped)")
    if run is not None and 0 < run.selected < min_selected:
        problems.append(f"the lane selected {run.selected} tests, fewer than the {min_selected} it should")
    if gl_tier and not gl_renderer:
        problems.append("no GL context here: a GPU lane can't run")
    return problems


def gl_renderer() -> str | None:
    """The GL renderer a hidden window gets here (e.g. Mesa's llvmpipe in CI), or None without one."""
    probe = ("import pyglet; w = pyglet.window.Window(visible=False); from pyglet.gl import gl_info; "
             "print(gl_info.get_renderer(), '|', gl_info.get_version_string()); w.close()")
    proc = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    return proc.stdout.strip().splitlines()[-1] if proc.returncode == 0 and proc.stdout.strip() else None


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
        "-p",
        "no:cacheprovider",  # a tier needs no cache; an unwritable .pytest_cache failed every run under -W error
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


SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swiftshader", "software")


def _tier_env(tier_cfg: TierDef, renderer: str | None = None) -> dict[str, str]:
    env = build_pytest_env()
    env.update(dict(tier_cfg.env))
    if renderer and any(name in renderer.lower() for name in SOFTWARE_RENDERERS):
        env["MESH_GL_SOFTWARE"] = "1"  # tests marked gpu_hardware skip, visibly, instead of failing
    return env


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
        extra_args=[*tier_cfg.pytest_args, *tier_cfg.paths, *extra_args],
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
    junit = repo_root / "artifacts" / f"pytest_{args.tier}.xml"
    pytest_cmd += [f"--junitxml={junit}", "-rfEs"]
    gl_tier = dict(tier_cfg.env).get("MESH_GL_SMOKE") == "1"
    renderer = gl_renderer() if gl_tier else None
    rc = _run(pytest_cmd, cwd=repo_root, env=_tier_env(tier_cfg, renderer))
    run = summarize_junit(junit) if junit.is_file() else None
    problems = lane_problems(run, gl_renderer=renderer, gl_tier=gl_tier,
                             min_selected=0 if extra_args else tier_cfg.min_selected)
    summary = {"tier": args.tier, "pytest_exit": rc, "selection": tier_cfg.pytest_mark, "paths": list(tier_cfg.paths),
               "gl_renderer": renderer, **(asdict(run) if run else {}), "problems": problems}
    (repo_root / "artifacts" / f"pytest_{args.tier}_summary.json").write_text(json.dumps(summary, indent=1) + "\n",
                                                                               encoding="utf-8")
    if run is not None:
        print(f"test-tiers: {args.tier}: selected {run.selected}, passed {run.passed}, failed {len(run.failed)}, "
              f"errors {len(run.errors)}, skipped {run.skipped}" + (f"; GL renderer: {renderer}" if gl_tier else ""))
        for reason, count in run.skip_reasons.items():
            print(f"test-tiers:   skipped {count}: {reason}")
    for problem in problems:
        print(f"test-tiers: FAILED: {problem}")
    if rc != 0:
        return rc
    if problems:
        return 1

    if tier_cfg.verify_all:
        rc = _run([sys.executable, "-m", "mesh_cli", "verify-all", "--artifacts", "artifacts"], cwd=repo_root)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
