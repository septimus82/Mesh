"""Extended's duplicate pull-request run (#422): #344's lanes are left out only when the push run of the same commit
tests the same tree, every check positive; any doubt runs them, and push, schedule and dispatch are untouched."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tooling import extended_dedup
from tooling.ci_require_jobs import FetchError
from tooling.extended_dedup import decide, gh_get, summary

pytestmark = [pytest.mark.fast]

REPO, BRANCH, WORKFLOW = "septimus82/Mesh", "redesign/visual-editor", "extended.yml"
BASE, HEAD, MERGE, TREE = "b" * 40, "h" * 40, "m" * 40, "t" * 40
PUSH_RUN = {"id": 7, "event": "push", "head_branch": BRANCH, "head_sha": HEAD, "status": "in_progress",
            "conclusion": None, "created_at": "2026-11-03T05:16:51Z", "html_url": "https://github.com/x/runs/7"}
EXTENDED = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "extended.yml"


def _event(*, repo: str = REPO, ref: str = BRANCH) -> dict[str, Any]:
    return {"pull_request": {"head": {"sha": HEAD, "ref": ref, "repo": {"full_name": repo}},
                             "base": {"sha": BASE, "ref": "main"}}}


def _api(*, parents: tuple[str, ...] = (BASE, HEAD), merge_tree: str = TREE, compare: str = "ahead", behind: int = 0,
         runs: list[dict[str, Any]] | None = None, broken: str = "") -> dict[str, Any]:
    answers: dict[str, Any] = {
        f"repos/{REPO}/commits/{MERGE}": {"parents": [{"sha": p} for p in parents],
                                         "commit": {"tree": {"sha": merge_tree}}},
        f"repos/{REPO}/commits/{HEAD}": {"commit": {"tree": {"sha": TREE}}},
        f"repos/{REPO}/compare/{BASE}...{HEAD}": {"status": compare, "behind_by": behind},
        f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?event=push&branch={BRANCH}&head_sha={HEAD}&per_page=20":
            {"workflow_runs": [PUSH_RUN] if runs is None else runs},
    }
    if broken:
        answers = {k: v for k, v in answers.items() if broken not in k}
    return answers


def _decide(event: dict[str, Any] | None = None, **api: Any) -> tuple[bool, list[str], dict[str, str]]:
    answers = _api(**api)

    def get(path: str) -> Any:
        if path not in answers:
            raise FetchError(f"gh api failed (exit 1): {path}: HTTP 502")
        return answers[path]

    return decide(event or _event(), repo=REPO, sha=MERGE, push_branch=BRANCH, workflow=WORKFLOW, get=get)


@pytest.mark.parametrize("state", [{"status": "queued"}, {"status": "in_progress"},
                                   {"status": "completed", "conclusion": "success"}])
def test_344_with_the_same_tree_as_a_live_or_green_push_run_leaves_its_lanes_out(state: dict[str, str]) -> None:
    skip, lines, facts = _decide(runs=[{**PUSH_RUN, "conclusion": None, **state}])
    assert skip, lines
    assert all(line.startswith("ok ") for line in lines) and len(lines) == 6
    assert facts["push_run"] == PUSH_RUN["html_url"] and facts["base"] == BASE and facts["head"] == HEAD


@pytest.mark.parametrize(("case", "kwargs", "reason"), [
    ("a fork", {"event": _event(repo="someone/Mesh")}, "the head is from someone/Mesh"),
    ("a feature branch", {"event": _event(ref="fix/hidden-touch-door")}, "not the push-tested"),
    ("base not an ancestor", {"compare": "diverged", "behind": 3}, "not an ancestor"),
    ("behind but called ahead", {"behind": 1}, "not an ancestor"),
    ("another tree", {"merge_tree": "x" * 40}, "is not the head's"),
    ("other parents", {"parents": (BASE, "z" * 40)}, "parents are"),
    ("no push run", {"runs": []}, "no extended.yml push run"),
    ("a failed push run", {"runs": [{**PUSH_RUN, "status": "completed", "conclusion": "failure"}]}, "is failure"),
    ("a cancelled push run", {"runs": [{**PUSH_RUN, "status": "completed", "conclusion": "cancelled"}]}, "cancelled"),
    ("a timed-out push run", {"runs": [{**PUSH_RUN, "status": "completed", "conclusion": "timed_out"}]}, "timed_out"),
    ("a push run for another commit", {"runs": [{**PUSH_RUN, "head_sha": "q" * 40}]}, "no extended.yml push run"),
    ("a dispatch, not a push", {"runs": [{**PUSH_RUN, "event": "workflow_dispatch"}]}, "no extended.yml push run"),
    ("the API errs on the merge commit", {"broken": "commits/" + MERGE}, "a read failed"),
    ("the API errs on the runs", {"broken": "actions/workflows"}, "a read failed"),
    ("a malformed runs list", {"runs": "nope"}, "no extended.yml push run"),
    ("a malformed compare", {"behind": "many"}, "not as expected"),
])
def test_any_doubt_runs_the_lanes(case: str, kwargs: dict[str, Any], reason: str) -> None:
    skip, lines, _facts = _decide(**kwargs)
    assert not skip, case
    assert lines[-1].startswith("NO ") and reason in lines[-1], (case, lines)


def test_ci_asks_about_its_own_push_runs() -> None:
    # ci.yml asks the same question about ci.yml: an Extended push run is no evidence for CI, nor the reverse.
    runs_of = {wf: f"repos/{REPO}/actions/workflows/{wf}/runs?event=push&branch={BRANCH}&head_sha={HEAD}&per_page=20"
               for wf in ("ci.yml", WORKFLOW)}
    answers = {k: v for k, v in _api().items() if k != runs_of[WORKFLOW]}
    answers[runs_of["ci.yml"]] = {"workflow_runs": [PUSH_RUN]}

    def get(path: str) -> Any:
        if path not in answers:
            raise FetchError(f"gh api failed (exit 1): {path}: HTTP 404")
        return answers[path]

    assert decide(_event(), repo=REPO, sha=MERGE, push_branch=BRANCH, workflow="ci.yml", get=get)[0]
    skip, lines, _ = decide(_event(), repo=REPO, sha=MERGE, push_branch=BRANCH, workflow=WORKFLOW, get=get)
    assert not skip and "a read failed" in lines[-1]


def test_the_newest_push_run_counts_so_an_older_success_never_hides_a_newer_failure() -> None:
    older = {**PUSH_RUN, "id": 6, "status": "completed", "conclusion": "success", "created_at": "2026-11-03T05:00:00Z"}
    newer = {**PUSH_RUN, "id": 8, "status": "completed", "conclusion": "failure", "created_at": "2026-11-03T06:00:00Z"}
    assert not _decide(runs=[newer, older])[0]
    assert _decide(runs=[{**newer, "conclusion": "success"}, {**older, "conclusion": "failure"}])[0]


def test_not_a_pull_request_runs_the_lanes() -> None:
    skip, lines, _ = decide({"ref": "refs/heads/main"}, repo=REPO, sha=MERGE, push_branch=BRANCH,
                            workflow=WORKFLOW, get=lambda path: pytest.fail(f"read {path}"))
    assert not skip and "not a pull_request event" in lines[-1]


def test_a_failed_gh_call_or_garbage_is_a_fetch_error() -> None:
    def failing(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, "", "HTTP 502")

    def garbage(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, "<html>", "")

    def slow(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("gh", 30)

    for run, words in ((failing, "exit 1"), (garbage, "unreadable"), (slow, "no answer")):
        with pytest.raises(FetchError, match=words):
            gh_get("repos/x/y", run=run)


def test_the_summary_never_reads_as_a_pass() -> None:
    skip, lines, facts = _decide()
    text = summary(skip, lines, facts)
    assert "did NOT run" in text and "not a test result" in text and str(PUSH_RUN["html_url"]) in text
    assert "The test jobs run" in summary(*_decide(runs=[]))


def test_main_writes_the_step_output_only_skip_true_on_a_positive_decision(tmp_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    event, out, step = tmp_path / "event.json", tmp_path / "out", tmp_path / "summary.md"
    event.write_text(json.dumps(_event()), encoding="utf-8")
    for name, value in (("GITHUB_EVENT_PATH", event), ("GITHUB_OUTPUT", out), ("GITHUB_STEP_SUMMARY", step),
                        ("GITHUB_REPOSITORY", REPO), ("GITHUB_SHA", MERGE)):
        monkeypatch.setenv(name, str(value))
    answers = _api()
    monkeypatch.setattr(extended_dedup, "gh_get", lambda path: answers[path])
    assert extended_dedup.main(["--push-branch", BRANCH, "--workflow", WORKFLOW]) == 0
    assert out.read_text(encoding="utf-8") == "skip=true\n" and "did NOT run" in step.read_text(encoding="utf-8")


def test_the_workflow_gates_only_pull_requests_and_runs_the_lanes_on_any_doubt() -> None:
    text = EXTENDED.read_text(encoding="utf-8")
    dedup, lane = text[text.index("\n  dedup:"):text.index("\n  lane:")], text[text.index("\n  lane:"):]
    # The push-tested branch the check names is the one push runs on; the workflow it reads is this file.
    assert f"push:\n    branches: [{BRANCH}]" in text
    assert f"python3 -m tooling.extended_dedup --push-branch {BRANCH} --workflow {EXTENDED.name}" in dedup
    assert "if: github.event_name == 'pull_request'" in dedup
    assert "permissions:\n      actions: read\n      contents: read" in dedup
    assert "skip: ${{ steps.decide.outputs.skip }}" in dedup and "id: decide" in dedup
    # Only an explicit skip=true leaves the lanes out: a skipped (push/schedule/dispatch) or failed check runs them.
    assert "needs: dedup\n" in lane
    assert "if: ${{ !cancelled() && needs.dedup.outputs.skip != 'true' }}" in lane
    assert lane.count("\n    if:") == 1, "the lane job has exactly one condition"
    assert "os: [ubuntu-latest, windows-latest]" in lane and "lane: [extended, gpu]" in lane


def test_the_timing_window_counts_push_runs_so_skipped_344_runs_dont_shrink_it(tmp_path: Path,
                                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    from tooling import ci_timing_collect

    calls: list[tuple[str, ...]] = []

    def gh(*args: str) -> str:
        calls.append(args)
        return "[]"

    monkeypatch.setattr(ci_timing_collect, "_gh", gh)
    assert ci_timing_collect.collect("redesign/visual-editor", 30, tmp_path) == []
    listing = calls[0]
    assert listing[:2] == ("run", "list") and listing[listing.index("--event") + 1] == "push"


CI = EXTENDED.with_name("ci.yml")
GATE = "    needs: dedup\n    if: ${{ !cancelled() && needs.dedup.outputs.skip != 'true' }}\n"
# Every ci.yml job, by what the duplicate check does to it. A new job must be put in one of these on purpose.
CI_GATED = {"arcade3-canary", "web-smoke", "pytest", "verify", "installed", "acceptance"}
CI_UNGATED = {"dedup", "timing-rolling", "ship"}  # the check itself; push-only; release-only (never on #344)


def _ci_jobs() -> dict[str, str]:
    text = CI.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    body = text[text.index("\njobs:\n") + len("\njobs:\n"):]
    parts = re.split(r"^  ([\w-]+):\n", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def test_ci_leaves_out_every_test_job_of_a_duplicate_344_run_and_only_then() -> None:
    jobs = _ci_jobs()
    assert set(jobs) == CI_GATED | {"tests"} | CI_UNGATED
    command = jobs["dedup"].split("run: ")[-1].strip()
    assert command == f"python3 -m tooling.extended_dedup --push-branch {BRANCH} --workflow {CI.name}"
    assert "if: github.event_name == 'pull_request'" in jobs["dedup"]
    assert "permissions:\n      actions: read\n      contents: read" in jobs["dedup"]
    assert "skip: ${{ steps.decide.outputs.skip }}" in jobs["dedup"] and "id: decide" in jobs["dedup"]
    ci_text = CI.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    assert f"  push:\n    branches: [main, {BRANCH}, 'release/**']\n" in ci_text
    for name in CI_GATED:
        # The check skipped (push, dispatch) or failed runs the job; only skip=true leaves it out. Exactly one condition.
        assert GATE in jobs[name], name
        assert jobs[name].count("\n    if:") + jobs[name].startswith("    if:") == 1, name
        # A matrix job, its name from the matrix: left out, it reports its unexpanded name, never a skipped real check.
        assert "    strategy:\n" in jobs[name] and "matrix:" in jobs[name], name
        assert re.search(r"^    name: [^\n]*\$\{\{ matrix\.", jobs[name], re.M), name
    for name in ("arcade3-canary", "web-smoke"):
        # One leg, so the expanded name is the one it always had: "<name> (required, py3.11)".
        assert f"    name: {name} (required, py${{{{ matrix.python }}}})\n" in jobs[name]
        assert '      matrix:\n        python: ["3.11"]\n' in jobs[name]
    fanin = jobs["tests"]
    assert "    needs: [dedup, pytest, verify, installed, acceptance]\n" in fanin
    assert "    if: ${{ always() && needs.dedup.outputs.skip != 'true' }}\n" in fanin
    assert "    name: tests (${{ matrix.os }}, py${{ matrix.python }})\n" in fanin
    for name in CI_UNGATED - {"dedup"}:
        assert "needs:" not in jobs[name] and "dedup" not in jobs[name], name
    assert "if: github.event_name == 'push' && github.ref_name == 'redesign/visual-editor'" in jobs["timing-rolling"]


def test_a_skipped_check_on_push_runs_every_gated_job() -> None:
    # GitHub's rule: a job whose `needs` was skipped is skipped too unless its `if` uses a status function. The gate's
    # `!cancelled()` (the fan-in's `always()`) is that function, so a push run (check skipped) runs everything.
    jobs = _ci_jobs()
    for name in CI_GATED:
        condition = jobs[name].split("    if: ", 1)[1].split("\n", 1)[0]
        assert condition.startswith("${{ !cancelled() && "), name
    assert jobs["tests"].split("    if: ", 1)[1].startswith("${{ always() && ")
