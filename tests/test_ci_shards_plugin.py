"""F13-C (#422): the shard plugin, run for real. Two shards of a small suite each run their own modules, record
them, and together pass the fan-in's check; a shard stopped part way, or one that ran the wrong modules, doesn't."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tooling import ci_shards

pytestmark = [pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[1]
SUITE = {
    # (test_m0..m5 land on both shards: see test_ci_shards' golden assignment)
    **{f"tests/test_m{i}.py": "def test_a():\n    pass\n\ndef test_b():\n    pass\n" for i in range(6)},
    "tests/test_m0.py": "import pathlib, pytest\n\n@pytest.mark.parametrize('p', [str(pathlib.Path(__file__).parent)])\n"
                        "def test_path(p):\n    pass\n\ndef test_skip():\n    pytest.skip('skipped')\n",
    "tests/test_m3.py": "import pytest\n\ndef test_a(subtests):\n    for i in range(3):\n        with subtests.test(i=i):\n"
                        "            if i == 2:\n                pytest.skip('one skipped subtest')\n",
    "tests/test_skipped_module.py": "import pytest\npytest.skip('whole module', allow_module_level=True)\n",
    "tests/test_slow.py": "import pytest\n\n@pytest.mark.slow\ndef test_slow():\n    pass\n",
}


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    for name, text in SUITE.items():
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text(text, encoding="utf-8")
    (project / "pytest.ini").write_text("[pytest]\ntestpaths = tests\nmarkers =\n    slow: slow\n"
                                        "addopts = -m \"not slow\"\n", encoding="utf-8")
    return project


def _run(project: Path, out: Path, shard: str, *extra: str) -> subprocess.CompletedProcess[str]:
    k = shard.split("/")[0]
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tooling.ci_shards_plugin",
         "--mesh-shard", shard, "--mesh-shard-record", str(out / f"shard-{k}.json"),
         f"--junitxml={out / f'junit-{k}.xml'}", *extra],
        cwd=project, env=env, capture_output=True, text=True, timeout=120, check=False)


def test_two_real_shards_run_the_whole_suite_once(tmp_path: Path) -> None:
    project, out = _project(tmp_path), tmp_path / "records"
    for shard in ("1/2", "2/2"):
        proc = _run(project, out, shard)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    whole = _run(project, tmp_path / "whole", "1/1")
    assert whole.returncode == 0
    records = [json.loads((out / f"shard-{k}.json").read_text(encoding="utf-8")) for k in (1, 2)]
    unsharded = json.loads((tmp_path / "whole" / "shard-1.json").read_text(encoding="utf-8"))
    # Each collected the same suite (the slow test deselected, the path in a test id written <repo>) ...
    assert records[0]["collected"] == records[1]["collected"] == unsharded["selected"]
    assert any(t.startswith("tests/test_m0.py::test_path[<repo>") for t in unsharded["selected"])
    assert not any(tmp_path.name in t for r in (*records, unsharded) for t in r["collected"] + r["selected"])
    assert not any("slow" in t for t in unsharded["collected"])
    assert records[0]["collection_skips"] == ["tests/test_skipped_module.py"]
    # (JUnit counts subtests as tests: the check's cross-check counts them too)
    assert records[0]["subtests"] == unsharded["subtests"] == {"passed": 2, "skipped": 1}
    # ... ran disjoint halves that add up to it, with the same outcomes as one whole run.
    one, two = (set(r["selected"]) for r in records)
    assert one and two and not one & two and one | two == set(unsharded["selected"])
    assert {**records[0]["outcomes"], **records[1]["outcomes"]} == unsharded["outcomes"]
    assert ci_shards.main(["check", str(out)]) == 0


def test_a_shard_stopped_part_way_leaves_an_incomplete_record(tmp_path: Path) -> None:
    project, out = _project(tmp_path), tmp_path / "records"
    (project / "conftest.py").write_text(
        "import os\n\ndef pytest_runtest_setup(item):\n    if item.name == 'test_b':\n        os._exit(3)\n",
        encoding="utf-8")
    for shard in ("1/2", "2/2"):
        _run(project, out, shard)
    record = json.loads((out / "shard-1.json").read_text(encoding="utf-8"))
    assert record["complete"] is False and record["selected"]
    assert ci_shards.main(["check", str(out)]) == 1


def test_a_failing_test_is_refused(tmp_path: Path) -> None:
    project, out = _project(tmp_path), tmp_path / "records"
    (project / "tests/test_m2.py").write_text("def test_a():\n    assert False\n", encoding="utf-8")
    assert [_run(project, out, shard).returncode for shard in ("1/2", "2/2")].count(1) == 1
    assert ci_shards.main(["check", str(out)]) == 1


@pytest.mark.parametrize("spec", ["3/2", "0/2", "x", "1/2 no record"])
def test_a_bad_shard_option_is_a_usage_error(tmp_path: Path, spec: str) -> None:
    project = _project(tmp_path)
    if spec.endswith("no record"):
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "tooling.ci_shards_plugin", "--mesh-shard",
                               "1/2"], cwd=project, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True,
                              text=True, timeout=120, check=False)
    else:
        proc = _run(project, tmp_path / "records", spec)
    assert proc.returncode == 4, proc.stdout + proc.stderr
