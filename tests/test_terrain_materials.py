"""Milestone 20C: painted terrain materials, headless: their storage (sparse, deterministic, compatible with 20B
rooms), the dab (time-based, rounding carried), the checked edit Studio, the CLI and AI share, its refusals, and that
paint never changes what is walked on. The drawing is tests/test_terrain_gpu.py."""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d
from engine.hd2d.terrain import CHUNK, MATERIALS, PAINTED, Terrain
from engine.hd2d.world import World

pytestmark = pytest.mark.fast


def _room(terrain: dict[str, Any] | None = None, size: tuple[int, int] = (640, 480)) -> dict[str, Any]:
    ground: dict[str, Any] = {"from": [0, 0], "to": list(size)}
    if terrain is not None:
        ground["terrain"] = terrain
    return {"entities": [], "settings": {"world_width": size[0], "world_height": size[1], "hd2d": {"ground": ground}}}


def _terrain(room: dict[str, Any]) -> Terrain:
    return Terrain.from_ground(ops._parsed_ground(room))


def _path(material: str = "earth", strength: float = 0.4) -> list[list[float]]:
    return [[64 + 8 * k, 200 + 40 * math.sin(k / 6), strength] for k in range(60)]


def test_paint_is_stored_sparse_sorted_and_the_same_every_time() -> None:
    a = ops.paint_terrain_stroke(_room(size=(2048, 1536)), "earth", _path(), 24)  # (48 chunks)
    terrain = a["settings"]["hd2d"]["ground"]["terrain"]
    assert terrain["chunks"] == {} and "edges" not in terrain  # (no heights: none stored; soft edges: not written)
    keys = list(terrain["materials"])
    assert keys == sorted(keys, key=lambda k: tuple(map(int, k.split(",")))[::-1])
    assert len(keys) <= 6, "only the chunks the path crosses"
    assert all(len(base64.b64decode(v)) == CHUNK * CHUNK * PAINTED for v in terrain["materials"].values())
    assert ops.paint_terrain_stroke(_room(size=(2048, 1536)), "earth", _path(), 24) == a
    t = _terrain(a)
    assert t.material_at(64 + 8 * 30, 200 + 40 * math.sin(5)) == "earth" and t.material_at(600, 40) == "grass"
    assert t.is_flat(), "paint changes no height"


def test_no_corner_is_ever_more_than_all_of_one_material() -> None:
    room = _room()
    for material in ("earth", "stone", "mud", "sand", "stone", "grass", "mud"):
        room = ops.paint_terrain_stroke(room, material, [[200 + 3 * k, 200, 0.7] for k in range(40)], 64)
    paint = _terrain(room).paint
    assert paint is not None
    assert max(sum(paint[k:k + PAINTED]) for k in range(0, len(paint), PAINTED)) <= 255


def test_grass_paints_the_others_away_and_the_plain_ground_comes_back() -> None:
    room = ops.paint_terrain_stroke(_room(), "mud", [[320, 240, 0.5]], 64)
    assert room["settings"]["hd2d"]["ground"]["terrain"]["materials"]
    for _ in range(4):
        room = ops.paint_terrain_stroke(room, "grass", [[320, 240, 1.0]], 96)
    assert "terrain" not in room["settings"]["hd2d"]["ground"], "unpainted and flat: the plain ground, as before"
    assert parse_hd2d(room["settings"]["hd2d"]).ground.terrain is None


@pytest.mark.parametrize("material", ["earth", "stone", "grass"])
def test_many_small_dabs_paint_what_a_few_big_ones_do(material: str) -> None:
    """Strength is by time: 60 dabs of a 60th of a second give what 6 of a sixth do (Studio's frames don't matter)."""
    base = ops.paint_terrain_stroke(_room(), "sand", [[320, 240, 1.0]], 128)  # (something to paint grass over)
    rate = 3.0

    def held(n: int) -> bytearray:
        dabs = [[320.0, 240.0, round(1 - math.exp(-rate / n), 6)] for _ in range(n)]
        paint = _terrain(ops.paint_terrain_stroke(base, material, dabs, 96)).paint
        return paint if paint is not None else bytearray(4)

    few, many = held(6), held(60)
    assert len(few) == len(many)
    assert max(abs(a - b) for a, b in zip(few, many)) <= 2


def test_paint_never_changes_what_is_walked_on() -> None:
    hilly = ops.sculpt_terrain_stroke(_room(), "raise", [[320, 240, 40]], 128)
    painted = ops.paint_terrain_stroke(hilly, "stone", _path(strength=1.0), 48)
    before, after = _terrain(hilly), _terrain(painted)
    assert after.heights == before.heights
    settings = parse_hd2d(painted["settings"]["hd2d"])
    w0, w1 = World(parse_hd2d(hilly["settings"]["hd2d"]), {}), World(settings, {})
    w0.update_terrain(before)
    w1.update_terrain(after)
    for x, y in ((3.0, 3.0), (10.0, 7.5), (12.0, 6.0)):
        assert w1.heights_at(x, y) == w0.heights_at(x, y)
    assert w1._nav_grid() == w0._nav_grid(), "navigation: the same grid"


def test_sculpting_flattening_and_edges_keep_the_paint() -> None:
    painted = ops.paint_terrain_stroke(_room(), "earth", _path(), 24)
    materials = painted["settings"]["hd2d"]["ground"]["terrain"]["materials"]
    sculpted = ops.sculpt_terrain_stroke(painted, "raise", [[200, 200, 24]], 96)
    assert sculpted["settings"]["hd2d"]["ground"]["terrain"]["materials"] == materials
    flat = ops.flatten_all_terrain(sculpted)
    assert flat["settings"]["hd2d"]["ground"]["terrain"] == {"cell": 16, "chunks": {}, "materials": materials}
    hard = ops.set_terrain_edges(flat, "hard")
    assert hard["settings"]["hd2d"]["ground"]["terrain"]["edges"] == "hard"
    assert _terrain(hard).edges == "hard"
    again = ops.paint_terrain_stroke(hard, "earth", [[500, 400, 0.5]], 32)
    assert again["settings"]["hd2d"]["ground"]["terrain"]["edges"] == "hard", "a stroke keeps the room's edges"
    assert "edges" not in ops.set_terrain_edges(hard, "soft")["settings"]["hd2d"]["ground"]["terrain"]


def test_hard_edges_chosen_on_a_plain_room_are_kept_for_its_first_stroke() -> None:
    hard = ops.set_terrain_edges(_room(), "hard")
    assert parse_hd2d(hard["settings"]["hd2d"]).ground.terrain == {"cell": 16, "chunks": {}, "edges": "hard"}
    painted = ops.paint_terrain_stroke(hard, "earth", [[100, 100, 0.5]], 32)
    assert painted["settings"]["hd2d"]["ground"]["terrain"]["edges"] == "hard"
    assert "terrain" not in ops.set_terrain_edges(hard, "soft")["settings"]["hd2d"]["ground"]


def test_a_20b_room_reads_and_writes_exactly_as_before() -> None:
    old = ops.sculpt_terrain_stroke(_room(), "raise", [[320, 240, 40]], 128)["settings"]["hd2d"]["ground"]["terrain"]
    assert set(old) == {"cell", "chunks"}
    t = Terrain.from_ground(parse_hd2d({"ground": {"from": [0, 0], "to": [640, 480], "terrain": old}}).ground)
    assert t.paint is None and t.edges == "soft"
    assert t.settings(old) == old and t.settings() == old
    room = ops.sculpt_terrain_stroke(_room(old), "lower", [[100, 100, 8]], 64)
    assert set(room["settings"]["hd2d"]["ground"]["terrain"]) == {"cell", "chunks"}, "no new keys in a 20B room"


@pytest.mark.parametrize(("material", "dabs", "radius", "words"), [
    ("lava", [[1, 1, 0.5]], 32, "material is one of"),
    ("earth", [], 32, "at least one"),
    ("earth", "dabs", 32, "at least one"),
    ("earth", [[1, 1]], 32, r"must be \[x, y, strength\]"),
    ("earth", [[1, 1, 1.5]], 32, "strength"),
    ("earth", [[1, 1, float("nan")]], 32, "strength"),
    ("earth", [[float("inf"), 1, 0.5]], 32, "x"),
    ("earth", [[5000, 1, 0.5]], 32, "off the room's ground"),
    ("earth", [[1, 1, 0.5]], 4, "radius"),
])
def test_bad_strokes_are_refused_with_the_reason(material: str, dabs: Any, radius: float, words: str) -> None:
    with pytest.raises(ops.OpError, match=words):
        ops.paint_terrain_stroke(_room(), material, dabs, radius)


def test_too_long_a_stroke_and_rooms_without_ground_are_refused() -> None:
    with pytest.raises(ops.OpError, match="at most"):
        ops.paint_terrain_stroke(_room(), "earth", [[1, 1, 0.1]] * (ops.STROKE_DABS + 1), 32)
    with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
        ops.paint_terrain_stroke({"entities": [], "settings": {}}, "earth", [[1, 1, 0.1]], 32)
    with pytest.raises(ops.OpError, match="edges are one of"):
        ops.set_terrain_edges(_room(), "fuzzy")


@pytest.mark.parametrize(("materials", "words"), [
    ({"0,0": "not base64!"}, "isn't base64"),
    ({"0,0": base64.b64encode(bytes(10)).decode()}, "has 10 bytes"),
    ({"0,0": base64.b64encode(bytes([200, 100, 0, 0]) * (CHUNK * CHUNK)).decode()}, "more than 255"),
    ({"9,9": base64.b64encode(bytes(CHUNK * CHUNK * PAINTED)).decode()}, "outside the ground"),
    ({"a,b": base64.b64encode(bytes(CHUNK * CHUNK * PAINTED)).decode()}, "keys are 'i,j'"),
    ([1, 2], "materials must map"),
])
def test_broken_paint_is_named_and_set_aside(materials: Any, words: str) -> None:
    raw = {"ground": {"from": [0, 0], "to": [640, 480], "terrain": {"cell": 16, "chunks": {}, "materials": materials}}}
    with pytest.raises(Hd2dSettingsError, match=words):
        parse_hd2d(raw)
    lenient = parse_hd2d(raw, lenient=True)
    assert lenient.ground.terrain is None and lenient.terrain_error and words.split()[0].strip("'\\") in (
        lenient.terrain_error + words)
    with pytest.raises(Hd2dSettingsError, match="edges must be one of"):
        parse_hd2d({"ground": {"from": [0, 0], "to": [640, 480], "terrain": {"cell": 16, "chunks": {}, "edges": 3}}})


def test_steep_and_gentle_faces_are_split_by_cell() -> None:
    t = Terrain.from_ground(parse_hd2d({"ground": {"from": [0, 0], "to": [640, 480]}}).ground)
    t.sculpt("lower", 320, 240, 160, 24)  # a gentle basin: no steep faces
    assert all(not t.chunk_mesh(ci, cj)[1] for ci in range(3) for cj in range(2))
    for _ in range(3):
        t.sculpt("raise", 320, 240, 96, 24)  # a mound with steep faces
    gentle, steep = t.chunk_mesh(1, 1)
    assert gentle and steep


def test_the_ai_and_the_cli_paint_with_studio_s_operation(tmp_path: Path) -> None:
    from engine import authoring_session
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    assert {"paint_terrain_stroke", "set_terrain_edges"} <= set(authoring.operations())
    for name in ("stone", "mud", "sand"):  # (the template brings the materials' textures)
        assert (root / "assets" / "hd2d_starter" / "textures" / f"{name}.png").is_file()
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    authoring.apply(project, [{"op": "paint_terrain_stroke", "room": room, "material": "stone", "radius": 48,
                               "dabs": [[300, 300, 0.8], [330, 310, 0.8]]}])
    assert project.scene(room)["settings"]["hd2d"]["ground"]["terrain"]["materials"]
    with pytest.raises(authoring.ChangeError, match="material is one of"):
        authoring.apply(project, [{"op": "paint_terrain_stroke", "room": room, "material": "lava",
                                   "dabs": [[1, 1, 0.5]]}])
    project.save()
    result = authoring_session.apply(root, [{"op": "set_terrain_edges", "room": room, "edges": "hard"}])
    assert result["ok"], result
    fresh = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    assert fresh.scene(room)["settings"]["hd2d"]["ground"]["terrain"]["edges"] == "hard"
    assert MATERIALS[0] == "grass"


# --- Technical QA's findings (Stage 20C), kept fixed ------------------------------------------------------------------
def test_the_ai_s_summary_says_what_was_painted_and_the_edges() -> None:
    from engine.authoring import _terrain_lines

    painted = ops.paint_terrain_stroke(_room(), "stone", [[320, 240, 1.0]], 64)
    lines = _terrain_lines("Hills", _room(), painted)
    assert len(lines) == 1 and lines[0].startswith("Hills: ground painted: stone about"), lines
    assert _terrain_lines("Hills", painted, ops.set_terrain_edges(painted, "hard")) == ["Hills: material edges hard"]


def test_broken_paint_sets_aside_only_the_paint_and_clear_paint_mends_it() -> None:
    hilly = ops.sculpt_terrain_stroke(_room(), "raise", [[320, 240, 40]], 128)
    room = ops.paint_terrain_stroke(hilly, "mud", [[100, 100, 0.8]], 48)
    room["settings"]["hd2d"]["ground"]["terrain"]["materials"]["0,0"] = "not base64!"
    lenient = parse_hd2d(room["settings"]["hd2d"], lenient=True)
    assert lenient.ground.terrain is not None and "materials" not in lenient.ground.terrain, "the heights stay"
    assert lenient.terrain_error.startswith("its paint is set aside (") and "isn't base64" in lenient.terrain_error
    assert Terrain.from_ground(lenient.ground).heights == _terrain(hilly).heights
    mended = ops.clear_terrain_paint(room)
    assert "materials" not in mended["settings"]["hd2d"]["ground"]["terrain"]
    assert _terrain(mended).heights == _terrain(hilly).heights
    assert "terrain" not in ops.clear_terrain_paint(ops.paint_terrain_stroke(_room(), "mud", [[1, 1, 1]], 48))[
        "settings"]["hd2d"]["ground"], "nothing else there: the plain ground"


def test_flattening_keeps_hard_edges_and_erasing_leaves_no_trace() -> None:
    hard = ops.set_terrain_edges(ops.sculpt_terrain_stroke(_room(), "raise", [[320, 240, 40]], 128), "hard")
    assert ops.flatten_all_terrain(hard)["settings"]["hd2d"]["ground"]["terrain"] == {"cell": 16, "chunks": {},
                                                                                      "edges": "hard"}
    room = ops.paint_terrain_stroke(_room(), "stone", [[320, 240, 1.0]], 64)
    for _ in range(40):  # (light, separate strokes: each starts from the stored bytes)
        room = ops.paint_terrain_stroke(room, "grass", [[320, 240, 0.6]], 96)  # (a brush wider than the patch)
    assert "terrain" not in room["settings"]["hd2d"]["ground"], "erased: the plain ground again"


def test_the_eyedropper_finds_paint_in_a_cell_the_ground_s_edge_cuts_short() -> None:
    t = Terrain.from_ground(parse_hd2d({"ground": {"from": [0, 0], "to": [650, 480]}}).ground)  # (40 cells and 10 px)
    t.paint_dab("sand", 650, 240, 9, 1.0)  # (only the corner on the edge, at x = 650)
    assert t.material_at(648, 240) == "sand" and t.material_at(636, 240) == "grass"
