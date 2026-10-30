"""Every test runs somewhere (H6, #422): the default suite, the extended lane (slow/e2e) or the gpu lane (needs GL),
selected by tooling/test_tiers.py, which CI's workflows run; and a lane that runs nothing never reports success."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tooling import test_tiers

# The subprocess checks are `integration` (the default suite), not `fast`: the fast tier is timed in verify-all.

REPO = Path(__file__).resolve().parents[1]
BACKGROUND = "tests/test_background_layers_render_contract.py"


def _baseline() -> dict[str, str]:
    rows = {}
    for line in (REPO / "tests" / "baselines" / "never_runs.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            nodeid, _, reason = line.partition("#")
            rows[nodeid.strip()] = reason.strip()
    return rows


@pytest.mark.fast
def test_every_gl_opt_in_is_found_by_the_capability_rule(gl_opt_in_unmarked: list[str]) -> None:
    # A test in a module that gates on MESH_GL_SMOKE but isn't `gl`-marked would run in no lane that has GL.
    assert not gl_opt_in_unmarked, "GL-gated some other way than the suite's skipif:\n" + "\n".join(gl_opt_in_unmarked)


@pytest.mark.fast
def test_no_test_runs_nowhere_unless_listed(never_runs_nodeids: list[str]) -> None:
    listed = _baseline()
    assert all(listed.values()), "every listed test says why it runs nowhere"
    unlisted = sorted(set(never_runs_nodeids) - set(listed))
    assert not unlisted, "these tests run in no lane (list them with a reason, or make them runnable):\n" + "\n".join(unlisted)


def _pytest(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    run_env = {k: v for k, v in os.environ.items() if k not in ("MESH_GL_SMOKE", "MESH_REQUIRE_GL", "PYTEST_ADDOPTS")}
    run_env.update(env or {})
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", *args],
                          cwd=REPO, env=run_env, capture_output=True, text=True, encoding="utf-8", errors="replace")


@pytest.mark.integration
def test_the_gpu_lane_finds_the_background_rendering_tests_by_capability() -> None:
    # They live in a file a test_*_gpu.py glob never matched (Astra, #422).
    proc = _pytest("--collect-only", "-q", "-m", "gl", BACKGROUND)
    selected = [line for line in proc.stdout.splitlines() if "::" in line]
    assert len(selected) == 2 and all(BACKGROUND in line for line in selected), proc.stdout[-800:]


@pytest.mark.integration
def test_a_gl_test_without_gl_fails_the_gpu_lane_instead_of_passing_as_skipped() -> None:
    # MESH_REQUIRE_GL=1 without MESH_GL_SMOKE: the opt-in gate skips them, and the gpu lane turns that into failures.
    proc = _pytest("-q", "-m", "gl", BACKGROUND, env={"MESH_REQUIRE_GL": "1"})
    assert proc.returncode != 0
    # The gate skips at setup, so pytest counts them as errors: red either way, and saying why.
    assert ("2 failed" in proc.stdout or "2 errors" in proc.stdout) and "skipped by its opt-in gate" in proc.stdout
    # Outside the gpu lane the same tests are visible skips, as in the default suite.
    proc = _pytest("-q", "-rs", "-m", "gl", BACKGROUND)
    assert proc.returncode == 0 and "2 skipped" in proc.stdout and "MESH_GL_SMOKE" in proc.stdout


@pytest.mark.fast
def test_an_empty_or_all_skipped_lane_is_not_a_success(tmp_path: Path) -> None:
    def run(cases: str) -> test_tiers.LaneRun:
        path = tmp_path / "junit.xml"
        path.write_text(f'<testsuites><testsuite time="1.5">{cases}</testsuite></testsuites>', encoding="utf-8")
        return test_tiers.summarize_junit(path)

    empty = run("")
    assert test_tiers.lane_problems(empty, gl_renderer="x", gl_tier=False) == ["the lane selected no test"]
    assert test_tiers.lane_problems(None, gl_renderer="x", gl_tier=False) == ["the lane selected no test"]
    skipped = run('<testcase classname="t" name="a"><skipped message="no GL"/></testcase>')
    assert (skipped.selected, skipped.skipped, skipped.skip_reasons) == (1, 1, {"no GL": 1})
    assert test_tiers.lane_problems(skipped, gl_renderer="x", gl_tier=False) == [
        "the lane ran no test (every selected test was skipped)"]
    good = run('<testcase classname="t" name="a"/><testcase classname="t" name="b"><failure/></testcase>')
    assert (good.passed, good.failed, good.seconds) == (1, ["t::b"], 1.5)
    assert test_tiers.lane_problems(good, gl_renderer=None, gl_tier=True) == ["no GL context here: a GPU lane can't run"]
    assert test_tiers.lane_problems(good, gl_renderer="llvmpipe", gl_tier=True) == []
    # A lane that suddenly finds fewer tests than it should (a marker or rule change dropped some) fails.
    assert test_tiers.lane_problems(good, gl_renderer="x", gl_tier=False, min_selected=3) == [
        "the lane selected 2 tests, fewer than the 3 it should"]
    assert {name: tier.min_selected for name, tier in test_tiers.TIERS.items() if tier.min_selected} == {
        "extended": 162, "gpu": 256, "acceptance": 27}


@pytest.mark.fast
def test_the_acceptance_lane_is_creator_workflow_gl_tests_that_exist() -> None:
    for path in test_tiers.ACCEPTANCE:
        source = (REPO / path).read_text(encoding="utf-8")
        assert "MESH_GL_SMOKE" in source, f"{path} is not a GL test, so the acceptance lane (-m gl) would skip it"
    assert BACKGROUND in test_tiers.ACCEPTANCE


@pytest.mark.fast
def test_the_extended_workflow_runs_both_lanes_by_the_canonical_selection() -> None:
    text = (REPO / ".github" / "workflows" / "extended.yml").read_text(encoding="utf-8")
    # Regular and on demand, with the same selection: after each integration merge, nightly, by hand, and on a PR
    # that changes the selection policy.
    for trigger in ("push:\n    branches: [redesign/visual-editor]", "schedule:", "workflow_dispatch:", "pull_request:"):
        assert trigger in text
    for policy_file in ("tooling/test_tiers.py", "tests/conftest.py", "pytest.ini"):
        assert f'"{policy_file}"' in text
    assert "os: [ubuntu-latest, windows-latest]" in text and "lane: [extended, gpu]" in text
    assert "python -m tooling.test_tiers ${{ matrix.lane }}" in text
    assert "continue-on-error" not in text and "if: ${{ always() }}" not in text.split("Run the ${{ matrix.lane }} lane")[1][:400]
    assert text.count("if: always()") == 2, "the summary and the reports are kept when a lane fails"
    assert "SOFTWARE renderer" in text, "a Mesa pass is not claimed as physical-GPU evidence"
