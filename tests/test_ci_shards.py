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
