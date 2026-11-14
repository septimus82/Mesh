"""#458: a lamp lit at a lamp post's lantern is not shadowed by that lamp post (its own fixture), and by nothing else
that isn't. The rule (``lamp_fixtures``) on the starter kit's real models, and the index ranges a lamp's shadow map
draws when it leaves its fixture out (``_kept_ranges``). The GPU's side: tests/test_hd2d_lamp_fixture_gpu.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.hd2d.glb import load_glb
from engine.hd2d.lighting import FIXTURE_MAX_M, FIXTURE_REACH_M, _kept_ranges, lamp_fixtures
from engine.hd2d.settings import PIXELS_PER_METRE as PX
from engine.hd2d.settings import Structure

pytestmark = [pytest.mark.integration]  # (reads the kit's model files)

KIT = Path(__file__).resolve().parents[1] / "assets" / "hd2d_starter" / "models"
MODELS = {name: load_glb(KIT / f"{name}.glb") for name in ("lamp_post", "wall_2m", "cottage", "barrel")}


def _at(model: str, x: float, y: float, sid: str, rotation: float = 0.0, scale: float = 1.0,
        elevation: float = 0.0) -> Structure:
    return Structure(model=model, x=x * PX, y=y * PX, elevation=elevation * PX, rotation=rotation, scale=scale, id=sid)


def test_the_kit_lamp_post_is_a_lantern_on_a_post() -> None:
    # The geometry the fix rests on (tooling/hd2d_assets/build_starter_kit.lamp_post): a closed lantern box round
    # the lamp's height, 0.52 m across at most, on a post whose top meets the lantern's floor.
    lo, hi = MODELS["lamp_post"].bounds()
    across = max(hi[0] - lo[0], hi[1] - lo[1])
    assert across == pytest.approx(0.52, abs=0.01) and across <= FIXTURE_MAX_M
    lantern = [p for p in MODELS["lamp_post"].parts if p.node == "lantern"]
    zs = [v for part in lantern for v in part.vertices[2::8]]
    assert min(zs) == pytest.approx(2.3, abs=0.01) and max(zs) == pytest.approx(2.75, abs=0.01)


@pytest.mark.parametrize("height", [2.3, 2.4, 2.5, 2.75])  # Lakeside's lamps hang at 2.4 m, the template's at 2.5 m
def test_a_lamp_at_the_lantern_has_the_lamp_post_as_its_fixture(height: float) -> None:
    post = _at("lamp_post", 8.0, 8.0, "post")
    assert lamp_fixtures((8.0, 8.0, height), [post], MODELS) == {"post"}
    # (Lakeside's lamps are 1.25 cm off the post's axis, from rounding px)
    assert lamp_fixtures((8.0 + 0.0125, 8.0, height), [post], MODELS) == {"post"}


@pytest.mark.parametrize("lamp", [(8.0, 8.0, 3.05), (8.0, 8.4, 2.4), (8.4, 8.0, 2.5), (9.0, 8.0, 2.4),
                                  (8.3, 8.0, 1.5)])
def test_a_lamp_merely_near_a_lamp_post_has_no_fixture(lamp: tuple[float, float, float]) -> None:
    # 20 cm above the cap, 0.2 m beside the lantern (twice), 1 m away, 0.22 m beside the post: each farther than
    # FIXTURE_REACH_M (0.15 m) from every part's box, so the lamp post still casts this lamp's shadows
    assert lamp_fixtures(lamp, [_at("lamp_post", 8.0, 8.0, "post")], MODELS) == set()


@pytest.mark.parametrize(("dx", "height"), [(0.25, 2.5), (0.27, 2.5), (0.30, 2.5), (0.0, 2.95), (0.15, 2.2),
                                            (0.21, 2.4)])
def test_a_lamp_a_few_centimetres_off_its_lantern_still_has_it_as_its_fixture(dx: float, height: float) -> None:
    # M17-L3: a light placed 25-30 cm off the lantern's centre (5-10 cm outside its box), 10 cm above the cap or just
    # under the lantern lost 28-99 % of its pool to its own lamp head; within FIXTURE_REACH_M it is that lamp's head
    post = _at("lamp_post", 8.0, 8.0, "post")
    assert FIXTURE_REACH_M == 0.15
    assert lamp_fixtures((8.0 + dx, 8.0, height), [post], MODELS) == {"post"}
    assert lamp_fixtures((8.0, 8.0 - dx, height), [post], MODELS) == {"post"}  # (any side)


def test_an_independent_panel_beside_the_light_is_never_its_fixture() -> None:
    # The panel #458's GPU test keeps casting: a wall_2m scaled to 1 m (fixture-sized), turned, 0.23-0.33 m from a
    # lamp in its lantern: farther than the reach, so it isn't left out; the lamp post is
    post, panel = _at("lamp_post", 8.0, 8.0, "post"), _at("wall_2m", 7.75, 8.0, "panel", rotation=90.0, scale=0.5,
                                                            elevation=1.5)
    assert lamp_fixtures((8.0, 8.0, 2.4), [post, panel], MODELS) == {"post"}
    assert lamp_fixtures((8.1, 8.0, 2.4), [panel], MODELS) == set()  # (0.25 m+ from the panel's face)


def test_a_small_prop_within_the_reach_is_left_out_and_one_beyond_it_is_not() -> None:
    # The rule's documented edge: a light within 0.15 m of a fixture-sized prop's box (a candle on a barrel) is that
    # prop's own; 0.2 m beside it, the barrel still casts its shadow
    barrel = _at("barrel", 8.0, 8.0, "barrel")
    assert lamp_fixtures((8.0, 8.0, 1.1), [barrel], MODELS) == {"barrel"}
    assert lamp_fixtures((8.6, 8.0, 0.5), [barrel], MODELS) == set()


def test_a_lamp_inside_any_part_of_a_fixture_sized_model_counts() -> None:
    # (inside the post itself, below the lantern: the light starts in the lamp post there too)
    assert lamp_fixtures((8.0, 8.0, 1.5), [_at("lamp_post", 8.0, 8.0, "post")], MODELS) == {"post"}


def test_walls_and_buildings_are_never_a_fixture_however_close_or_even_around_the_lamp() -> None:
    wall = _at("wall_2m", 8.0, 8.35, "wall")  # its face 0.25 m from a lamp at (8, 8)
    inside_wall = _at("wall_2m", 8.0, 8.0, "wall_round")  # the lamp inside the wall's own box
    house = _at("cottage", 20.0, 20.0, "house")
    assert lamp_fixtures((8.0, 8.0, 2.4), [wall, inside_wall], MODELS) == set()
    assert lamp_fixtures((20.0, 20.0, 1.5), [house], MODELS) == set()  # a lamp inside a house: still blocked by it


def test_the_placement_turn_scale_and_height_are_undone() -> None:
    turned = _at("lamp_post", 8.0, 8.0, "turned", rotation=37.0)
    assert lamp_fixtures((8.0 + 0.15, 8.0 + 0.1, 2.5), [turned], MODELS) == {"turned"}
    raised = _at("lamp_post", 8.0, 8.0, "raised", elevation=3.0)
    assert lamp_fixtures((8.0, 8.0, 5.5), [raised], MODELS) == {"raised"}
    assert lamp_fixtures((8.0, 8.0, 2.5), [raised], MODELS) == set()
    small = _at("lamp_post", 8.0, 8.0, "small", scale=0.5)
    assert lamp_fixtures((8.0, 8.0, 1.25), [small], MODELS) == {"small"}
    big = _at("lamp_post", 8.0, 8.0, "big", scale=3.0)  # 1.56 m across: no longer a fixture-sized model
    assert lamp_fixtures((8.0, 8.0, 7.5), [big], MODELS) == set()


def test_only_the_fixture_of_the_lamp_and_every_other_structure_kept() -> None:
    posts = [_at("lamp_post", 8.0, 8.0, "a"), _at("lamp_post", 9.0, 8.0, "b"), _at("barrel", 8.0, 9.0, "barrel")]
    assert lamp_fixtures((8.0, 8.0, 2.4), posts, MODELS) == {"a"}
    assert lamp_fixtures((9.0, 8.0, 2.4), posts, MODELS) == {"b"}
    assert lamp_fixtures((8.0, 8.0, 2.4), posts, {}) == set()  # (models not read: nothing left out)


def test_a_lamps_shadow_map_draws_every_span_but_its_fixtures() -> None:
    spans = [("wall", 0, 36), ("post", 36, 108), ("crate", 144, 36), ("post", 180, 12), ("barrel", 192, 60)]
    assert _kept_ranges(spans, frozenset({"post"})) == [(0, 36), (144, 36), (192, 60)]
    assert _kept_ranges(spans, frozenset({"wall"})) == [(36, 216)]  # (adjacent kept spans: one draw)
    assert _kept_ranges(spans, frozenset({"other"})) is None  # nothing of it here: drawn whole
    assert _kept_ranges(spans, frozenset()) is None
    assert _kept_ranges(None, frozenset({"post"})) is None  # a draw without spans (ground, scatter): whole
    assert _kept_ranges([("post", 0, 36)], frozenset({"post"})) == []  # (an unbatched draw of the fixture: none)
