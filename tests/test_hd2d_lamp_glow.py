"""M17-L3 E2: which parts a lamp lights as its own lamp head (engine.hd2d.lighting.lamp_head), and the glow the
renderer gives them (Hd2dRenderer._lamp_heads), without a GPU.

The eight lamps of the E2 investigation's four rooms (tooling/hd2d_lamp_glow_demo.py rebuilds them from the starter
kit) each light their own lantern's glass and nothing else: not Lakeside lamp 4's cottage, not #459's panel; the
cottage's ceiling lamp, in no fixture, lights nothing. Anything uncertain lights nothing. The pixels:
tests/test_hd2d_lamp_glow_gpu.py."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from engine.hd2d import lighting
from engine.hd2d.glb import Material, load_glb
from engine.hd2d.renderer import Hd2dRenderer
from engine.hd2d.settings import MAX_LIGHTS, PointLight, Structure
from engine.hd2d.settings import PIXELS_PER_METRE as PPM

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_lamp_glow_demo as demo  # noqa: E402

POST = REPO / "assets/hd2d_starter/models/lamp_post.glb"
MODEL = "assets/models/lamp_post.glb"


@pytest.fixture(scope="module")
def rooms(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    project = tmp_path_factory.mktemp("glow") / "game"
    return project, demo.build(project)


def _lantern() -> frozenset[int]:
    return frozenset(i for i, p in enumerate(load_glb(POST).parts) if p.material.name == "lantern")


def test_the_eight_lamps_light_their_own_lantern_glass_only(rooms: tuple[Path, dict[str, str]]) -> None:
    project, paths = rooms
    expected = {"village": ["lamp_west", "lamp_east"], "lakeside": ["lamp_post", "lamp_post_2", "lamp_post_3",
                                                                     "lamp_post_4"],
                "fixtures": ["lamp_a", "lamp_b"], "cottage": [None]}
    found = {room: demo.heads(project, path) for room, path in paths.items()}
    assert {room: [r["head"] and r["head"]["structure"] for r in rows] for room, rows in found.items()} == expected
    lit = [r["head"] for rows in found.values() for r in rows if r["head"]]
    assert len(lit) == 8
    for head in lit:
        assert head["nodes"] == ["lantern"] and head["materials"] == ["lantern"]
        assert head["parts"] == sorted(_lantern())  # (the lantern node's glass; its "iron" frame shares the post's)


def test_lakeside_lamp_4_never_lights_the_cottage_and_459s_panel_stays_unlit(rooms: tuple[Path, dict[str, str]]) -> None:
    project, paths = rooms
    lake = demo.heads(project, paths["lakeside"])
    assert [r["head"]["structure"] for r in lake] == ["lamp_post", "lamp_post_2", "lamp_post_3", "lamp_post_4"]
    hd2d, models = demo.room_settings(project, paths["lakeside"])
    lamp4 = hd2d.lights[3]
    near = (lamp4.x / PPM, lamp4.y / PPM, lamp4.elevation / PPM)
    assert "cottage" not in lighting.lamp_fixtures(near, hd2d.structures, models)  # (0.2 m inside its corner)
    fixtures = demo.heads(project, paths["fixtures"])
    assert all(r["head"]["structure"] != "near_panel" for r in fixtures)


def test_the_cottage_ceiling_lamp_has_no_fixture_so_nothing_glows(rooms: tuple[Path, dict[str, str]]) -> None:
    project, paths = rooms
    hd2d, models = demo.room_settings(project, paths["cottage"])
    renderer = cast(Any, SimpleNamespace(_heads=None, settings=hd2d, models=models))
    assert Hd2dRenderer._lamp_heads(renderer) == {}


def _post(sid: str, x: float, y: float) -> Structure:
    return Structure(id=sid, model=MODEL, x=x, y=y)


def test_uncertain_heads_light_nothing() -> None:
    models = {MODEL: load_glb(POST)}
    one = [_post("a", 320.0, 320.0)]
    assert lighting.lamp_head((10.0, 10.0, 2.5), one, models) == ("a", _lantern())
    # on the boundary between the lantern and its cap: two nodes as near as each other
    assert lighting.lamp_head((10.0, 10.0, 2.75), one, models) is None
    # two lamp posts in one place: two fixtures as near as each other
    assert lighting.lamp_head((10.0, 10.0, 2.5), one + [_post("b", 320.0, 320.0)], models) is None
    # a lamp in no fixture's reach
    assert lighting.lamp_head((10.0, 10.0, 3.2), one, models) is None


def test_a_head_whose_material_is_shared_or_authored_glows_by_no_lamp() -> None:
    post = load_glb(POST)
    iron = next(p.material for p in post.parts if p.material.name == "iron")
    shared = dataclasses.replace(post, parts=[dataclasses.replace(p, material=iron) for p in post.parts])
    assert lighting.lamp_head((10.0, 10.0, 2.5), [_post("a", 320.0, 320.0)], {MODEL: shared}) is None
    glass = next(p.material for p in post.parts if p.material.name == "lantern")
    authored = Material(glass.name, glass.image, emissive=(1.0, 0.8, 0.55))  # (E1: its own emission is drawn)
    emissive = dataclasses.replace(post, parts=[dataclasses.replace(p, material=authored) if p.material is glass else p
                                                for p in post.parts])
    assert lighting.lamp_head((10.0, 10.0, 2.5), [_post("a", 320.0, 320.0)], {MODEL: emissive}) is None


def _glows(lamps: list[PointLight], structures: list[Structure]) -> dict:
    settings = SimpleNamespace(lights=tuple(lamps), structures=structures)
    return Hd2dRenderer._lamp_heads(cast(Any, SimpleNamespace(_heads=None, settings=settings,
                                                              models={MODEL: load_glb(POST)})))


def test_a_heads_glow_is_its_lamps_colour_times_intensity_in_linear_light() -> None:
    post = [_post("a", 320.0, 320.0)]
    lamp = PointLight(x=320.0, y=320.0, elevation=80.0, radius=224.0, color=(1.0, 0.5, 0.0), intensity=2.0)
    glow = _glows([lamp], post)
    assert set(glow) == {("a", i) for i in _lantern()}
    r, g, b = next(iter(glow.values()))
    assert r == pytest.approx(2.0) and g == pytest.approx(2.0 * ((0.5 + 0.055) / 1.055) ** 2.4) and b == 0.0
    assert _glows([dataclasses.replace(lamp, intensity=0.0)], post) == {}  # (intensity 0: no glow, no draw)
    twice = _glows([lamp, dataclasses.replace(lamp, color=(0.0, 0.0, 1.0), intensity=1.0)], post)
    assert next(iter(twice.values())) == pytest.approx((2.0, g, 1.0))  # (two lamps in one lantern: both)


def test_only_the_lamps_the_room_draws_light_their_heads() -> None:
    """The first MAX_LIGHTS lamps are the ones lit; a lamp past them glows no more than it shines."""
    posts = [_post(f"p{i}", 64.0 + 96.0 * i, 320.0) for i in range(MAX_LIGHTS + 1)]
    lamps = [PointLight(x=st.x, y=st.y, elevation=80.0, radius=224.0, color=(1.0, 0.8, 0.5)) for st in posts]
    lit = {sid for sid, _i in _glows(lamps, posts)}
    assert lit == {f"p{i}" for i in range(MAX_LIGHTS)}
