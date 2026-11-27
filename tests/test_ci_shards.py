"""F13-C (#422): Windows' suite as two shards of whole modules, and the fan-in's proof that together they ran it once.

The check (``tooling/ci_shards.py check``) must refuse every way two shard records can fail to add up to the whole
suite: a missing, duplicate, incomplete or failed shard; another commit, collection or scheme; a test run twice, run
nowhere or without an outcome; a JUnit report that disagrees with its record. The assignment must be fixed for every
module, present or new.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tooling import ci_shards
from tooling.ci_shards import check, ids_digest, module_of, normalize, scheme_digest, shard_of

pytestmark = [pytest.mark.fast]

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
MODULES = [f"tests/test_m{i}.py" for i in range(8)]
COLLECTED = sorted([f"{m}::test_{t}" for m in MODULES for t in ("a", "b")] + ["tests/test_m0.py::test_p[<repo>/x]"])
SKIPS = ["tests/test_skipped_module.py"]


def _records() -> list[dict[str, Any]]:
    """Two good records for COLLECTED: each shard ran its modules' tests and they passed (one skipped)."""
    records = []
    for k in (1, 2):
        selected = [t for t in COLLECTED if shard_of(module_of(t)) == k]
        outcomes = {t: "passed" for t in selected}
        outcomes[selected[0]] = "skipped"
        records.append({"schema": 1, "complete": True, "shard": k, "shards": 2, "commit": COMMIT,
                        "scheme_digest": scheme_digest(2), "collected": list(COLLECTED),
                        "collected_digest": ids_digest(COLLECTED), "collection_skips": list(SKIPS),
                        "selected": selected, "outcomes": outcomes, "durations": {t: 0.5 for t in selected},
                        "exitstatus": 0})
    return records


def _junit(records: list[dict[str, Any]]) -> dict[int, dict[str, int] | None]:
    return {r["shard"]: {"tests": len(r["selected"]) + len(SKIPS), "failures": 0, "errors": 0,
                         "skipped": 1 + len(SKIPS)} for r in records}


def test_both_shards_of_the_whole_suite_pass_and_skipped_modules_count_once() -> None:
    assert {shard_of(m) for m in MODULES} == {1, 2}, "the example needs modules on both shards"
    records = _records()
    problems, summary = check(records, commit=COMMIT, junit=_junit(records))
    assert problems == []
    assert summary["collected"] == summary["selected"] == len(COLLECTED)
    assert summary["passed"] == len(COLLECTED) - 2 and summary["skipped"] == 2
    assert summary["collection_skips"] == 1


def _broken(change: str) -> list[dict[str, Any]]:
    records = _records()
    one, two = records
    moved = two["selected"][0]
    if change == "missing shard":
        records.pop()
    elif change == "duplicate shard":
        records.append(copy.deepcopy(one))
    elif change == "shard out of range":
        two["shard"] = 3
    elif change == "incomplete":
        two["complete"] = False
    elif change == "other format":
        two["schema"] = 99
    elif change == "pytest failed":
        two["exitstatus"] = 1
    elif change == "other commit":
        two["commit"] = "b" * 40
    elif change == "other scheme":
        two["scheme_digest"] = "0" * 64
    elif change == "other shard count":
        two["shards"] = 3
    elif change == "other collection":
        two["collected"] = two["collected"][:-1]
        two["collected_digest"] = ids_digest(two["collected"])
    elif change == "corrupted collection":
        two["collected_digest"] = "0" * 64
    elif change == "other collection skips":
        two["collection_skips"] = []
    elif change == "overlap":
        one["selected"].append(moved)
        one["outcomes"][moved] = "passed"
    elif change == "missing test":
        two["selected"].remove(moved)
        del two["outcomes"][moved]
    elif change == "selected twice":
        two["selected"].append(moved)
    elif change == "no outcome":
        del two["outcomes"][moved]
    elif change == "unselected outcome":
        two["outcomes"]["tests/test_other.py::test_x"] = "passed"
    elif change == "failed test":
        two["outcomes"][moved] = "failed"
    elif change == "errored test":
        two["outcomes"][moved] = "error"
    return records


CHANGES = ["missing shard", "duplicate shard", "shard out of range", "incomplete", "other format", "pytest failed",
           "other commit", "other scheme", "other shard count", "other collection", "corrupted collection",
           "other collection skips", "overlap", "missing test", "selected twice", "no outcome", "unselected outcome",
           "failed test", "errored test"]


@pytest.mark.parametrize("change", CHANGES)
def test_every_way_the_shards_fail_to_add_up_is_refused(change: str) -> None:
    records = _broken(change)
    problems, _ = check(records, commit=COMMIT, junit=_junit(records))
    assert problems, change


def test_a_whole_run_as_one_shard_is_held_to_its_floor() -> None:
    # A whole run as shard 1/1 (Linux's default suite until S1 5.9 split it, #648), checked the same way and held to the
    # suite's floor, so a collection that lost tests fails instead of passing green.
    outcomes = {t: "passed" for t in COLLECTED}
    record = {"schema": 1, "complete": True, "shard": 1, "shards": 1, "commit": COMMIT, "scheme_digest": scheme_digest(1),
              "collected": list(COLLECTED), "collected_digest": ids_digest(COLLECTED), "collection_skips": [],
              "selected": list(COLLECTED), "outcomes": outcomes, "durations": {}, "exitstatus": 0}
    junit = {1: {"tests": len(COLLECTED), "failures": 0, "errors": 0, "skipped": 0}}
    assert check([record], shards=1, commit=COMMIT, junit=junit, min_selected=len(COLLECTED))[0] == []
    problems, _ = check([record], shards=1, commit=COMMIT, junit=junit, min_selected=len(COLLECTED) + 1)
    assert problems == [f"the shards' suite holds {len(COLLECTED)} tests, fewer than the {len(COLLECTED) + 1} it should"]


def test_a_record_for_another_commit_than_this_run_is_refused() -> None:
    assert check(_records(), commit="c" * 40)[0]


def test_a_test_moved_to_the_other_shard_is_refused() -> None:
    records = _records()
    moved = records[0]["selected"].pop()
    records[1]["selected"].append(moved)
    records[1]["outcomes"][moved] = records[0]["outcomes"].pop(moved)
    problems, _ = check(records, commit=COMMIT)
    assert any("its modules hold" in line for line in problems)


@pytest.mark.parametrize("junit", ["missing", "disagreeing", "failures"])
def test_a_junit_report_missing_or_disagreeing_with_its_record_is_refused(junit: str) -> None:
    records = _records()
    reports = _junit(records)
    counts = reports[2]
    assert counts is not None
    if junit == "missing":
        reports[2] = None
    elif junit == "disagreeing":
        counts["tests"] -= 1
    else:
        counts["failures"] = 1
    problems, _ = check(records, commit=COMMIT, junit=reports)
    assert any("JUnit" in line for line in problems)


def _write(folder: Path, records: list[dict[str, Any]], *, junit: bool = True) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for record in records:
        k = record["shard"]
        (folder / f"shard-{k}.json").write_text(json.dumps(record), encoding="utf-8")
        if junit:
            skipped = sum(1 for o in record["outcomes"].values() if o == "skipped") + len(SKIPS)
            (folder / f"junit-{k}.xml").write_text(
                f'<testsuites><testsuite name="pytest" tests="{len(record["outcomes"]) + len(SKIPS)}" failures="0" '
                f'errors="0" skipped="{skipped}"/></testsuites>', encoding="utf-8")


def test_the_cli_passes_good_records_and_refuses_bad_ones(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path / "good", _records())
    assert ci_shards.main(["check", str(tmp_path / "good"), "--commit", COMMIT]) == 0
    assert "OK: the shards ran the whole suite" in capsys.readouterr().out
    _write(tmp_path / "overlap", _broken("overlap"))
    assert ci_shards.main(["check", str(tmp_path / "overlap"), "--commit", COMMIT]) == 1
    _write(tmp_path / "no-junit", _records(), junit=False)
    assert ci_shards.main(["check", str(tmp_path / "no-junit"), "--commit", COMMIT]) == 1
    assert ci_shards.main(["check", str(tmp_path / "absent"), "--commit", COMMIT]) == 1
    out = capsys.readouterr().out
    assert "no JUnit report" in out and "no record from shard(s) 1/2, 2/2" in out


def test_an_os_fan_in_refuses_a_missing_shard_and_a_suite_under_its_floor(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # S1 5.9: each OS's ``tests`` fan-in (Linux's now too) runs ``check shard-records --min-selected N --commit SHA`` on
    # its two shards' records, so a shard that left no record (missing, cancelled, its upload lost) or a suite that
    # collected under the floor turns the OS's check red.
    floor = len(COLLECTED)
    args = ["--min-selected", str(floor), "--commit", COMMIT]
    _write(tmp_path / "both", _records())
    assert ci_shards.main(["check", str(tmp_path / "both"), *args]) == 0
    _write(tmp_path / "one", _records()[:1])
    assert ci_shards.main(["check", str(tmp_path / "one"), *args]) == 1
    assert "FAILED  no record from shard(s) 2/2" in capsys.readouterr().out
    _write(tmp_path / "low", _records())
    assert ci_shards.main(["check", str(tmp_path / "low"), "--min-selected", str(floor + 1), "--commit", COMMIT]) == 1
    out = capsys.readouterr().out
    assert f"fewer than the {floor + 1} it should" in out and "REFUSED: 1 problem(s)" in out


def _plan_records(plan: str) -> list[dict[str, Any]]:
    """Good records for COLLECTED split by ``plan`` at its own count (PLAN_SHARDS), as that plan's shard jobs write them."""
    n = ci_shards.PLAN_SHARDS[plan]
    records = []
    for k in range(1, n + 1):
        selected = [t for t in COLLECTED if shard_of(module_of(t), n, plan) == k]
        records.append({"schema": 1, "complete": True, "shard": k, "shards": n, "commit": COMMIT, "plan": plan,
                        "scheme_digest": scheme_digest(n, plan), "collected": list(COLLECTED),
                        "collected_digest": ids_digest(COLLECTED), "collection_skips": list(SKIPS),
                        "selected": selected, "outcomes": {t: "passed" for t in selected},
                        "durations": {t: 0.5 for t in selected}, "exitstatus": 0})
    return records


@pytest.mark.parametrize("change", ["none", "missing 3/3", "failed shard", "under the floor", "as two shards",
                                    "as the default plan"])
def test_the_windows_fan_in_checks_three_shards_and_fails_closed(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], change: str) -> None:
    # S1 5.9 follow-up: Windows' suite runs as three shards by its own plan; its ``tests`` fan-in runs ``check
    # shard-records --plan default-windows --shards 3 --min-selected N``. A missing 3/3 (cancelled, its upload lost),
    # a failed shard, a suite under the floor, or records checked as another split all turn it red.
    records = _plan_records("default-windows")
    assert {len(r["selected"]) > 0 for r in records} == {True}, "the example needs tests on all three shards"
    floor, args = len(COLLECTED), ["--plan", "default-windows", "--shards", "3"]
    if change == "missing 3/3":
        records = records[:2]
    elif change == "failed shard":
        records[1]["outcomes"][records[1]["selected"][0]] = "failed"
        records[1]["exitstatus"] = 1
    elif change == "under the floor":
        floor += 1
    elif change == "as two shards":
        args = ["--plan", "default-windows", "--shards", "2"]
    elif change == "as the default plan":
        args = ["--shards", "3"]
    _write(tmp_path, records)
    code = ci_shards.main(["check", str(tmp_path), *args, "--min-selected", str(floor), "--commit", COMMIT])
    out = capsys.readouterr().out
    assert code == (0 if change == "none" else 1), out
    if change == "missing 3/3":
        assert "FAILED  no record from shard(s) 3/3" in out
    elif change == "failed shard":
        assert "shard 2/3: pytest exited 1" in out and "didn't pass" in out


def test_windows_own_plan_pins_real_modules_to_its_three_shards() -> None:
    pins = ci_shards.DEFAULT_WINDOWS_PINNED
    assert len(pins) == 30 and set(pins.values()) == {1, 2, 3} and ci_shards.PLAN_SHARDS["default-windows"] == 3
    for module, shard in pins.items():
        assert (ROOT / module).is_file(), f"{module} is pinned in default-windows but gone: re-measure and re-pin"
        assert shard_of(module, 3, "default-windows") == shard
    # Linux's split (the default plan, two shards) is untouched by it.
    assert scheme_digest(2) == "4c825fd905d1b1bec2b5176af6713297789c73ac4e7408eb888ecefa65a88e91"
    assert scheme_digest(3, "default-windows") == "09c4faad8abd21dae8318703f6557f0bfe7395a59a094e1e2758f81c9270cf58"


@pytest.mark.parametrize("damage", ["truncated", "not an object"])
def test_an_unreadable_record_is_refused_not_skipped(tmp_path: Path, damage: str) -> None:
    _write(tmp_path, _records())
    (tmp_path / "shard-2.json").write_text('{"schema": 1, "shard"' if damage == "truncated" else "[]", encoding="utf-8")
    assert ci_shards.main(["check", str(tmp_path), "--commit", COMMIT]) == 1


# --------------------------------------------------------------------------- #
# The assignment: fixed for every module, present or new.
# --------------------------------------------------------------------------- #

def test_the_assignment_is_fixed_by_the_module_path_alone() -> None:
    # Golden values: if these change, every module may move (bump SCHEME and say why).
    assert [shard_of(m) for m in ("tests/test_ci_require_jobs.py", "tests/test_ci_shards.py",
                                  "tests/test_zz_new_module.py", "tests/sub/test_new.py")] == [2, 2, 1, 2]
    assert shard_of("tests\\sub\\test_new.py".replace("\\", "/")) == shard_of(module_of("tests\\sub\\test_new.py::t"))
    assert all(shard_of(m, 1) == 1 for m in MODULES)
    assert {shard_of(f"tests/test_new_{i}.py", 3) for i in range(30)} == {1, 2, 3}


def test_every_pinned_module_exists_and_is_on_a_real_shard() -> None:
    assert ci_shards.PINNED, "the heaviest modules are pinned"
    for module, shard in ci_shards.PINNED.items():
        assert (ROOT / module).is_file(), module
        assert shard in range(1, ci_shards.SHARDS + 1)
        assert shard_of(module) == shard


def test_the_scheme_digest_covers_the_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    before = scheme_digest(2)
    first = next(iter(ci_shards.PINNED))
    monkeypatch.setitem(ci_shards.PINNED, first, 3 - ci_shards.PINNED[first])
    assert scheme_digest(2) != before


def test_ids_with_the_checkout_path_are_written_the_same_on_every_checkout() -> None:
    for root in ("D:\\a\\Mesh\\Mesh", "D:/a/Mesh/Mesh"):
        assert normalize("tests/test_x.py::test_p[D:\\a\\Mesh\\Mesh\\scenes\\a.json]", root) == \
            "tests/test_x.py::test_p[<repo>\\scenes\\a.json]"
    # (pytest escapes a backslash in a parametrize id as two)
    assert normalize("tests/test_x.py::test_p[D:\\\\a\\\\Mesh\\\\Mesh\\\\s.json]", "D:\\a\\Mesh\\Mesh") == \
        "tests/test_x.py::test_p[<repo>\\\\s.json]"
    assert normalize("tests/test_x.py::test_p[/home/runner/work/Mesh/Mesh/s.json]", "/home/runner/work/Mesh/Mesh") == \
        "tests/test_x.py::test_p[<repo>/s.json]"
