"""Flake quarantine (S1 5.3, owner decision D10): dated, issue-linked, expiring, report-only, never retried.

tests/baselines/quarantine.txt is held to ``tooling.quarantine.problems``; tests/conftest.py keeps its tests out of
every required lane and Extended's report-only quarantine job runs them. How to quarantine: docs/ci.md.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tooling import baseline_growth, quarantine, test_tiers

pytestmark = [pytest.mark.fast]

REPO = Path(__file__).resolve().parents[1]
ME = "tests/test_flake_quarantine_contract.py::test_the_contract_refuses_each_bad_entry"
TODAY = date(2026, 11, 26)


def test_every_quarantined_test_has_an_issue_an_expiry_and_exists() -> None:
    today = datetime.now(timezone.utc).date()  # (CI's clock: an entry expires on the same day everywhere)
    found = quarantine.problems(quarantine.PATH.read_text(encoding="utf-8"), today)
    assert not found, "tests/baselines/quarantine.txt (see docs/ci.md, Flake Quarantine):\n" + "\n".join(found)


@pytest.mark.parametrize(("line", "why"), [
    (f"{ME} 649 2026-11-20 2026-12-20", None),
    (f"{ME} 649 2026-11-26 2026-12-26", None),  # 30 days, added today: the longest allowed
    (f"{ME} 649 2026-10-27 2026-11-26", None),  # expires today: still valid
    (f"{ME} 2026-11-20 2026-12-20", "expected '<node id> <issue>"),  # no issue at all
    (f"{ME} #649 2026-11-20 2026-12-20", "no issue number"),
    (f"{ME} none 2026-11-20 2026-12-20", "no issue number"),
    (f"{ME} 649 2026-10-20 2026-11-19", "expired on 2026-11-19"),
    (f"{ME} 649 2026-11-20 2026-12-21", "expires 31 days after it was added, more than 30"),
    (f"{ME} 649 2026-11-27 2026-12-20", "added 2026-11-27 is in the future"),
    (f"{ME} 649 2026-11-20 20261220", "dates must be YYYY-MM-DD"),
    ("tests/test_flake_quarantine_contract.py::test_nope 649 2026-11-20 2026-12-20", "no such test"),
    ("tests/test_no_such_module.py::test_x 649 2026-11-20 2026-12-20", "no such test"),
    ("tests/test_flake_quarantine_contract.py 649 2026-11-20 2026-12-20", "no such test"),  # a module is no test
])
def test_the_contract_refuses_each_bad_entry(line: str, why: str | None) -> None:
    found = quarantine.problems(f"# a comment\n\n{line}\n", TODAY, REPO)
    assert (found == []) if why is None else (len(found) == 1 and why in found[0]), found


def test_parametrized_and_class_ids_name_their_test() -> None:
    assert quarantine.problems(f"{ME}[x-y] 649 2026-11-20 2026-12-20", TODAY, REPO) == []
    assert quarantine.problems(
        "tests/test_flake_quarantine_contract.py::Nope::test_x 649 2026-11-20 2026-12-20", TODAY, REPO)


def test_only_well_formed_entries_quarantine(tmp_path: Path) -> None:
    listing = tmp_path / "quarantine.txt"
    listing.write_text(f"# c\n{ME} 649 2026-11-20 2026-12-20\ntests/test_x.py::test_y 2026-11-20 2026-12-20\n",
                       encoding="utf-8")
    assert quarantine.quarantined(listing) == {ME}  # (the malformed one keeps running in the required lanes)
    assert quarantine.quarantined(tmp_path / "missing.txt") == set()


def test_quarantined_tests_leave_every_required_run_and_are_all_the_quarantine_lane_runs() -> None:
    from tests.conftest import _quarantine

    def run(only: bool, listed: set[str]) -> tuple[list[str], list[str]]:
        items = [SimpleNamespace(nodeid=n) for n in ("tests/a.py::t1", "tests\\b.py::t2", "tests/c.py::t3")]
        dropped: list[str] = []
        config = SimpleNamespace(getoption=lambda name, default=None: only,
                                 hook=SimpleNamespace(pytest_deselected=lambda items: dropped.extend(i.nodeid for i in items)))
        _quarantine(config, items, listed)
        return [i.nodeid for i in items], dropped

    listed = {"tests/b.py::t2"}
    assert run(False, listed) == (["tests/a.py::t1", "tests/c.py::t3"], ["tests\\b.py::t2"])
    assert run(True, listed) == (["tests\\b.py::t2"], ["tests/a.py::t1", "tests/c.py::t3"])
    assert run(False, set()) == (["tests/a.py::t1", "tests\\b.py::t2", "tests/c.py::t3"], [])
    assert run(True, set())[0] == []  # (nothing quarantined: the lane runs nothing; test_tiers says so and passes)


def test_the_quarantine_lane_is_report_only_and_the_required_lanes_keep_w_error() -> None:
    lane = test_tiers.TIERS["quarantine"]
    assert lane.pytest_args == ("--mesh-quarantined",) and lane.min_selected == 0 and not lane.verify_all
    assert [name for name, tier in test_tiers.TIERS.items() if "--mesh-quarantined" in tier.pytest_args] == ["quarantine"]
    cmd = test_tiers._pytest_cmd(mark_expr="gl", extra_args=[], xdist_jobs=None)
    assert cmd[cmd.index("-W") + 1] == "error"
    assert "addopts = -W error" in (REPO / "pytest.ini").read_text(encoding="utf-8")
    text = (REPO / ".github" / "workflows" / "extended.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
    job = text[text.index("\n  quarantine:\n"):]
    assert "python -m tooling.test_tiers quarantine" in job and "exit 0" in job  # (runs them, never fails on them)
    assert "GITHUB_STEP_SUMMARY" in job and "::warning title=quarantined test failed::" in job  # (and says so)
    assert '"tests/baselines/quarantine.txt"' in text  # (a pull request changing the list runs Extended)


def test_no_test_is_ever_retried_automatically() -> None:
    # D10: no silent retries. A re-run attempt is a person's decision, recorded in the PR or issue.
    retry = re.compile(r"rerunfailures|--reruns|pytest-retry|--retries|--force-flaky|['\"]flaky\b|nick-fields/retry", re.I)
    files = [REPO / "pyproject.toml", REPO / "pytest.ini", *sorted((REPO / ".github").rglob("*.yml"))]
    hits = [f"{p.relative_to(REPO)}: {line.strip()}" for p in files
            for line in p.read_text(encoding="utf-8").splitlines() if retry.search(line)]
    assert not hits, "automatic retries:\n" + "\n".join(hits)


def test_a_new_or_renewed_quarantine_is_baseline_growth() -> None:
    path = "tests/baselines/quarantine.txt"
    assert baseline_growth.BASELINES[path] == "lines"
    old = f"# header\n{ME} 649 2026-11-01 2026-11-30\n"
    assert baseline_growth.growth(path, "lines", old, old) == []
    assert baseline_growth.growth(path, "lines", old, "# header\n") == []  # (unquarantining shrinks it)
    assert baseline_growth.growth(path, "lines", old, f"# header\n{ME} 649 2026-11-26 2026-12-26\n") == [
        f"+ {ME} 649 2026-11-26 2026-12-26"]
