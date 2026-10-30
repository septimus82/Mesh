"""The CI fan-in (H3, #422 F13): an OS's ``tests`` check is green only when its ``pytest`` and ``verify`` jobs both
succeeded, and the workflow is wired so that check always reports."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tooling.ci_require_jobs import COMPONENTS, required_jobs, verdict

pytestmark = [pytest.mark.fast]

REQUIRED = required_jobs("windows-latest", "3.11")
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _jobs(**conclusions: str | None) -> list[dict[str, object]]:
    return [{"name": f"{part} (windows-latest, py3.11)", "status": "completed", "conclusion": c}
            for part, c in conclusions.items()]


ALL_OK = {part: "success" for part in COMPONENTS}


def test_the_required_jobs_are_this_os_s_pytest_verify_and_installed() -> None:
    assert COMPONENTS == ("pytest", "verify", "installed")
    assert REQUIRED == ["pytest (windows-latest, py3.11)", "verify (windows-latest, py3.11)",
                        "installed (windows-latest, py3.11)"]


def test_green_only_when_all_succeeded() -> None:
    ok, lines = verdict(_jobs(**ALL_OK), REQUIRED)
    assert ok and len(lines) == 3


@pytest.mark.parametrize("bad", ["failure", "cancelled", "skipped", "timed_out", "action_required", None])
@pytest.mark.parametrize("which", COMPONENTS)
def test_any_other_conclusion_of_any_job_is_red(which: str, bad: str | None) -> None:
    conclusions: dict[str, str | None] = {**ALL_OK, which: bad}
    ok, lines = verdict(_jobs(**conclusions), REQUIRED)
    assert not ok
    assert any(line.startswith("FAILED") and which in line for line in lines)


@pytest.mark.parametrize("absent", COMPONENTS)
def test_a_missing_job_is_red(absent: str) -> None:
    ok, lines = verdict(_jobs(**{k: v for k, v in ALL_OK.items() if k != absent}), REQUIRED)
    assert not ok
    assert any(line.startswith("MISSING") and absent in line for line in lines)


def test_the_other_os_does_not_count() -> None:
    other = [{"name": f"{part} (ubuntu-latest, py3.11)", "conclusion": "success"} for part in COMPONENTS]
    assert not verdict(other + _jobs(**{**ALL_OK, "installed": "failure"}), REQUIRED)[0]
    assert not verdict(other, REQUIRED)[0]


def test_the_latest_entry_of_a_rerun_job_wins() -> None:
    assert verdict(_jobs(**{**ALL_OK, "pytest": "failure"}) + _jobs(pytest="success"), REQUIRED)[0]
    assert not verdict(_jobs(**ALL_OK) + _jobs(installed="failure"), REQUIRED)[0]


def _job_block(text: str, job: str) -> str:
    match = re.search(rf"^  {job}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.S | re.M)
    assert match, job
    return match.group(1)


def test_the_workflow_fans_every_job_into_the_tests_check() -> None:
    text = WORKFLOW.read_text(encoding="utf-8-sig")
    pytest_job, verify_job, installed_job, tests_job = (_job_block(text, j) for j in ("pytest", "verify", "installed", "tests"))
    # The component names the fan-in looks for, and the check name reviews look at.
    assert "name: pytest (${{ matrix.os }}, py${{ matrix.python }})" in pytest_job
    assert "name: verify (${{ matrix.os }}, py${{ matrix.python }})" in verify_job
    assert "name: installed (${{ matrix.os }}, py${{ matrix.python }})" in installed_job
    assert "name: tests (${{ matrix.os }}, py${{ matrix.python }})" in tests_job
    # It always runs after both (never left pending or skipped) and asks the jobs list, not needs.*.result.
    assert "needs: [pytest, verify, installed]" in tests_job
    assert "if: ${{ always() }}" in tests_job
    assert "tooling/ci_require_jobs.py --os \"${{ matrix.os }}\"" in tests_job
    assert "actions: read" in tests_job
    for block in (pytest_job, verify_job, installed_job, tests_job):
        assert "os: [ubuntu-latest, windows-latest]" in block
        assert "fail-fast: false" in block
    # Neither component may be skipped by a condition of its own, or soften its result (job-level keys only; verify's
    # PR-comment steps may fail softly, as before the split).
    for block in (pytest_job, verify_job, installed_job):
        assert not re.search(r"^    (if|continue-on-error):", block, re.M)
    # installed (H5): this commit's wheel, tested by the file that proves the check catches broken wheels; nothing in
    # the job installs the checkout, and the project's conftest (which imports the checkout's engine) stays out.
    assert "tests/test_wheel_bundles_engine_data.py" in installed_job and "--noconftest" in installed_job
    assert "-o addopts=" in installed_job and "-W error" in installed_job
    assert "pip install -e" not in installed_job and "mesh-ci-setup" not in installed_job
    # Each half does its own work: the full suite in pytest; verify-all, the bundle and the artifacts in verify.
    assert "python -m pytest" in pytest_job
    # verify only collects (to start verify-all as warm as it did after the full run): the suite never runs twice.
    collects = [line for line in verify_job.splitlines() if "python -m pytest" in line]
    assert collects and all("--collect-only" in line for line in collects)
    assert verify_job.index("--collect-only") < verify_job.index("Run verify-all (Windows)")
    # Its output is filtered, so a failed collection must fail the step by its own exit code, not pass as a warm-up.
    assert all(line.split("{", 1)[1].strip().startswith("$out = ") and "|" not in line for line in collects)
    warm = verify_job[verify_job.index("Warm pytest's caches"):verify_job.index("Run verify-all (Windows)")]
    assert "$code = $LASTEXITCODE" in warm
    assert re.search(r"if \(\$code -ne 0\) \{.*throw ", warm)
    for step in ("Run verify-all (Windows)", "Run verify-all (Linux)", "Build release bundle (seeded, Windows)",
                 "Build release bundle (seeded, Linux)", "name: mesh-artifacts-${{ matrix.os }}-py${{ matrix.python }}"):
        assert step in verify_job
    assert "verify-all" not in pytest_job
