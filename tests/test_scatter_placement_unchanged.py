"""Milestone 22C: counting why places are refused changes nothing placed. Each step of three scenarios
(tests/scatter_scenarios.py: a dense meadow then trees and rocks over it; steep ground, a path, a pond and a hut;
mixed collections) gives exactly the scatter it gave before M22C (its digest, recorded on b3f3275 before any
change), with and without a ``Tally``. Integration: a few seconds of scattering."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scatter_scenarios as sc  # noqa: E402

from engine.hd2d.scatter import Tally  # noqa: E402

pytestmark = pytest.mark.integration

BEFORE = {  # step -> (digest of its scatter as stored, instances), on b3f3275
    "meadow_then_trees_and_rocks/meadow": ("d807a2f4e4560d9a", 4236),
    "meadow_then_trees_and_rocks/trees": ("d807a2f4e4560d9a", 4236),
    "meadow_then_trees_and_rocks/rocks": ("80958150aae32850", 4289),
    "meadow_then_trees_and_rocks/meadow_again": ("80958150aae32850", 4289),
    "varied_ground/meadow": ("995f095f4c271d27", 3559),
    "varied_ground/pond_edge": ("4b83fba3b9e73f46", 3627),
    "varied_ground/rocks_on_path": ("e0b7c4e38887ac97", 3670),
    "varied_ground/trees_on_mound": ("e0b7c4e38887ac97", 3670),
    "varied_ground/shrubs": ("ff4d12e026bdd6cd", 3780),
    "mixed_collections/deadfall": ("337e5e527e12ef9b", 1312),
    "mixed_collections/wildflowers": ("eb7c30779cd921ab", 3148),
    "mixed_collections/boulders": ("eb7c30779cd921ab", 3148),
}


@pytest.mark.parametrize("name", list(sc.STEPS))
@pytest.mark.parametrize("counted", [False, True])
def test_the_same_strokes_place_exactly_what_they_did_before(name: str, counted: bool) -> None:
    for step, scene, tally in sc.run(name, tally=Tally if counted else (lambda: None)):
        rows = scene["settings"]["hd2d"].get("scatter", {})
        assert (sc.digest(scene), sum(len(v) for v in rows.values())) == BEFORE[f"{name}/{step}"], step
        if counted:
            assert tally.placed == sum(tally.placed_by.values())


def test_the_lakeside_case_is_counted_as_it_happened() -> None:
    """Trees, then rocks, over a dense meadow: the meadow already there is why."""
    steps = {step: tally for step, _scene, tally in sc.run("meadow_then_trees_and_rocks", tally=Tally)}
    trees, rocks, again = steps["trees"], steps["rocks"], steps["meadow_again"]
    assert trees.placed == 0 and trees.refused.most_common(1)[0][0] == "spacing"
    assert set(trees.crowded_by) <= {"grass_tuft", "grass_tall", "flowers_yellow", "flowers_pink"}
    assert rocks.placed == 53 and rocks.refused.most_common(1)[0][0] == "spacing"
    assert again.full == again.dabs and again.placed == 0
