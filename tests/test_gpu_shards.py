"""#422 F13: Windows' gpu lane as two shards of whole modules, and a fan-in that is green only when together they ran
the whole gl selection exactly once.

The fan-in (``gpu (windows-latest, py3.11)`` in extended.yml) runs ``tooling/ci_shards.py check --plan gpu`` on the
shards' records and ``tooling/ci_require_jobs.py`` on their jobs. Every way the two can fail to add up to the lane must
be refused: a failed or errored test, a test missing or run twice, a missing, cancelled or incomplete shard, another
commit, another selection or plan, fewer tests than the lane's floor. A skip is an outcome (visible, listed); a test
with none is missing. The default suite's split (ci.yml) must not move.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tooling import ci_require_jobs, ci_shards, test_tiers
from tooling.ci_shards import GPU_PINNED, PINNED, check, ids_digest, module_of, scheme_digest, shard_of

pytestmark = [pytest.mark.fast]

REPO = Path(__file__).resolve().parents[1]
EXTENDED = REPO / ".github" / "workflows" / "extended.yml"
COMMIT = "c" * 40
# Two pinned gpu modules, one on each shard and each pinned away from where the hash would put it, and four hashed
# ones; the physical-GPU skip as in the real lane.
MODULES = ["tests/test_water_gpu.py", "tests/test_fire_gpu.py",
           *(f"tests/test_g{i}_gpu.py" for i in range(4))]
COLLECTED = sorted(f"{m}::test_{t}" for m in MODULES for t in ("a", "b"))
PHYSICAL = "tests/test_g0_gpu.py::test_b"  # (skipped: needs a physical GPU)


def _records(plan: str = "gpu", collected: list[str] | None = None) -> list[dict[str, Any]]:
    collected = list(COLLECTED if collected is None else collected)
    records = []
    for k in (1, 2):
        selected = [t for t in collected if shard_of(module_of(t), 2, plan) == k]
        outcomes = {t: "skipped" if t == PHYSICAL else "passed" for t in selected}
        records.append({"schema": 1, "complete": True, "shard": k, "shards": 2, "commit": COMMIT, "plan": plan,
                        "scheme_digest": scheme_digest(2, plan), "collected": collected,
                        "collected_digest": ids_digest(collected), "collection_skips": [], "selected": selected,
                        "outcomes": outcomes, "durations": {t: 1.0 for t in selected}, "subtests": {},
                        "exitstatus": 0})
    return records


def _junit(records: list[dict[str, Any]]) -> dict[int, dict[str, int] | None]:
    return {r["shard"]: {"tests": len(r["selected"]), "failures": 0, "errors": 0,
                         "skipped": sum(o == "skipped" for o in r["outcomes"].values())} for r in records}


def _check(records: list[dict[str, Any]], **kwargs: Any) -> tuple[list[str], dict[str, Any]]:
    return check(records, commit=COMMIT, junit=_junit(records), plan="gpu", **kwargs)


# --- the plans ------------------------------------------------------------------------------------------------------

def test_the_default_suites_split_is_unchanged() -> None:
    # The digests and assignment ci.yml's shards had before plans existed (57dc0c3): its records still match.
    assert scheme_digest(2) == "337c292c31a29b91f76c9955a1f83a1045f55275afbc70cf28883926d02356b1"
    assert scheme_digest(1) == "ad47ad828de6a9bbef5dcaaf10edddbf63de97873e28e8bd3fb1e9e9d597d8a6"
    assert all(shard_of(m) == k for m, k in PINNED.items())
    assert ci_shards.PLANS == {"default": PINNED, "gpu": GPU_PINNED}


def test_the_gpu_plan_pins_real_gl_modules_to_real_shards_and_has_its_own_scheme() -> None:
    for module, shard in GPU_PINNED.items():
        assert shard in (1, 2) and shard_of(module, 2, "gpu") == shard, module
        source = (REPO / module).read_text(encoding="utf-8")
        assert test_tiers.GL_ENV[0][0] in source, f"{module} isn't a gl test module"  # (its GL opt-in)
    assert not set(GPU_PINNED) & set(PINNED), "a module pinned in both plans"
    assert scheme_digest(2, "gpu") != scheme_digest(2)
    # Hashed modules land where the default plan's hash puts them: only the pins differ.
    assert shard_of("tests/test_g1_gpu.py", 2, "gpu") == shard_of("tests/test_g1_gpu.py")


def test_the_terrain_module_and_its_measurement_run_in_one_shard() -> None:
    assert shard_of("tests/test_terrain_gpu.py", 2, "gpu") == 2


# --- the fan-in's check, on gpu records -----------------------------------------------------------------------------

def test_two_complete_shards_pass_and_the_physical_gpu_skip_is_listed() -> None:
    assert all(shard_of(m, 2, "gpu") != shard_of(m) for m in MODULES[:2]), "the pins must move these two"
    records = _records()
    assert {shard_of(module_of(t), 2, "gpu") for t in COLLECTED} == {1, 2}
    problems, summary = _check(records, min_selected=len(COLLECTED))
    assert problems == []
    assert summary["plan"] == "gpu" and summary["collected"] == summary["selected"] == len(COLLECTED)
    assert summary["skipped"] == 1 and summary["skipped_tests"] == [PHYSICAL]


def _broken(change: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records, kwargs = _records(), {}
    one, two = records
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
        records = _records(plan="default")
    elif change == "a selected test without an outcome":
        del two["outcomes"][victim]
    elif change == "fewer than the lane's floor":
        kwargs["min_selected"] = len(COLLECTED) + 1
    else:
        raise AssertionError(change)
    return records, kwargs


@pytest.mark.parametrize("change", [
    "a failed gpu test", "an errored gpu test", "a missing test", "a test run twice", "a missing shard",
    "a cancelled shard", "a failed shard", "another commit", "another selection", "a module on the wrong shard",
    "the default plan's split", "a selected test without an outcome", "fewer than the lane's floor"])
def test_every_way_the_gpu_shards_fail_to_add_up_is_refused(change: str) -> None:
    records, kwargs = _broken(change)
    problems, _ = _check(records, **kwargs)
    assert problems, change


def test_a_skip_is_an_outcome_but_a_missing_outcome_is_not() -> None:
    records = _records()
    two = records[1]
    victim = next(t for t in two["selected"] if t != PHYSICAL)
    two["outcomes"][victim] = "skipped"
    problems, summary = check(records, commit=COMMIT, plan="gpu")
    assert problems == [] and victim in summary["skipped_tests"]  # (visible, never quietly passed)
    del two["outcomes"][victim]
    problems, _ = check(records, commit=COMMIT, plan="gpu")
    assert any("no outcome" in p for p in problems)


def test_the_expected_tests_are_what_the_shards_collected_not_a_fixed_count() -> None:
    grown = sorted([*COLLECTED, "tests/test_new_gpu.py::test_a"])
    assert _check(_records(collected=grown), min_selected=len(COLLECTED))[0] == []
    records = _records(collected=grown)
    for record in records:
        record["selected"] = [t for t in record["selected"] if "test_new_gpu" not in t]
        record["outcomes"] = {t: o for t, o in record["outcomes"].items() if "test_new_gpu" not in t}
    assert any("ran in no shard" in p or "its modules hold" in p for p in check(records, commit=COMMIT, plan="gpu")[0])


def test_the_cli_takes_the_plan_and_the_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records = _records()
    for record in records:
        k = record["shard"]
        (tmp_path / f"shard-{k}.json").write_text(json.dumps(record), encoding="utf-8")
        counts = _junit(records)[k] or {}
        (tmp_path / f"junit-{k}.xml").write_text(
            '<testsuites><testsuite tests="{tests}" failures="0" errors="0" skipped="{skipped}"/></testsuites>'.format(
                **counts), encoding="utf-8")
    assert ci_shards.main(["check", str(tmp_path), "--plan", "gpu", "--commit", COMMIT]) == 0
    assert ci_shards.main(["check", str(tmp_path), "--plan", "gpu", "--commit", COMMIT,
                           "--min-selected", str(len(COLLECTED) + 1)]) == 1
    assert ci_shards.main(["check", str(tmp_path), "--commit", COMMIT]) == 1  # (as the default plan: another scheme)
    assert ci_shards.main(["check", str(tmp_path / "nowhere"), "--plan", "gpu"]) == 1
    (tmp_path / "junit-2.xml").unlink()  # (a shard's JUnit report missing from its artifact)
    assert ci_shards.main(["check", str(tmp_path), "--plan", "gpu", "--commit", COMMIT]) == 1
    out = capsys.readouterr().out
    assert "fewer than the" in out and "assigned modules by another scheme" in out and "no record from shard" in out
    assert "shard 2/2: no JUnit report" in out


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
    assert rc == 0, summary["problems"]  # (1 test < min_selected 256: the fan-in holds the whole selection to it)
    text = " ".join(cmd)
    assert "-m gl" in text and "-p tooling.ci_shards_plugin --mesh-shard 2/2 --mesh-shard-plan gpu" in text
    assert re.search(r"--mesh-shard-record \S*artifacts[\\/]shards[\\/]shard-2\.json", text)
    assert re.search(r"--junitxml=\S*artifacts[\\/]shards[\\/]junit-2\.xml", text)
    assert summary["shard"] == "2/2" and summary["runner"]["before"]["error"] == "stub"


def test_the_unsharded_gpu_lane_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rc, cmd, summary = _tiers(tmp_path, monkeypatch, ["gpu"])
    assert "ci_shards_plugin" not in " ".join(cmd) and summary["shard"] is None
    assert rc == 1 and summary["problems"] == ["the lane selected 1 tests, fewer than the 256 it should"]


@pytest.mark.parametrize("argv", [["--shard", "3/2", "gpu"], ["--shard", "x", "gpu"], ["--shard", "1/2", "extended"]])
def test_a_bad_shard_or_a_lane_without_a_plan_is_refused(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        test_tiers.main(argv)
    assert raised.value.code == 2


# --- ci_require_jobs --job: the shard jobs' own conclusions ---------------------------------------------------------

SHARD_JOBS = ["gpu (windows-latest, py3.11, shard 1/2)", "gpu (windows-latest, py3.11, shard 2/2)"]


@pytest.mark.parametrize(("conclusions", "ok"), [(("success", "success"), True), (("success", "failure"), False),
                                                  (("cancelled", "success"), False), (("success", None), False)])
def test_the_fan_in_needs_both_shard_jobs_to_have_succeeded(monkeypatch: pytest.MonkeyPatch,
                                                            conclusions: tuple[str | None, ...], ok: bool) -> None:
    jobs = [{"name": n, "status": "completed", "conclusion": c, "run_attempt": 1}
            for n, c in zip(SHARD_JOBS, conclusions) if c is not None]
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_RUN_ID", "1")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setattr(ci_require_jobs, "fetch_jobs", lambda *_a, **_k: (copy.deepcopy(jobs), len(jobs)))
    real = ci_require_jobs.check
    monkeypatch.setattr(ci_require_jobs, "check", lambda fetch, required, attempt: real(fetch, required, attempt,
                                                                                         delays=(), sleep=lambda _s: None))
    argv = ["--name", "gpu (windows-latest, py3.11)", *(a for n in SHARD_JOBS for a in ("--job", n))]
    assert ci_require_jobs.main(argv) == (0 if ok else 1)


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


def test_windows_gpu_runs_as_two_shards_and_every_other_lane_as_before() -> None:
    jobs = _jobs()
    assert set(jobs) == {"dedup", "lane", "gpu-shards"}
    lane = jobs["lane"]
    legs = re.findall(r"^          - \{ (.*) \}$", lane, re.M)
    assert legs == ["os: ubuntu-latest, lane: extended", "os: windows-latest, lane: extended",
                    "os: ubuntu-latest, lane: gpu",
                    'os: windows-latest, lane: gpu, shard: "1/2", shard_index: 1',
                    'os: windows-latest, lane: gpu, shard: "2/2", shard_index: 2']
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
    # One leg: run, it's "gpu (windows-latest, py3.11)"; left out by #344's duplicate check, it's unexpanded.
    assert "    name: gpu (${{ matrix.os }}, py3.11)\n" in fanin and "        os: [windows-latest]\n" in fanin
    assert "    needs: [dedup, lane]\n" in fanin
    assert "    if: ${{ always() && needs.dedup.outputs.skip != 'true' }}\n" in fanin
    assert "permissions:\n      actions: read\n      contents: read" in fanin
    assert "pattern: lane-gpu-${{ matrix.os }}-py3.11-shard-*" in fanin
    # Its checks run whatever happened before (a failed download, a cancelled run): then they refuse. Never
    # !cancelled(), which would skip them and leave the job green on a cancelled run.
    assert fanin.count("        if: always()") == 2 and "cancelled()" not in fanin.split("steps:", 1)[1]
    assert "continue-on-error" not in fanin
    floor = test_tiers.TIERS["gpu"].min_selected
    assert (f'python3 tooling/ci_shards.py check gpu-shards --plan gpu --min-selected {floor} '
            '--commit "${{ github.sha }}"') in fanin
    assert "exit $code" in fanin and "shell: bash" in fanin
    names = re.findall(r'--job "([^"]+)"', fanin)
    assert names == [n.replace("windows-latest", "${{ matrix.os }}") for n in SHARD_JOBS]
    assert len(names) == ci_shards.SHARDS
