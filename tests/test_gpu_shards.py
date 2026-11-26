"""#422 F13: each OS's gpu lane as two shards of whole modules (Windows since F13, Linux since CI-422B, each by its own
plan), and a fan-in per OS that is green only when together its shards ran the whole gl selection exactly once.

Each fan-in (``gpu (<os>, py3.11)`` in extended.yml) runs ``tooling/ci_shards.py check --plan <plan>`` on its OS's
shards' records and ``tooling/ci_require_jobs.py`` on their jobs. Every way the two can fail to add up to the lane must
be refused: a failed or errored test, a test missing or run twice, a missing, cancelled or incomplete shard, another
commit, another selection or plan, fewer tests than the lane's floor. A skip is an outcome (visible, listed); a test
with none is missing. The default suite's split (ci.yml) must not move.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tooling import ci_require_jobs, ci_shards, test_tiers
from tooling.ci_shards import (
    GPU_LINUX_PINNED,
    GPU_PINNED,
    PINNED,
    PLAN_SHARDS,
    check,
    ids_digest,
    module_of,
    scheme_digest,
    shard_of,
)

pytestmark = [pytest.mark.fast]

REPO = Path(__file__).resolve().parents[1]
EXTENDED = REPO / ".github" / "workflows" / "extended.yml"
COMMIT = "c" * 40
# Two pinned gpu modules, one on each shard and each pinned away from where the hash would put it, and four hashed
# ones; the physical-GPU skip as in the real lane.
MODULES = ["tests/test_water_gpu.py", "tests/test_hd2d_starter_gpu.py",
           *(f"tests/test_g{i}_gpu.py" for i in range(4))]
COLLECTED = sorted(f"{m}::test_{t}" for m in MODULES for t in ("a", "b"))
PHYSICAL = "tests/test_g0_gpu.py::test_b"  # (skipped: needs a physical GPU)
GPU_PLANS = ("gpu", "gpu-linux")  # (Windows', Linux's: every fan-in check below holds for both)
# S1 5.9: Windows' gpu lane runs as three shards, Linux's as two; each plan's pins are for its own count.
assert PLAN_SHARDS["gpu"] == 3 and PLAN_SHARDS["gpu-linux"] == 2


def _records(plan: str = "gpu", collected: list[str] | None = None, shards: int | None = None) -> list[dict[str, Any]]:
    collected = list(COLLECTED if collected is None else collected)
    n = shards or PLAN_SHARDS[plan]
    records = []
    for k in range(1, n + 1):
        selected = [t for t in collected if shard_of(module_of(t), n, plan) == k]
        outcomes = {t: "skipped" if t == PHYSICAL else "passed" for t in selected}
        records.append({"schema": 1, "complete": True, "shard": k, "shards": n, "commit": COMMIT, "plan": plan,
                        "scheme_digest": scheme_digest(n, plan), "collected": collected,
                        "collected_digest": ids_digest(collected), "collection_skips": [], "selected": selected,
                        "outcomes": outcomes, "durations": {t: 1.0 for t in selected}, "subtests": {},
                        "exitstatus": 0})
    return records


def _junit(records: list[dict[str, Any]]) -> dict[int, dict[str, int] | None]:
    return {r["shard"]: {"tests": len(r["selected"]), "failures": 0, "errors": 0,
                         "skipped": sum(o == "skipped" for o in r["outcomes"].values())} for r in records}


def _check(records: list[dict[str, Any]], plan: str = "gpu", **kwargs: Any) -> tuple[list[str], dict[str, Any]]:
    return check(records, shards=PLAN_SHARDS[plan], commit=COMMIT, junit=_junit(records), plan=plan, **kwargs)


# --- the plans ------------------------------------------------------------------------------------------------------

def test_the_default_suites_split_is_the_s1_5_9_one() -> None:
    # The digests and assignment ci.yml's shards (both OSes) have since S1 5.9's re-pin (scheme f13c-2); a change to
    # either moves modules between shards, so it is made on purpose, from measured timings, with these updated.
    assert scheme_digest(2) == "4c825fd905d1b1bec2b5176af6713297789c73ac4e7408eb888ecefa65a88e91"
    assert scheme_digest(1) == "d8c2ec23482332827f2a0a7032e9676ed92b3b75c23984427d9a642e6ca950b5"
    assert all(shard_of(m) == k for m, k in PINNED.items())
    assert ci_shards.PLANS == {"default": PINNED, "default-windows": ci_shards.DEFAULT_WINDOWS_PINNED, "gpu": GPU_PINNED,
                               "gpu-linux": GPU_LINUX_PINNED}


def test_windows_gpu_split_is_the_s1_5_9_one() -> None:
    # S1 5.9: Windows' gpu lane as three shards, pinned from 6 push runs' timings (30 heaviest modules plus the 5.7 (ii)
    # e2e leg); Linux's two keep their pins (plus the e2e leg).
    assert scheme_digest(3, "gpu") == "32fb46efc0d9ff8e41e2792e9c22e568579fa4378133870f686b35289a64bc20"
    assert scheme_digest(2, "gpu-linux") == "2eac12d62cc1713bc65af2cf99091929e8bb7383ff7a25141848dae21b909fa2"
    assert len(GPU_PINNED) == 31 and set(GPU_PINNED.values()) == {1, 2, 3}
    assert GPU_PINNED["tests/test_terrain_gpu.py"] == 2


def test_a_plans_pins_apply_only_at_its_own_shard_count() -> None:
    # Split any other way (a stale workflow, a wrong --shards), every module goes by the hash and the scheme digest
    # says so, so records of another count never pass as this plan's.
    for plan, pins in ci_shards.PLANS.items():
        n = PLAN_SHARDS[plan]
        assert all(shard_of(m, n, plan) == k for m, k in pins.items())
        other = 2 if n == 3 else 3
        assert all(shard_of(m, other, plan) == int(hashlib.sha256(m.encode()).hexdigest(), 16) % other + 1 for m in pins)
        assert scheme_digest(other, plan) != scheme_digest(n, plan)
    assert scheme_digest(2, "gpu") != scheme_digest(3, "gpu")


@pytest.mark.parametrize("plan", GPU_PLANS)
def test_a_gpu_plan_pins_real_gl_modules_to_real_shards_and_has_its_own_scheme(plan: str) -> None:
    pins = ci_shards.PLANS[plan]
    n = PLAN_SHARDS[plan]
    for module, shard in pins.items():
        assert shard in range(1, n + 1) and shard_of(module, n, plan) == shard, module
        assert (REPO / module).is_file(), f"{module} is pinned in the {plan} plan but gone: re-measure and re-pin"
        source = (REPO / module).read_text(encoding="utf-8")
        assert test_tiers.GL_ENV[0][0] in source, f"{module} isn't a gl test module"  # (its GL opt-in)
    assert not set(pins) & set(PINNED), "a module pinned in a gpu plan and the default suite's"
    assert len({scheme_digest(2), scheme_digest(3, "gpu"), scheme_digest(2, "gpu-linux")}) == 3
    # Hashed modules land where the hash puts them at the plan's count: only the pins differ.
    assert shard_of("tests/test_g1_gpu.py", n, plan) == shard_of("tests/test_g1_gpu.py", n, "default")


def _gl_modules() -> list[str]:
    opt_in = test_tiers.GL_ENV[0][0]
    return sorted(f"tests/{p.name}" for p in (REPO / "tests").glob("test_*.py")
                  if opt_in in p.read_text(encoding="utf-8", errors="replace"))


@pytest.mark.parametrize("plan", GPU_PLANS)
def test_every_gl_module_today_and_any_new_one_lands_in_exactly_one_shard(plan: str) -> None:
    # The fan-in proves it on each run's real collection (every shard collects the whole selection); this holds the
    # plan to it without GL: the two shards' modules partition every module that opts into GL, neither shard is empty,
    # and a module no plan names (a new one) is placed by the hash, never dropped.
    modules = _gl_modules()
    assert len(modules) >= 60, "the gl modules weren't found"
    n = PLAN_SHARDS[plan]
    parts = [{m for m in modules if shard_of(m, n, plan) == k} for k in range(1, n + 1)]
    assert set().union(*parts) == set(modules) and sum(map(len, parts)) == len(modules) and all(parts)
    assert shard_of("tests/test_brand_new_gpu.py", n, plan) in range(1, n + 1)


def test_linux_s_plan_comes_from_linux_s_timings_not_windows() -> None:
    # Each OS's pins come from its own lane's timings: Linux's split differs from Windows' (terrain and lighting
    # controls share Linux's shard 1, while Windows' plan separates them).
    assert GPU_LINUX_PINNED["tests/test_hd2d_lighting_controls_gpu.py"] == GPU_LINUX_PINNED["tests/test_terrain_gpu.py"]
    assert GPU_PINNED["tests/test_hd2d_lighting_controls_gpu.py"] != GPU_PINNED["tests/test_terrain_gpu.py"]
    assert len(GPU_LINUX_PINNED) == 13 and scheme_digest(2, "gpu-linux") != scheme_digest(2, "gpu")


# S1 5.9 (roadmap 5.9, 5.7 ii): the HD-2D e2e leg (gl tests in the e2e module) runs in each OS's lightest gpu shard:
# Windows' 2 of 3 (1,172 s against 1,175 and 1,177 s without it, on the measured runs), Linux's 2 (816 s against 913 s).
@pytest.mark.parametrize(("plan", "shard"), [("gpu", 2), ("gpu-linux", 2)])
def test_the_hd2d_e2e_leg_runs_in_the_lightest_gpu_shard(plan: str, shard: int) -> None:
    assert shard_of("tests/test_e2e_creator_workflow.py", PLAN_SHARDS[plan], plan) == shard


@pytest.mark.parametrize(("plan", "shard"), [("gpu", 2), ("gpu-linux", 1)])
def test_the_terrain_module_and_its_measurement_run_in_one_shard(plan: str, shard: int) -> None:
    # (its gated stroke, zero-reload guard, report-only measurements and fault-detection test, all in one module)
    assert shard_of("tests/test_terrain_gpu.py", PLAN_SHARDS[plan], plan) == shard


# --- the fan-in's check, on gpu records -----------------------------------------------------------------------------

@pytest.mark.parametrize("plan", GPU_PLANS)
def test_complete_shards_pass_and_the_physical_gpu_skip_is_listed(plan: str) -> None:
    n = PLAN_SHARDS[plan]
    assert all(shard_of(m, n, plan) != shard_of(m, n, "default") for m in MODULES[:2]), "the pins must move these two"
    records = _records(plan)
    assert {shard_of(module_of(t), n, plan) for t in COLLECTED} == set(range(1, n + 1))
    problems, summary = _check(records, plan, min_selected=len(COLLECTED))
    assert problems == []
    assert summary["plan"] == plan and summary["collected"] == summary["selected"] == len(COLLECTED)
    assert summary["skipped"] == 1 and summary["skipped_tests"] == [PHYSICAL]


def _broken(change: str, plan: str = "gpu") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records, kwargs = _records(plan), {}
    one, two = records[0], records[-1]  # (the first and the last shard: 2/2 on Linux, 3/3 on Windows)
    victim = two["selected"][0]
    if change == "a failed gpu test":
        two["outcomes"][victim] = "failed"
        two["exitstatus"] = 1
    elif change == "an errored gpu test":
        two["outcomes"][victim] = "error"
        two["exitstatus"] = 1
    elif change == "a missing test":
        two["selected"].remove(victim)
        del two["outcomes"][victim]
    elif change == "a test run twice":
        one["selected"].append(victim)
        one["outcomes"][victim] = "passed"
    elif change == "a missing shard":
        records.pop()
    elif change == "a cancelled shard":
        two.update(complete=False, exitstatus=None)
    elif change == "a failed shard":
        two["exitstatus"] = 2
    elif change == "another commit":
        two["commit"] = "d" * 40
    elif change == "another selection":
        two["collected"] = two["collected"][:-1]
        two["collected_digest"] = ids_digest(two["collected"])
    elif change == "a module on the wrong shard":
        moved = [t for t in two["selected"] if module_of(t) == module_of(victim)]
        for t in moved:
            two["selected"].remove(t)
            one["selected"].append(t)
            one["outcomes"][t] = two["outcomes"].pop(t)
    elif change == "the default plan's split":
        records = _records(plan="default", shards=PLAN_SHARDS[plan])
    elif change == "a selected test without an outcome":
        del two["outcomes"][victim]
    elif change == "fewer than the lane's floor":
        kwargs["min_selected"] = len(COLLECTED) + 1
    elif change == "an empty shard":
        two.update(selected=[], outcomes={}, durations={})
    elif change == "an empty collection":
        records = _records(plan, collected=[])
        kwargs["min_selected"] = test_tiers.TIERS["gpu"].min_selected
    elif change == "two records for one shard":
        records.append(copy.deepcopy(two))
    elif change == "the other OS's plan":  # (stale or crossed records: Windows' checked as Linux's, or back)
        records = _records(plan="gpu-linux" if plan == "gpu" else "gpu")
    elif change == "the other OS's stale scheme":  # (a record written before its plan was re-pinned)
        other = "gpu-linux" if plan == "gpu" else "gpu"
        two["scheme_digest"] = scheme_digest(PLAN_SHARDS[other], other)
    else:
        raise AssertionError(change)
    return records, kwargs


@pytest.mark.parametrize("plan", GPU_PLANS)
@pytest.mark.parametrize("change", [
    "a failed gpu test", "an errored gpu test", "a missing test", "a test run twice", "a missing shard",
    "a cancelled shard", "a failed shard", "another commit", "another selection", "a module on the wrong shard",
    "the default plan's split", "a selected test without an outcome", "fewer than the lane's floor",
    "an empty shard", "an empty collection", "two records for one shard", "the other OS's plan",
    "the other OS's stale scheme"])
def test_every_way_the_gpu_shards_fail_to_add_up_is_refused(change: str, plan: str) -> None:
    records, kwargs = _broken(change, plan)
    problems, _ = _check(records, plan, **kwargs)
    assert problems, change


@pytest.mark.parametrize("plan", GPU_PLANS)
def test_a_missing_last_shard_turns_the_gpu_fan_in_red(plan: str) -> None:
    # S1 5.9: Windows' fan-in checks three records (--shards 3): with shard 3/3's missing (cancelled, its upload lost),
    # the check refuses, naming it; Linux's the same with 2/2. The other shards alone never pass as the whole lane.
    n = PLAN_SHARDS[plan]
    records = _records(plan)
    assert _check(records, plan, min_selected=len(COLLECTED))[0] == []
    problems, _ = _check(records[:-1], plan, min_selected=len(COLLECTED))
    assert problems == [f"no record from shard(s) {n}/{n}: missing, cancelled or stopped before it finished"]


def test_a_skip_is_an_outcome_but_a_missing_outcome_is_not() -> None:
    records = _records()
    two = next(r for r in records if any(t != PHYSICAL for t in r["selected"]))
    victim = next(t for t in two["selected"] if t != PHYSICAL)
    two["outcomes"][victim] = "skipped"
    problems, summary = check(records, shards=3, commit=COMMIT, plan="gpu")
    assert problems == [] and victim in summary["skipped_tests"]  # (visible, never quietly passed)
    del two["outcomes"][victim]
    problems, _ = check(records, shards=3, commit=COMMIT, plan="gpu")
    assert any("no outcome" in p for p in problems)


def test_the_expected_tests_are_what_the_shards_collected_not_a_fixed_count() -> None:
    grown = sorted([*COLLECTED, "tests/test_new_gpu.py::test_a"])
    assert _check(_records(collected=grown), min_selected=len(COLLECTED))[0] == []
    records = _records(collected=grown)
    for record in records:
        record["selected"] = [t for t in record["selected"] if "test_new_gpu" not in t]
        record["outcomes"] = {t: o for t, o in record["outcomes"].items() if "test_new_gpu" not in t}
    assert any("ran in no shard" in p or "its modules hold" in p
               for p in check(records, shards=3, commit=COMMIT, plan="gpu")[0])


def test_the_cli_takes_the_plan_and_the_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records = _records()
    for record in records:
        k = record["shard"]
        (tmp_path / f"shard-{k}.json").write_text(json.dumps(record), encoding="utf-8")
        counts = _junit(records)[k] or {}
        (tmp_path / f"junit-{k}.xml").write_text(
            '<testsuites><testsuite tests="{tests}" failures="0" errors="0" skipped="{skipped}"/></testsuites>'.format(
                **counts), encoding="utf-8")
    gpu = ["--plan", "gpu", "--shards", "3"]
    assert ci_shards.main(["check", str(tmp_path), *gpu, "--commit", COMMIT]) == 0
    assert ci_shards.main(["check", str(tmp_path), *gpu, "--commit", COMMIT,
                           "--min-selected", str(len(COLLECTED) + 1)]) == 1
    assert ci_shards.main(["check", str(tmp_path), "--shards", "3", "--commit", COMMIT]) == 1  # (the default plan's scheme)
    assert ci_shards.main(["check", str(tmp_path), "--plan", "gpu", "--commit", COMMIT]) == 1  # (as two shards)
    assert ci_shards.main(["check", str(tmp_path / "nowhere"), *gpu]) == 1
    (tmp_path / "junit-2.xml").unlink()  # (a shard's JUnit report missing from its artifact)
    assert ci_shards.main(["check", str(tmp_path), *gpu, "--commit", COMMIT]) == 1
    out = capsys.readouterr().out
    assert "fewer than the" in out and "assigned modules by another scheme" in out and "no record from shard" in out
    assert "shard 2/3: no JUnit report" in out


# --- test_tiers --shard ---------------------------------------------------------------------------------------------

def _tiers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> tuple[int, list[str], dict[str, Any]]:
    monkeypatch.setattr(test_tiers, "__file__", str(tmp_path / "tooling" / "test_tiers.py"))
    monkeypatch.setattr(test_tiers, "runner_calibration", lambda: {"cpu": "x", "complete": False, "error": "stub"})
    monkeypatch.setattr(test_tiers, "gl_renderer", lambda: "llvmpipe (LLVM 22.1.1, 256 bits) | 4.5 Mesa 26.0.3")
    seen: list[str] = []

    def pytest_run(cmd: list[str], **_k: Any) -> int:
        seen[:] = cmd
        junit = Path(next(a.split("=", 1)[1] for a in cmd if a.startswith("--junitxml=")))
        junit.parent.mkdir(parents=True, exist_ok=True)
        junit.write_text('<testsuites><testsuite tests="1"><testcase classname="tests.test_g0_gpu" name="test_a"/>'
                         "</testsuite></testsuites>", encoding="utf-8")
        return 0

    monkeypatch.setattr(test_tiers, "_run", pytest_run)
    rc = test_tiers.main(argv)
    summary = json.loads((tmp_path / "artifacts" / "pytest_gpu_summary.json").read_text(encoding="utf-8"))
    return rc, seen, summary


def test_a_gpu_shard_runs_the_plugin_by_the_gpu_plan_and_isnt_held_to_the_whole_floor(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rc, cmd, summary = _tiers(tmp_path, monkeypatch, ["--shard", "2/2", "gpu"])
    assert rc == 0, summary["problems"]  # (1 test < min_selected 605: the fan-in holds the whole selection to it)
    text = " ".join(cmd)
    assert "-m gl" in text and "-p tooling.ci_shards_plugin --mesh-shard 2/2 --mesh-shard-plan gpu" in text
    assert re.search(r"--mesh-shard-record \S*artifacts[\\/]shards[\\/]shard-2\.json", text)
    assert re.search(r"--junitxml=\S*artifacts[\\/]shards[\\/]junit-2\.xml", text)
    assert summary["shard"] == "2/2" and summary["runner"]["before"]["error"] == "stub"


def test_the_unsharded_gpu_lane_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rc, cmd, summary = _tiers(tmp_path, monkeypatch, ["gpu"])
    assert "ci_shards_plugin" not in " ".join(cmd) and summary["shard"] is None
    assert rc == 1 and summary["problems"] == ["the lane selected 1 tests, fewer than the 605 it should"]


def test_a_linux_gpu_shard_runs_by_linux_s_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rc, cmd, summary = _tiers(tmp_path, monkeypatch, ["--shard", "1/2", "--shard-plan", "gpu-linux", "gpu"])
    assert rc == 0, summary["problems"]
    text = " ".join(cmd)
    assert "-m gl" in text and "-p tooling.ci_shards_plugin --mesh-shard 1/2 --mesh-shard-plan gpu-linux" in text
    assert re.search(r"--mesh-shard-record \S*artifacts[\\/]shards[\\/]shard-1\.json", text)
    assert summary["shard"] == "1/2"


@pytest.mark.parametrize("argv", [["--shard", "3/2", "gpu"], ["--shard", "x", "gpu"], ["--shard", "1/2", "extended"],
                                  ["--shard-plan", "gpu-linux", "gpu"],  # (a plan without a shard)
                                  ["--shard", "1/2", "--shard-plan", "default", "gpu"],  # (another lane's plan)
                                  ["--shard", "1/2", "--shard-plan", "gpu-mac", "gpu"]])  # (no such plan)
def test_a_bad_shard_or_a_lane_without_a_plan_is_refused(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        test_tiers.main(argv)
    assert raised.value.code == 2


# --- ci_require_jobs --job: the shard jobs' own conclusions ---------------------------------------------------------

OSES = ("windows-latest", "ubuntu-latest")
OS_PLAN = {"windows-latest": "gpu", "ubuntu-latest": "gpu-linux"}


def _shard_jobs(os_name: str) -> list[str]:
    """An OS's gpu shard job names, as its fan-in builds them from its matrix leg's ``shards`` (S1 5.9: 3 on Windows)."""
    n = PLAN_SHARDS[OS_PLAN[os_name]]
    return [f"gpu ({os_name}, py3.11, shard {k}/{n})" for k in range(1, n + 1)]


SHARD_JOBS = _shard_jobs("windows-latest")


@pytest.mark.parametrize("os_name", OSES)
@pytest.mark.parametrize("which", ["first", "last"])  # (Windows' last is 3/3)
@pytest.mark.parametrize(("bad", "ok"), [("success", True), ("failure", False), ("cancelled", False),
                                         (None, False), ("skipped", False), ("timed_out", False)])
def test_the_fan_in_needs_every_shard_job_to_have_succeeded(monkeypatch: pytest.MonkeyPatch, os_name: str, which: str,
                                                            bad: str | None, ok: bool) -> None:
    names = _shard_jobs(os_name)
    victim = names[0] if which == "first" else names[-1]
    # (the other OS's shards all succeeded: they must never stand in for this OS's; None: the job is missing)
    other = [{"name": n, "status": "completed", "conclusion": "success", "run_attempt": 1}
             for n in _shard_jobs(next(o for o in OSES if o != os_name))]
    jobs = other + [{"name": n, "status": "completed", "conclusion": bad if n == victim else "success", "run_attempt": 1}
                    for n in names if n != victim or bad is not None]
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_RUN_ID", "1")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setattr(ci_require_jobs, "fetch_jobs", lambda *_a, **_k: (copy.deepcopy(jobs), len(jobs)))
    real = ci_require_jobs.check
    monkeypatch.delenv("NEEDS_RESULTS", raising=False)  # (only the jobs list decides here)
    monkeypatch.setattr(ci_require_jobs, "check", lambda *a, **k: real(*a, **k, delays=(), sleep=lambda _s: None))
    argv = ["--name", f"gpu ({os_name}, py3.11)", *(a for n in names for a in ("--job", n))]
    assert ci_require_jobs.main(argv) == (0 if ok else 1)


@pytest.mark.parametrize(("listed", "needs", "ok"), [
    ("in_progress", '["skipped", "failure"]', False),  # (stale list, and needs: doesn't vouch: never success)
    ("queued", "", False),  # (no needs: word at all)
    ("in_progress", "not json", False),
    ("in_progress", '["success", "success"]', True)])  # (#469: the engine vouches every needed job succeeded)
def test_a_stale_or_unreadable_jobs_list_is_never_taken_as_success(listed: str, needs: str, ok: bool) -> None:
    names = _shard_jobs("ubuntu-latest")
    jobs = [{"name": names[0], "status": "completed", "conclusion": "success", "run_attempt": 1},
            {"name": names[1], "status": listed, "conclusion": None, "run_attempt": 1}]
    passed, lines = ci_require_jobs.check(lambda: (copy.deepcopy(jobs), len(jobs)), names, 1,
                                          needs_ok=ci_require_jobs.needs_succeeded(needs), delays=(0, 0),
                                          sleep=lambda _s: None, log=lambda _l: None)
    assert passed is ok, lines


def test_jobs_by_name_or_by_os_not_both() -> None:
    with pytest.raises(SystemExit):
        ci_require_jobs.main(["--job", "x", "--os", "windows-latest", "--python", "3.11"])
    with pytest.raises(SystemExit):
        ci_require_jobs.main([])


# --- the workflow ---------------------------------------------------------------------------------------------------

def _jobs() -> dict[str, str]:
    text = EXTENDED.read_text(encoding="utf-8").replace("\r\n", "\n")
    body = text[text.index("\njobs:\n") + len("\njobs:\n"):]
    parts = re.split(r"^  ([\w-]+):\n", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def test_each_os_s_gpu_lane_runs_as_its_plan_s_shards_and_every_other_lane_as_before() -> None:
    jobs = _jobs()
    assert set(jobs) == {"dedup", "lane", "gpu-shards", "quarantine"}  # (quarantine: D10, report-only)
    lane = jobs["lane"]
    legs = re.findall(r"^          - \{ (.*) \}$", lane, re.M)
    assert legs == ["os: ubuntu-latest, lane: extended", "os: windows-latest, lane: extended",
                    'os: ubuntu-latest, lane: gpu, shard: "1/2", shard_index: 1, plan: gpu-linux',
                    'os: ubuntu-latest, lane: gpu, shard: "2/2", shard_index: 2, plan: gpu-linux',
                    # (Windows' legs: the lane's own plan, gpu, as three shards since S1 5.9)
                    'os: windows-latest, lane: gpu, shard: "1/3", shard_index: 1',
                    'os: windows-latest, lane: gpu, shard: "2/3", shard_index: 2',
                    'os: windows-latest, lane: gpu, shard: "3/3", shard_index: 3']
    assert 'if ("${{ matrix.plan }}") { $shard += @("--shard-plan", "${{ matrix.plan }}") }' in lane
    assert "xvfb-run -a python -m tooling.test_tiers @shard ${{ matrix.lane }}" in lane  # (each Linux shard, own Xvfb)
    # Unsharded legs keep their names; shards are "gpu (windows-latest, py3.11, shard K/2)".
    assert ("    name: ${{ matrix.lane }} (${{ matrix.os }}, py3.11${{ matrix.shard && "
            "format(', shard {0}', matrix.shard) || '' }})\n") in lane
    assert "    needs: dedup\n    # " in lane and "    if: ${{ !cancelled() && needs.dedup.outputs.skip != 'true' }}\n" in lane
    assert '$shard = @(); if ("${{ matrix.shard }}") { $shard = @("--shard", "${{ matrix.shard }}") }' in lane
    assert "python -m tooling.test_tiers @shard ${{ matrix.lane }}" in lane
    # Both shards get the desktop contract (it's per lane and OS) and upload their record, replacing a re-run's.
    assert "if: runner.os == 'Windows' && matrix.lane == 'gpu'" in lane
    upload = lane[lane.index("- name: Upload lane reports"):]
    assert ("name: lane-${{ matrix.lane }}-${{ matrix.os }}-py3.11${{ matrix.shard && "
            "format('-shard-{0}', matrix.shard_index) || '' }}") in upload
    assert re.search(r"^          overwrite: true\b", upload, re.M), "a re-run attempt must replace its record"
    assert re.search(r"^            artifacts/shards/$", upload, re.M) and "        if: always()\n" in upload


def test_the_fan_in_keeps_the_lanes_check_name_and_fails_closed() -> None:
    fanin = _jobs()["gpu-shards"]
    # One leg per OS: run, it's "gpu (<os>, py3.11)", the name each lane's check had (Linux's unsharded lane until
    # CI-422B); left out by #344's duplicate check, it's unexpanded. Not fail-fast: one OS's red never cancels the other.
    assert "    name: gpu (${{ matrix.os }}, py3.11)\n" in fanin
    fanin_legs = re.findall(r"^          - \{ (.*) \}$", fanin, re.M)
    assert fanin_legs == ["os: windows-latest, plan: gpu, shards: 3", "os: ubuntu-latest, plan: gpu-linux, shards: 2"]
    # Each leg's count is its plan's, and the lane runs exactly that many shards of it on that OS.
    lane_counts = Counter(re.findall(r'^          - \{ os: ([\w-]+), lane: gpu, shard: "\d/(\d)"', _jobs()["lane"], re.M))
    for leg in fanin_legs:
        os_name, plan, shards = (part.split(": ")[1] for part in leg.split(", "))
        assert int(shards) == PLAN_SHARDS[plan] and lane_counts[(os_name, shards)] == int(shards)
    assert "    strategy:\n      fail-fast: false\n" in fanin
    # Each fan-in leg checks by the plan its OS's shards ran (a mismatch would refuse every record: another scheme).
    lane_plans = {os: plan or "gpu" for os, plan in re.findall(
        r'^          - \{ os: ([\w-]+), lane: gpu, shard: "\d/\d", shard_index: \d(?:, plan: ([\w-]+))? \}$',
        _jobs()["lane"], re.M)}
    assert lane_plans == {leg.split(",")[0].split(": ")[1]: leg.split("plan: ")[1].split(",")[0] for leg in fanin_legs}
    assert set(lane_plans.values()) <= set(ci_shards.PLANS)
    assert "    needs: [dedup, lane]\n" in fanin
    assert "    if: ${{ always() && needs.dedup.outputs.skip != 'true' }}\n" in fanin
    assert "permissions:\n      actions: read\n      contents: read" in fanin
    assert "pattern: lane-gpu-${{ matrix.os }}-py3.11-shard-*" in fanin
    # Its checks run whatever happened before (a failed download, a cancelled run): then they refuse. Never
    # !cancelled(), which would skip them and leave the job green on a cancelled run.
    assert fanin.count("        if: always()") == 2 and "cancelled()" not in fanin.split("steps:", 1)[1]
    assert "continue-on-error" not in fanin
    floor = test_tiers.TIERS["gpu"].min_selected
    assert ('python3 tooling/ci_shards.py check gpu-shards --plan ${{ matrix.plan }} --shards ${{ matrix.shards }} '
            f'--min-selected {floor} --commit "${{{{ github.sha }}}}"') in fanin
    assert "exit $code" in fanin and "shell: bash" in fanin
    # The engine's needs: results stand in for a stale jobs list (ci_require_jobs.observe): "success" for lane must mean
    # every leg succeeded, so no leg may fail softly.
    assert "NEEDS_RESULTS: ${{ toJSON(needs.*.result) }}" in fanin
    assert "continue-on-error" not in _jobs()["lane"]
    # It requires one job per shard of its leg's count, by the names the lane's shards report (a missing 3/3 is red).
    assert ('jobs=(); for k in $(seq 1 ${{ matrix.shards }}); do jobs+=(--job "gpu (${{ matrix.os }}, py3.11, shard '
            '$k/${{ matrix.shards }})"); done\n') in fanin
    assert 'python3 tooling/ci_require_jobs.py --name "gpu (${{ matrix.os }}, py3.11)" "${jobs[@]}"' in fanin
