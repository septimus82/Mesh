"""S1-0 part C: pytest collection plugin that records each collected test's lane markers (collect only, runs nothing).

    py -3.13 -m pytest -o addopts= -p no:cacheprovider -p docs.s1.evidence.portfolio_plugin --collect-only -q \
        --s1-portfolio-out docs/s1/evidence/data/portfolio_by_file.csv

Runs after tests/conftest.py's marker hook (trylast), so it sees the markers the conftest adds by node id and the
``gl`` marker it adds by capability. ``default_skip`` is pytest's own skip/skipif evaluation in the current
environment (no MESH_GL_SMOKE, so GL tests show as skipped there, as in CI's default pytest job).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import pytest

LANE_MARKS = ("fast", "integration", "slow", "e2e", "gl", "gpu_hardware", "packaging_hygiene", "builtin_behaviours")


def pytest_addoption(parser):
    parser.addoption("--s1-portfolio-out", default=None)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    out = config.getoption("--s1-portfolio-out")
    if not out:
        return
    from _pytest.skipping import evaluate_skip_marks

    rows: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in items:
        path = item.nodeid.split("::", 1)[0].replace("\\", "/")
        row = rows[path]
        row["tests"] += 1
        names = {m.name for m in item.iter_markers()}
        for mark in LANE_MARKS:
            if mark in names:
                row[mark] += 1
        if not names & {"fast", "integration", "slow", "e2e"}:
            row["unmarked"] += 1
        try:
            skipped = evaluate_skip_marks(item) is not None
        except Exception:  # a condition that can't be evaluated here
            skipped = False
        if skipped:
            row["default_skip"] += 1
    cols = ["tests", *LANE_MARKS, "unmarked", "default_skip"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", *cols])
        for path in sorted(rows):
            w.writerow([path, *(rows[path].get(c, 0) for c in cols)])
