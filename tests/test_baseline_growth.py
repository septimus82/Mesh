"""Baselines don't grow without a reason (#624 phase B, PR b): ``tooling/baseline_growth.py`` on synthetic git repos.

Each case builds a repo whose ``main`` holds the baselines, branches, changes one, commits, and checks against ``main``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tooling import baseline_growth

pytestmark = [pytest.mark.integration]  # real git subprocesses

RUFF = "tooling/ruff_baseline.txt"
POLICY = "tooling/exception_policy_baseline.json"
BUDGET = "tooling/metrics/exception_budget_count.txt"
NEVER_RUNS = "tests/baselines/never_runs.txt"
MARKER_CAP = "tests/test_todo_audit_ratchet_contract.py"
STEP_BUDGET = "tooling/metrics/verify_step_budget.json"
PERF = "tooling/perf_baselines/baselines.json"
_STEP_BUDGET = {"schema_version": 2, "tolerance_ms": 50, "budgets_ms": {"verify-demo": 100},
                "platforms": {"linux": {"budgets_ms": {"verify-demo": 80}, "ratio_limits": {"verify-demo": 1.25}}},
                "report_only_note": "text is not a limit"}
_PERF = {"schema_version": 1, "ticks": 120, "metric_names": ["a"],
         "scenes": [{"id": "hall", "path": "h.json", "counters": {"a": 5}},
                    {"id": "field", "path": "f.json", "counters": {"a": 7}}]}


def _json_with(base: dict, change) -> str:  # noqa: ANN001
    data = json.loads(json.dumps(base))
    change(data)
    return json.dumps(data)


BASE_FILES = {
    RUFF: "a.py: F401 unused\nb.py: E501 long\n",
    baseline_growth.MYPY_BASELINE: "c.py: error: bad  [arg-type]\n",
    POLICY: json.dumps({"schema_version": 1, "ble001_count_total": 5, "broad_catch_count_total": 9}),
    BUDGET: "3\n",
    NEVER_RUNS: "# header\ntests/test_x.py::test_a  # needs a thing\n",
    MARKER_CAP: "BASELINE_TOTAL = 35\n",
    STEP_BUDGET: json.dumps(_STEP_BUDGET),
    PERF: json.dumps(_PERF),
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


def _init(root: Path) -> None:
    _git(root, "init", "-q", "-b", "main")
    for key, value in (("core.autocrlf", "false"), ("user.name", "t"), ("user.email", "t@example.invalid")):
        _git(root, "config", key, value)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _init(root)
    for rel, text in BASE_FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _commit(root, "base")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def _change(repo: Path, rel: str, text: str | None, message: str = "change") -> None:
    if text is None:
        (repo / rel).unlink()
    else:
        (repo / rel).write_text(text, encoding="utf-8")
    _commit(repo, message)


def test_no_change_passes(repo: Path) -> None:
    _commit(repo, "unrelated")
    assert baseline_growth.check(repo, "main") == (0, [])


def test_growth_without_a_marker_fails_and_says_what_grew(repo: Path) -> None:
    _change(repo, RUFF, BASE_FILES[RUFF] + "c.py: F841 unused var\n")

    code, lines = baseline_growth.check(repo, "main")

    assert code == 1
    assert f"no 'baseline-growth: {RUFF}: <reason>' line" in lines[0]
    assert lines[1].strip() == "+ c.py: F841 unused var"


def test_growth_with_a_marker_in_any_commit_passes(repo: Path) -> None:
    _change(repo, RUFF, BASE_FILES[RUFF] + "c.py: F841 unused var\n",
            f"Upgrade ruff\n\nbaseline-growth: {RUFF}: ruff 0.16 reports a new rule on old code\n")
    _commit(repo, "a later commit")

    code, lines = baseline_growth.check(repo, "main")

    assert code == 0
    assert lines[0] == f"{RUFF} grew, explained: ruff 0.16 reports a new rule on old code"


@pytest.mark.parametrize("message", [
    f"baseline-growth: {baseline_growth.MYPY_BASELINE}: another file's reason",  # names a different baseline
    f"baseline-growth: {RUFF}:",  # no reason
    f"baseline-growth: {RUFF}:   ",
    f"see baseline-growth: {RUFF}: not at the start of a line",
])
def test_a_marker_must_name_the_file_and_give_a_reason(repo: Path, message: str) -> None:
    _change(repo, RUFF, BASE_FILES[RUFF] + "c.py: F841 unused var\n", f"change\n\n{message}\n")

    assert baseline_growth.check(repo, "main")[0] == 1


def test_a_marker_on_the_base_branch_does_not_count(repo: Path) -> None:
    _git(repo, "checkout", "-q", "main")
    _commit(repo, f"old\n\nbaseline-growth: {RUFF}: an earlier change's reason\n")
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "--no-edit", "main")
    _change(repo, RUFF, BASE_FILES[RUFF] + "c.py: F841 unused var\n")

    assert baseline_growth.check(repo, "main")[0] == 1


@pytest.mark.parametrize(("rel", "text"), [
    (RUFF, "a.py: F401 unused\n"),  # an entry fixed and removed
    (NEVER_RUNS, "# header\n"),
    (POLICY, json.dumps({"schema_version": 2, "ble001_count_total": 4, "broad_catch_count_total": 9})),
    (BUDGET, "2\n"),
    (MARKER_CAP, "BASELINE_TOTAL = 30\n"),
    (NEVER_RUNS, "# a reworded header\ntests/test_x.py::test_a  # a reworded reason\n"),  # same entries
    (MARKER_CAP, "BASELINE_TOTAL = 99\nBASELINE_TOTAL = 30\n"),  # the last assignment is the cap
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d["platforms"]["linux"]["budgets_ms"].update({"verify-demo": 70}))),
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d.update(report_only_note="reworded", schema_version=3))),
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d["budgets_ms"].update({"web-smoke": 10}))),  # a new limit
    (PERF, _json_with(_PERF, lambda d: d["scenes"].reverse())),  # records by id: reordering isn't growth
    (PERF, _json_with(_PERF, lambda d: d["scenes"][0]["counters"].update(a=4))),
])
def test_shrinking_or_rewording_passes(repo: Path, rel: str, text: str) -> None:
    _change(repo, rel, text)
    assert baseline_growth.check(repo, "main") == (0, [])


@pytest.mark.parametrize(("rel", "text", "row"), [
    (baseline_growth.MYPY_BASELINE, BASE_FILES[baseline_growth.MYPY_BASELINE] * 2,
     "+ c.py: error: bad  [arg-type]"),  # the same entry once more
    (NEVER_RUNS, BASE_FILES[NEVER_RUNS] + "tests/test_y.py::test_b  # why\n", "+ tests/test_y.py::test_b"),
    (POLICY, json.dumps({"schema_version": 1, "ble001_count_total": 5, "broad_catch_count_total": 10}),
     "broad_catch_count_total: 9 -> 10"),
    (POLICY, json.dumps({"schema_version": 1, "ble001_count_total": 5}), "broad_catch_count_total: 9 -> removed"),
    (BUDGET, "4\n", "3 -> 4"),
    (MARKER_CAP, "BASELINE_TOTAL = 36\n", "35 -> 36"),
    (MARKER_CAP, "BASELINE_TOTAL = 30\nBASELINE_TOTAL = 40\n", "35 -> 40"),  # Python keeps the last one
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d["platforms"]["linux"]["ratio_limits"].update({"verify-demo": 1.5})),
     "platforms.linux.ratio_limits.verify-demo: 1.25 -> 1.5"),
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d.update(tolerance_ms=60)), "tolerance_ms: 50 -> 60"),
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d["budgets_ms"].pop("verify-demo")),
     "budgets_ms.verify-demo: 100 -> removed"),
    # a new report-only ceiling turns a hard timing limit report-only (#697)
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d.update(report_only_ceiling_ratios={"verify-demo": 1.65})),
     "report_only_ceiling_ratios.verify-demo: new 1.65"),
    (STEP_BUDGET, _json_with(_STEP_BUDGET, lambda d: d["platforms"]["linux"].update(
        report_only_ceiling_ratios={"verify-demo": 1.65})), "platforms.linux.report_only_ceiling_ratios.verify-demo: new 1.65"),
    (PERF, _json_with(_PERF, lambda d: d["scenes"][1]["counters"].update(a=8)), "scenes[field].counters.a: 7 -> 8"),
    (PERF, _json_with(_PERF, lambda d: d["scenes"].pop(0)), "scenes[hall].counters.a: 5 -> removed"),
    (BUDGET, None, "deleted"),
])
def test_every_kind_of_baseline_growth_fails(repo: Path, rel: str, text: str | None, row: str) -> None:
    _change(repo, rel, text)

    code, lines = baseline_growth.check(repo, "main")

    assert code == 1
    assert lines[0].startswith(f"{rel} grew since ")
    assert row in [line.strip() for line in lines[1:]]


def test_a_new_public_api_export_is_growth(repo: Path) -> None:
    api = "tests/baselines/public_api_exports.txt"
    _git(repo, "checkout", "-q", "main")
    (repo / api).write_text("runtime:run_game\n", encoding="utf-8")
    _commit(repo, "api")
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "--no-edit", "main")
    _change(repo, api, "runtime:run_game\nruntime:load_scene_payload\n")

    code, lines = baseline_growth.check(repo, "main")

    assert code == 1 and "+ runtime:load_scene_payload" in [line.strip() for line in lines]


def test_a_baseline_new_since_the_merge_base_has_nothing_to_grow_from(repo: Path) -> None:
    _git(repo, "rm", "-q", RUFF)
    _commit(repo, "drop it")
    _git(repo, "branch", "-f", "main")  # the base no longer has it
    _change(repo, RUFF, "x.py: F401 unused\n")

    assert baseline_growth.check(repo, "main") == (0, [])


def test_uncommitted_growth_fails_until_committed_with_a_marker(repo: Path) -> None:
    (repo / BUDGET).write_text("9\n", encoding="utf-8")
    assert baseline_growth.check(repo, "main")[0] == 1


@pytest.mark.parametrize(("rel", "text"), [(POLICY, "{not json"), (BUDGET, "three\n"), (MARKER_CAP, "x = 1\n")])
def test_a_baseline_that_does_not_parse_cannot_be_checked(repo: Path, rel: str, text: str) -> None:
    _change(repo, rel, text)
    assert baseline_growth.check(repo, "main")[0] == 2


def test_a_base_that_does_not_resolve_cannot_be_checked(repo: Path) -> None:
    code, lines = baseline_growth.check(repo, "origin/no-such-branch")
    assert code == 2 and "merge-base" in lines[0]


def test_the_command_line_exit_codes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert baseline_growth.main(["--base", "main", "--repo", str(repo)]) == 0
    _change(repo, BUDGET, "4\n")
    assert baseline_growth.main(["--base", "main", "--repo", str(repo)]) == 1
    assert "FAILED: a baseline grew without a reason" in capsys.readouterr().out
    assert baseline_growth.main(["--base", "origin/no-such-branch", "--repo", str(repo)]) == 2  # never a pass
    assert "could not check" in capsys.readouterr().out


def test_every_listed_baseline_exists_in_this_checkout() -> None:
    root = Path(__file__).resolve().parents[1]
    assert [rel for rel in baseline_growth.BASELINES if not (root / rel).is_file()] == []
    for rel, kind in baseline_growth.BASELINES.items():  # each parses as its kind, and equals itself
        text = (root / rel).read_text(encoding="utf-8")
        assert baseline_growth.growth(rel, kind, text, text) == [], rel


# --------------------------------------------------------------------------- #
# verify-all's mypy-baseline-guard compares with the merge base's committed baseline, never local state (#624 B).


def _mypy_guard_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, grow: bool, marker: str = "") -> None:
    from tests._verify_skips import allow_synthetic_repo_skips
    from tests.test_cli_verify_all_tooling_unavailable import _synthetic_repo

    root = _synthetic_repo(monkeypatch, tmp_path)
    allow_synthetic_repo_skips(monkeypatch)
    _init(root)
    baseline = root / baseline_growth.MYPY_BASELINE
    baseline.parent.mkdir(parents=True)
    baseline.write_text("c.py: error: bad  [arg-type]\n", encoding="utf-8")
    _commit(root, "base")
    _git(root, "checkout", "-q", "-b", "feature")
    if grow:
        baseline.write_text("c.py: error: bad  [arg-type]\nd.py: error: worse  [misc]\n", encoding="utf-8")
    # The local count file the guard used to read (git-ignored, so absent in CI): it would call any size fine.
    (root / ".mesh" / "metrics").mkdir(parents=True)
    (root / ".mesh" / "metrics" / "mypy_baseline_count.txt").write_text("99\n", encoding="utf-8")
    _commit(root, f"change\n\n{marker}\n")
    monkeypatch.setenv("MESH_BASELINE_BASE", "main")


def _guard(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    import mesh_cli

    mesh_cli.main(["verify-all"])
    steps = {step["name"]: step for step in json.loads(capsys.readouterr().out)["steps"]}
    return steps["mypy-baseline-guard"]


def test_the_mypy_guard_fails_on_growth_since_the_merge_base(monkeypatch, tmp_path, capsys) -> None:
    _mypy_guard_repo(monkeypatch, tmp_path, grow=True)
    step = _guard(capsys)
    assert (step["ok"], step["code"]) == (False, 1)
    assert str(step["error"]).startswith("mypy baseline grew: tooling/mypy_baseline.txt grew since ")
    assert "+ d.py: error: worse" in str(step["error"])


def test_the_mypy_guard_passes_growth_with_a_marker(monkeypatch, tmp_path, capsys) -> None:
    _mypy_guard_repo(monkeypatch, tmp_path, grow=True,
                     marker="baseline-growth: tooling/mypy_baseline.txt: mypy 1.20 reports more on old code")
    step = _guard(capsys)
    assert (step["ok"], step["error"]) == (True, "")


def test_the_mypy_guard_passes_without_growth(monkeypatch, tmp_path, capsys) -> None:
    _mypy_guard_repo(monkeypatch, tmp_path, grow=False)
    step = _guard(capsys)
    assert (step["ok"], step["error"]) == (True, "")


def test_the_mypy_guard_fails_when_its_base_does_not_resolve(monkeypatch, tmp_path, capsys) -> None:
    _mypy_guard_repo(monkeypatch, tmp_path, grow=False)
    monkeypatch.setenv("MESH_BASELINE_BASE", "origin/no-such-branch")
    step = _guard(capsys)
    assert (step["ok"], step["code"]) == (False, 2)
    assert "merge-base" in str(step["error"])
