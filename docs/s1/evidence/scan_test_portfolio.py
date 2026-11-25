"""S1-0 part C section 1: test portfolio by lane and by kind of test double (static; imports nothing from Mesh).

    py -3.13 docs/s1/evidence/scan_test_portfolio.py

Input: data/portfolio_by_file.csv, written by portfolio_plugin.py (one ``pytest --collect-only``, addopts cleared).
Each test file is classified by regex over its source (approximate, a file can be in several classes):

* real_window: constructs a GameWindow or uses one of the repo's real-window entry points (part B's regex in
  scan_behaviour_test_coverage.py, plus the headless editor, the worker processes and Studio processes), or holds a
  test with the ``gl`` marker;
* studio_real: constructs engine.studio.Studio;
* subprocess: runs a child Python / mesh_cli process;
* source_scan: parses or globs Mesh's own source (static policy tests);
* mock: unittest.mock (MagicMock/Mock/patch); specd: any spec=/spec_set=/autospec/create_autospec;
* fake_window: a window made of MagicMock/Mock/SimpleNamespace, or a hand-written *Window* class;
* none of the above: plain data/unit tests.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

REAL = re.compile(r"GameWindow\(|_game_window_live|_b01_arena|launch_editor\(|run_game\(|perf_command|trace_command|"
                  r"release_check_pipeline|_run_owned_editor|no_activate\(|_headless_editor|tests\._\w+_worker|StudioProcess|StudioDriver")
STUDIO = re.compile(r"\bStudio\(")
SUBPROC = re.compile(r"\bsubprocess\.|sys\.executable")
MOCK = re.compile(r"\bMagicMock\b|\bMock\(|\bmock\.patch|@patch\b|\bpatch\(|\bpatch\.object\(")
SPECD = re.compile(r"\bspec(_set)?=|create_autospec|autospec=True")
FAKE_WINDOW = re.compile(
    r"\b\w*window\w*\s*=\s*(MagicMock|Mock|SimpleNamespace)\(|\bwindow\s*=\s*(MagicMock|Mock|SimpleNamespace)\(|"
    r"^class \w*Window\w*\b", re.M | re.I)
MAGICMOCK_WINDOW = re.compile(r"\b\w*window\w*\s*=\s*(MagicMock|Mock)\(", re.I)
NS_WINDOW = re.compile(r"\b\w*window\w*\s*=\s*SimpleNamespace\(", re.I)
CLASS_WINDOW = re.compile(r"^class \w*Window\w*\b", re.M)
SOURCE_SCAN = re.compile(r"ast\.parse\(|rglob\(\"\*\.py\"\)|glob\(\"\*\*/\*\.py\"\)")  # tests that read Mesh's source


def main() -> int:
    rows = list(csv.DictReader((HERE / "data" / "portfolio_by_file.csv").open(encoding="utf-8")))
    total = Counter()
    kinds_files = Counter()
    kinds_tests = Counter()
    sites = Counter()
    for row in rows:
        n = int(row["tests"])
        for k, v in row.items():
            if k != "file":
                total[k] += int(v)
        src = (REPO / row["file"]).read_text(encoding="utf-8", errors="replace")
        flags = {
            # a GL test (the gpu lane) needs a real window too, even when a worker process builds it
            "real_window": bool(REAL.search(src)) or int(row["gl"]) > 0,
            "studio_real": bool(STUDIO.search(src)),
            "subprocess": bool(SUBPROC.search(src)),
            "mock": bool(MOCK.search(src)),
            "specd": bool(SPECD.search(src)),
            "fake_window": bool(FAKE_WINDOW.search(src)),
            "source_scan": bool(SOURCE_SCAN.search(src)),
        }
        sites["magicmock_window"] += len(MAGICMOCK_WINDOW.findall(src))
        sites["simplenamespace_window"] += len(NS_WINDOW.findall(src))
        sites["fake_window_class"] += len(CLASS_WINDOW.findall(src))
        sites["MagicMock("] += src.count("MagicMock(")
        sites["create_autospec/spec="] += len(SPECD.findall(src))
        for k, v in flags.items():
            if v:
                kinds_files[k] += 1
                kinds_tests[k] += n
        if flags["fake_window"] and not flags["real_window"]:
            kinds_files["fake_window_only"] += 1
            kinds_tests["fake_window_only"] += n
        if not any(flags.values()):
            kinds_files["plain"] += 1
            kinds_tests["plain"] += n
        if flags["mock"] and not flags["specd"]:
            kinds_files["mock_unspecd"] += 1
            kinds_tests["mock_unspecd"] += n
    print(f"test files collected: {len(rows)} | tests collected (addopts cleared): {total['tests']}")
    print("\nby marker (a test can carry several):")
    for k in ("fast", "integration", "slow", "e2e", "gl", "gpu_hardware", "packaging_hygiene", "builtin_behaviours",
              "unmarked", "default_skip"):
        print(f"  {k:20} {total[k]:6}  ({100 * total[k] / total['tests']:.1f}%)")
    print("\nby kind of test file (files / tests in them; a file can be in several):")
    for k in ("real_window", "studio_real", "subprocess", "source_scan", "mock", "specd", "mock_unspecd", "fake_window",
              "fake_window_only", "plain"):
        print(f"  {k:18} {kinds_files[k]:5} files  {kinds_tests[k]:6} tests  ({100 * kinds_tests[k] / total['tests']:.1f}%)")
    print("\nsites:")
    for k, v in sites.items():
        print(f"  {k:24} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
