"""Milestone 22C: why a scatter stroke placed fewer than it asked for, counted from the brush's own decisions
(``engine.hd2d.scatter.Tally``, ``refusal``) and said in words with what to do (``explain``). Each reason from a real
stroke; counting never changes what is placed."""

from __future__ import annotations

from typing import Any

import pytest

import engine.project_ops as ops
from engine.hd2d import scatter as sc
from engine.hd2d.scatter import ASSETS, COLLECTIONS, Rules, Tally, allowed, explain, refusal

pytestmark = pytest.mark.fast


def _room(w: int = 640, h: int = 480) -> dict[str, Any]:
    return {"entities": [], "settings": {"world_width": w, "world_height": h,
                                         "hd2d": {"ground": {"from": [0, 0], "to": [w, h]}}}}


def _stroke(scene: dict[str, Any], collection: Any, dabs: list[list[float]], radius: float = 64,
            **kw: Any) -> tuple[dict[str, Any], Tally, str]:
    tally = Tally()
    out = ops.scatter_stroke(scene, collection, dabs, radius, tally=tally, **kw)
    weights = COLLECTIONS[collection] if isinstance(collection, str) else collection
    assert out == ops.scatter_stroke(scene, collection, dabs, radius, **kw), "counting changes nothing placed"
    return out, tally, explain(tally, collection if isinstance(collection, str) else "", weights)


def _count(scene: dict[str, Any]) -> int:
    return sum(len(v) for v in scene["settings"]["hd2d"].get("scatter", {}).values())


def test_refusal_is_allowed_in_words_with_the_same_checks() -> None:
    ground, _spots, _routes = ops.scatter_context(_room())
    rules = Rules()
    for name, asset in ASSETS.items():
        for x, y in ((320, 240), (-10, 240), (700, 900)):
            assert allowed(asset, x, y, ground, rules) == (refusal(asset, x, y, ground, rules) is None), name
    assert refusal(ASSETS["grass_tuft"], -10, 240, ground, rules) == "off_ground"


def test_trees_over_a_dense_meadow_are_crowded_out_by_the_meadow() -> None:
    meadow, _t, _w = _stroke(_room(), "Meadow", [[320, 240]], 96, seed=1)
    after, tally, words = _stroke(meadow, "Small tree", [[320, 240]], 96, seed=3)
    assert tally.placed == 0 and after == meadow
    assert tally.refused["spacing"] > tally.refused["clump"] and set(tally.crowded_by) <= set(COLLECTIONS["Meadow"])
    assert words.startswith("Held back: the Meadow already there leaves too little room (")
    assert words.endswith("Thin it first (Ctrl+drag) or scatter these before it.")


def test_density_already_reached() -> None:
    meadow, _t, _w = _stroke(_room(), "Meadow", [[320, 240]], 96, seed=1)
    again, tally, words = _stroke(meadow, "Meadow", [[320, 240]], 96, seed=2)
    assert again == meadow and tally.full == tally.dabs == 1 and tally.wanted == 0 and not tally.refused
    assert words == "Already as dense as Per m² asks here. Raise Per m² or brush somewhere sparser."


def test_too_close_to_their_own_kind() -> None:
    _out, tally, words = _stroke(_room(), "Small tree", [[320, 240]], 160, density=1.0, clumping=0.0)
    assert 0 < tally.placed < tally.wanted and set(tally.crowded_by) == {"tree_small"}
    assert words.startswith("Held back: they are as close as their spacing allows (")


def test_steep_ground_by_the_assets_own_limit_and_by_the_brushs_rule() -> None:
    mound = ops.sculpt_terrain_stroke(_room(), "raise", [[320, 240, 160]] * 3, 96)
    _out, tally, words = _stroke(mound, "Small tree", [[320, 240]], 64)
    assert tally.placed == 0 and tally.refused["slope"] and words.startswith("Held back: the ground is too steep (")
    assert words.endswith("Smooth or flatten it (Sculpt).")  # (trees never stand steeper than 25°)
    _out, tally, words = _stroke(mound, "Rocks", [[320, 240]], 64, slope=10)
    assert tally.refused["slope"] and "Raise Slope (°) (up to 40° for these) or smooth it." in words


def test_a_material_the_brush_isnt_set_to_and_one_the_thing_never_grows_on() -> None:
    _out, tally, words = _stroke(_room(), "Rocks", [[320, 240]], 64, on=["earth"])
    assert tally.materials == {"grass": tally.refused["material"]} and tally.placed == 0
    assert "the ground is grass, not chosen in the materials row" in words
    assert "Turn on Grass there or paint the ground." in words
    stone = ops.paint_terrain_stroke(_room(), "stone", [[320, 240, 1.0]] * 2, 120)
    _out, tally, words = _stroke(stone, "Meadow", [[320, 240]], 48, on=["stone"])
    assert tally.refused["grows"] and "these do not grow on stone" in words and "Paint it grass, or pick something else." in words


def test_water_structures_and_the_edge_of_the_ground() -> None:
    r, pond = ops.place_blank(_room(), "r", "Pond", 320, 240)
    r = ops.set_water(r, pond, preset="natural_pond", width=320, height=256)
    _out, tally, words = _stroke(r, "Meadow", [[320, 240]], 48)
    assert tally.refused["water"] and "in water (" in words and "turn off Out of water" in words
    hut = _room()
    hut["settings"]["hd2d"]["structures"] = [{"id": "hut", "model": "assets/models/none.glb", "x": 320.0, "y": 240.0}]
    _out, tally, words = _stroke(hut, "Meadow", [[320, 240]], 40)
    assert tally.refused["structure"] and "on or by a structure or doorway" in words and "turn off Off buildings" in words
    _out, tally, words = _stroke(_room(), "Meadow", [[-200, -200]], 96)
    assert tally.refused["off_ground"] and "past the edge of the room's ground" in words


def test_clumps_a_tiny_brush_and_the_rooms_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _out, tally, words = _stroke(_room(), "Small tree", [[200, 400]], 64, clumping=1.0, density=1.0)
    assert tally.placed == 0 and set(tally.refused) == {"clump"}
    assert words.startswith("Most tries (") and words.endswith("Lower Clumps or brush more ground.")
    _out, tally, words = _stroke(_room(), "Small tree", [[320, 240]], 8, density=0.01)
    assert tally.tiny == 1 and words.startswith("The brush is too small for Per m² to place one.")
    monkeypatch.setattr(sc, "MAX_INSTANCES", 10)
    full = ops.scatter_stroke(_room(), "Grass tuft", [[320, 240]], 96, density=2.0)
    assert _count(full) == 10
    after, tally, words = _stroke(full, "Rocks", [[200, 200]], 64)
    assert after == full and tally.at_limit == 1
    assert words.startswith("The room holds the most scattered things it can (10).")


def test_two_causes_at_once_and_a_mixed_collections_own_things() -> None:
    r = ops.paint_terrain_stroke(_room(), "earth", [[x, y, 1.0] for x in range(340, 460, 24) for y in range(140, 340, 24)],
                                 48)  # earth to the east of the brush, a pond to its west
    r, pond = ops.place_blank(r, "r", "Pond", 200, 240)
    r = ops.set_water(r, pond, preset="pond", width=300, height=280)
    _out, tally, words = _stroke(r, "Meadow", [[320, 240]], 112)
    assert tally.placed == 0 and tally.refused["material"] > tally.refused["water"] > 0
    assert words.index("the ground is earth") < words.index("in water (")  # both, most first
    assert "Turn on Earth there or paint the ground; brush beside it, turn off Out of water" in words
    hill = ops.sculpt_terrain_stroke(_room(), "raise", [[320, 240, 20]] * 3, 160)  # (steeper than 12°, under 40°)
    _out, tally, words = _stroke(hill, {"rock_small": 1, "fallen_branch": 1}, [[320, 240]], 96, seed=1)
    assert tally.placed == tally.wanted and tally.placed_by == {"rock_small": tally.placed}  # rocks fill it ...
    assert tally.by_asset["fallen_branch", "slope"] > 0  # ... the branches are refused: said, though all were added
    assert words.startswith("No fallen branch: the ground is too steep (") and words.endswith("(Sculpt).")


def test_nothing_under_the_brush_to_thin_and_no_change_when_nothing_is_placed() -> None:
    room = _room()
    out, tally, _words = _stroke(room, "Meadow", [[320, 240]], 96, mode="thin")
    assert tally.under == 0 and _count(out) == 0
    meadow, _t, _w = _stroke(_room(), "Meadow", [[320, 240]], 96, seed=1)
    out, tally, _words = _stroke(meadow, "Meadow", [[320, 240]], 96, mode="thin", share=0.5)
    assert tally.under == _count(meadow) and _count(out) < _count(meadow)
