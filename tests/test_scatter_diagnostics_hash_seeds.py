"""Milestone 22C: what a stroke's ``Tally`` says (which things crowded it out, and the words) is the same in every
Python process, whatever its string-hash seed (``PYTHONHASHSEED``: it orders the sets the brush's index keeps).
Each stroke of tests/scatter_scenarios.py, counted in processes with different seeds. Integration (subprocesses)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[1]
COUNT = r"""
import json, sys
sys.path.insert(0, {tests!r})
import scatter_scenarios as sc
from engine.hd2d.scatter import COLLECTIONS, Tally, explain
out = {{}}
for name in sc.STEPS:
    for step, scene, t in sc.run(name, tally=Tally):
        out[f"{{name}}/{{step}}"] = [sc.digest(scene), sorted(t.crowded_by.items()), sorted(t.refused.items()),
                                   sorted([list(k), v] for k, v in t.by_asset.items()),
                                   explain(t, sc.COLLECTION[step], COLLECTIONS[sc.COLLECTION[step]])]
print(json.dumps(out))
"""


def _counted(seed: int) -> dict:
    env = {**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONPATH": str(REPO)}
    done = subprocess.run([sys.executable, "-c", COUNT.format(tests=str(REPO / "tests"))], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-2000:]
    result: dict = json.loads(done.stdout.strip().splitlines()[-1])
    return result


def test_the_counts_and_the_words_are_the_same_whatever_the_hash_seed() -> None:
    first, second, third = _counted(0), _counted(1), _counted(4242)
    for step in first:
        assert first[step] == second[step] == third[step], step
