"""The CI fan-in (H3, #422 F13): an OS's ``tests`` check is green only when its ``pytest`` and ``verify`` jobs both
succeeded, and the workflow is wired so that check always reports."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tooling import ci_require_jobs as fanin
from tooling.ci_require_jobs import COMPONENTS, SHARDED, FetchError, check, fetch_jobs, required_jobs, verdict

pytestmark = [pytest.mark.fast]

REQUIRED = required_jobs("windows-latest", "3.11")
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
SHARD_JOBS = ["pytest (windows-latest, py3.11, shard 1/2)", "pytest (windows-latest, py3.11, shard 2/2)"]


def _names(part: str) -> list[str]:
    """A component's Windows job names (F13-C: ``pytest`` is two shard jobs)."""
    return SHARD_JOBS if part == "pytest" else [f"{part} (windows-latest, py3.11)"]


def _jobs(**conclusions: str | None) -> list[dict[str, object]]:
    return [{"name": name, "status": "completed", "conclusion": c}
            for part, c in conclusions.items() for name in _names(part)]


ALL_OK = {part: "success" for part in COMPONENTS}


def test_the_required_jobs_are_this_os_s_pytest_verify_installed_and_acceptance() -> None:
    assert COMPONENTS == ("pytest", "verify", "installed", "acceptance")
    # F13-C: Windows' pytest is two shard jobs, each required; Linux's is one, as before.
    assert SHARDED == {"windows-latest": 2}
    assert REQUIRED == [*SHARD_JOBS, "verify (windows-latest, py3.11)",
                        "installed (windows-latest, py3.11)", "acceptance (windows-latest, py3.11)"]
    assert required_jobs("ubuntu-latest", "3.11") == [
        "pytest (ubuntu-latest, py3.11)", "verify (ubuntu-latest, py3.11)",
        "installed (ubuntu-latest, py3.11)", "acceptance (ubuntu-latest, py3.11)"]


def test_the_shard_count_is_the_one_the_shards_use() -> None:
    from tooling import ci_shards

    assert SHARDED["windows-latest"] == ci_shards.SHARDS


def test_green_only_when_all_succeeded() -> None:
    ok, lines = verdict(_jobs(**ALL_OK), REQUIRED)
    assert ok and len(lines) == 5


@pytest.mark.parametrize("bad", ["failure", "cancelled", "skipped", None, "missing"])
@pytest.mark.parametrize("shard", SHARD_JOBS)
def test_one_shard_that_did_not_succeed_is_red(shard: str, bad: str | None) -> None:
    jobs = [job for job in _jobs(**ALL_OK) if job["name"] != shard or bad != "missing"]
    for job in jobs:
        if job["name"] == shard:
            job["conclusion"] = bad
    ok, lines = verdict(jobs, REQUIRED)
    assert not ok
    assert any(line.startswith(("FAILED", "MISSING")) and shard in line for line in lines)
    # Nor does an unsharded Windows pytest job (an older workflow's) stand in for the shards.
    stale: list[dict[str, object]] = [{"name": "pytest (windows-latest, py3.11)", "conclusion": "success"}]
    assert not verdict(jobs + stale, REQUIRED)[0]


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
    pytest_job, verify_job, installed_job, acceptance_job, tests_job = (
        _job_block(text, j) for j in ("pytest", "verify", "installed", "acceptance", "tests"))
    # The component names the fan-in looks for, and the check name reviews look at.
    assert ("name: pytest (${{ matrix.os }}, py${{ matrix.python }}${{ matrix.shard && format(', shard {0}', "
            "matrix.shard) || '' }})") in pytest_job
    assert "name: verify (${{ matrix.os }}, py${{ matrix.python }})" in verify_job
    assert "name: installed (${{ matrix.os }}, py${{ matrix.python }})" in installed_job
    assert "name: acceptance (${{ matrix.os }}, py${{ matrix.python }})" in acceptance_job
    assert "name: tests (${{ matrix.os }}, py${{ matrix.python }})" in tests_job
    # It always runs after both (never left pending or skipped) and asks the jobs list, not needs.*.result.
    assert "needs: [pytest, verify, installed, acceptance]" in tests_job
    assert "if: ${{ always() }}" in tests_job
    assert "tooling/ci_require_jobs.py --os \"${{ matrix.os }}\"" in tests_job
    assert "actions: read" in tests_job
    for block in (verify_job, installed_job, acceptance_job, tests_job):
        assert "os: [ubuntu-latest, windows-latest]" in block
    for block in (pytest_job, verify_job, installed_job, acceptance_job, tests_job):
        assert "fail-fast: false" in block
    # F13-C: pytest's matrix is Linux whole and Windows as the two shards required_jobs names, nothing else.
    legs = re.findall(r"^          - \{ (.*) \}$", pytest_job, re.M)
    assert legs == ['os: ubuntu-latest, python: "3.11", shard: "", shard_index: 0',
                    'os: windows-latest, python: "3.11", shard: "1/2", shard_index: 1',
                    'os: windows-latest, python: "3.11", shard: "2/2", shard_index: 2']
    windows_run = pytest_job[pytest_job.index("Run pytest (Windows"):pytest_job.index("Run pytest (Linux)")]
    assert ("-p tooling.ci_shards_plugin --mesh-shard ${{ matrix.shard }} --mesh-shard-record "
            "artifacts/shards/shard-${{ matrix.shard_index }}.json --junitxml=artifacts/shards/junit-"
            "${{ matrix.shard_index }}.xml") in windows_run
    linux_run = pytest_job[pytest_job.index("Run pytest (Linux)"):]
    assert "xvfb-run -a python -m pytest -q\n" in linux_run and "mesh-shard" not in linux_run
    record_upload = pytest_job[pytest_job.index("Upload the shard's record"):]
    assert "if: always() && matrix.shard != ''" in record_upload and "overwrite: true" in record_upload
    assert "name: pytest-shard-${{ matrix.shard_index }}-${{ matrix.os }}-py${{ matrix.python }}" in record_upload
    # The Windows fan-in refuses unless the shards' records prove the whole suite ran once, on this commit.
    assert "pattern: pytest-shard-*-${{ matrix.os }}-py${{ matrix.python }}" in tests_job
    assert 'python3 tooling/ci_shards.py check shard-records --commit "${{ github.sha }}"' in tests_job
    assert tests_job.count("if: matrix.os == 'windows-latest'") == 2
    # Neither component may be skipped by a condition of its own, or soften its result (job-level keys only; verify's
    # PR-comment steps may fail softly, as before the split).
    for block in (pytest_job, verify_job, installed_job, acceptance_job):
        assert not re.search(r"^    (if|continue-on-error):", block, re.M)
    # acceptance (H6): the canonical creator-workflow lane, failing if it can't run its GL tests.
    assert "python -m tooling.test_tiers acceptance" in acceptance_job and "$LASTEXITCODE -ne 0" in acceptance_job
    # installed (H5): this commit's wheel, tested by the file that proves the check catches broken wheels; nothing in
    # the job installs the checkout, and the project's conftest (which imports the checkout's engine) stays out.
    assert "tests/test_wheel_bundles_engine_data.py" in installed_job and "--noconftest" in installed_job
    assert "-o addopts=" in installed_job and "-W error" in installed_job
    # The shared setup only for its display (H7: the exported games open windows), told not to install the checkout,
    # which it then doesn't.
    assert "pip install -e" not in installed_job and "mesh-ci-setup" in installed_job
    assert 'install-project: "false"' in installed_job and "$LASTEXITCODE -ne 0" in installed_job
    setup = (WORKFLOW.parents[1] / "actions" / "mesh-ci-setup" / "action.yml").read_text(encoding="utf-8")
    install_step = setup[setup.index("- name: Install dependencies"):].split("\n    - name:", 1)[0]
    assert "if: inputs.install-project == 'true'" in install_step and "pip install -e" in install_step
    assert setup.count("pip install -e") == 1
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


# --------------------------------------------------------------------------- #
# H7 (#422): the jobs list is read until one read is complete and current; the verdict is always one read's.
# --------------------------------------------------------------------------- #

ATTEMPT = 2


def _read(jobs: dict[str, Any], *, attempt: int = ATTEMPT, total: int | None = None) -> tuple[list[dict[str, Any]], int]:
    """One read of the jobs list: each job ``name: conclusion`` (finished) or ``name: (status, conclusion)``."""
    listed = []
    for part, state in jobs.items():
        status, conclusion = state if isinstance(state, tuple) else ("completed", state)
        listed += [{"name": name, "status": status, "conclusion": conclusion, "run_attempt": attempt}
                   for name in _names(part)]
    return listed, len(listed) if total is None else total


def _fan_in(*reads: tuple[list[dict[str, Any]], int] | Exception) -> tuple[bool, list[str], list[float], list[str]]:
    """Run ``check`` over these reads in order (the last one repeats): (passed, lines, sleeps, log)."""
    queue = list(reads)
    sleeps: list[float] = []
    log: list[str] = []

    def fetch() -> tuple[list[dict[str, Any]], int]:
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    ok, lines = check(fetch, REQUIRED, ATTEMPT, sleep=sleeps.append, log=log.append)
    return ok, lines, sleeps, log


def test_a_complete_current_read_decides_at_once() -> None:
    ok, lines, sleeps, _ = _fan_in(_read(ALL_OK))
    assert ok and sleeps == [] and all(line.startswith("ok") for line in lines)


def test_missing_then_complete_passes() -> None:
    ok, _, sleeps, log = _fan_in(_read({k: v for k, v in ALL_OK.items() if k != "verify"}), _read(ALL_OK))
    assert ok and sleeps == [fanin.DELAYS[0]]
    assert "verify (windows-latest, py3.11) not listed" in log[0]


def test_running_then_successful_passes() -> None:
    ok, _, sleeps, log = _fan_in(_read({**ALL_OK, "pytest": ("in_progress", None)}), _read(ALL_OK))
    assert ok and len(sleeps) == 1 and "still in_progress" in log[0]


def test_a_transient_api_failure_is_read_again() -> None:
    ok, _, sleeps, log = _fan_in(FetchError("gh api failed (exit 1, page 1): gh: Server Error (HTTP 502)"),
                                 _read(ALL_OK))
    assert ok and len(sleeps) == 1 and "HTTP 502" in log[0]


def test_an_incomplete_list_is_read_again() -> None:
    ok, _, sleeps, log = _fan_in(_read(ALL_OK, total=14), _read(ALL_OK))
    assert ok and "incomplete list: 5 of 14 jobs" in log[0]


@pytest.mark.parametrize("persistent", ["api", "missing", "running", "stale"])
def test_a_persistent_problem_fails_after_bounded_reads_saying_why(persistent: str) -> None:
    reads: dict[str, tuple[list[dict[str, Any]], int] | Exception] = {
        "api": FetchError("no answer within 30 s (page 1)"),
        "missing": _read({k: v for k, v in ALL_OK.items() if k != "acceptance"}),
        "running": _read({**ALL_OK, "verify": ("queued", None)}),
        "stale": _read(ALL_OK, attempt=ATTEMPT - 1),
    }
    ok, lines, sleeps, log = _fan_in(reads[persistent])
    assert not ok and sleeps == list(fanin.DELAYS) and len(log) == len(fanin.DELAYS)
    assert lines[0].startswith(f"no complete, current jobs list after {len(fanin.DELAYS) + 1} reads; the last one:")


@pytest.mark.parametrize("bad", ["failure", "cancelled", "timed_out", "skipped"])
def test_a_finished_component_that_failed_fails_at_once(bad: str) -> None:
    ok, lines, sleeps, _ = _fan_in(_read({**ALL_OK, "installed": bad}), _read(ALL_OK))
    assert not ok and sleeps == [], "a genuine failure is not waited out"
    assert f"FAILED  installed (windows-latest, py3.11): {bad}" in lines


def test_successes_from_different_reads_are_never_combined() -> None:
    first = _read({"pytest": "success", "verify": "success"})
    second = _read({"installed": "success", "acceptance": "success"})
    ok, lines, _, _ = _fan_in(first, second, first, second, first, second)
    assert not ok and "no complete, current jobs list" in lines[0]


def test_an_older_success_never_hides_a_newer_failure() -> None:
    older = _read(ALL_OK, attempt=1)[0]
    newer = _read({**ALL_OK, "pytest": "failure"})[0]
    ok, lines, _, _ = _fan_in((older + newer, 10))
    assert not ok and f"FAILED  {SHARD_JOBS[0]}: failure" in lines and f"FAILED  {SHARD_JOBS[1]}: failure" in lines
    ok, _, _, _ = _fan_in((newer + older, 10))
    assert not ok, "whatever the order GitHub lists them in"


def test_a_stale_read_of_an_earlier_attempt_is_read_again() -> None:
    ok, lines, sleeps, log = _fan_in(_read({**ALL_OK, "verify": "failure"}, attempt=1), _read(ALL_OK))
    assert ok and len(sleeps) == 1 and "listed from attempt 1, not this attempt (2)" in log[0]


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], returncode, stdout, stderr)


def test_fetch_reads_every_page_with_a_timeout() -> None:
    calls: list[tuple[list[str], object]] = []

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kw["timeout"]))
        page = int(cmd[-1].rsplit("page=", 1)[1])
        jobs = [{"name": f"j{page}-{i}"} for i in range(100 if page == 1 else 50)]
        return _proc(0, json.dumps({"total_count": 150, "jobs": jobs}))

    jobs, total = fetch_jobs("o/r", "7", timeout=12, run=run)
    assert (len(jobs), total) == (150, 150) and len(calls) == 2
    assert all(t == 12 for _, t in calls) and "filter=latest" in calls[0][0][-1]


def test_fetch_errors_are_named_and_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "s3cr3t-token-value")

    def failing(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        return _proc(1, stderr="gh: Server Error (HTTP 502) token=s3cr3t-token-value ghs_abcdefghijklmnopqrstuvwxyz0123")

    def slow(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, 30)

    def garbled(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        return _proc(0, "<html>502</html>")

    with pytest.raises(FetchError) as err:
        fetch_jobs("o/r", "7", run=failing)
    assert "HTTP 502" in str(err.value) and "s3cr3t" not in str(err.value) and "ghs_" not in str(err.value)
    with pytest.raises(FetchError, match="no answer within 30 s"):
        fetch_jobs("o/r", "7", run=slow)
    with pytest.raises(FetchError, match="unreadable answer"):
        fetch_jobs("o/r", "7", run=garbled)
