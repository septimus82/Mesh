"""Milestone 16 Stage 5A: editing HD-2D structures, headless. The structure operations (project_ops) are the one
path for Mesh Studio and AI tools: validated, with stable ids and useful errors; the authoring layer checks the
model file and describes changes in words; the editor's camera rays and 3D picking agree with what is drawn."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d.glb import load_glb, model_problem
from engine.hd2d.picking import Picker, ground_point, placement
from engine.hd2d.renderer import Camera, _placement
from engine.hd2d.settings import parse_hd2d

pytestmark = pytest.mark.fast
REPO = Path(__file__).resolve().parents[1]
CROSSING = REPO / "tooling" / "hd2d_assets" / "stone_crossing.glb"
MODEL = "assets/models/stone_crossing.glb"


def _room() -> dict:
    return {"name": "t", "entities": [], "settings": {"hd2d": {
        "structures": [{"id": "crossing", "model": MODEL, "x": 512, "y": 384}], "ground": {"to": [1024, 768]}}}}


def test_place_move_turn_and_remove_a_structure() -> None:
    room, sid = ops.place_structure(_room(), MODEL, 300, 200, rotation=-90)
    assert sid == "stone_crossing" and ops.find_structure(room, sid) == {
        "id": sid, "model": MODEL, "x": 300.0, "y": 200.0, "rotation": 270.0}
    room2, sid2 = ops.place_structure(room, MODEL, 600, 200)
    assert sid2 == "stone_crossing_2", "ids stay unique and stable"
    room3 = ops.set_structure(room2, "crossing", x=576, elevation=32, rotation=450)
    assert ops.find_structure(room3, "crossing") == {"id": "crossing", "model": MODEL, "x": 576.0, "y": 384,
                                                     "elevation": 32.0, "rotation": 90.0}
    assert ops.find_structure(room2, "crossing")["x"] == 512, "pure: the input room is unchanged"
    room4 = ops.remove_structure(room3, sid)
    assert [s["id"] for s in ops.structures(room4)] == ["crossing", "stone_crossing_2"]


@pytest.mark.parametrize(("change", "message"), [
    (lambda r: ops.place_structure({"entities": []}, MODEL, 1, 1), "isn't an HD-2D room"),
    (lambda r: ops.place_structure(r, "outpost.obj", 1, 1), "project-relative .glb"),
    (lambda r: ops.place_structure(r, MODEL, 1, 1, structure_id="crossing"), "already a structure 'crossing'"),
    (lambda r: ops.place_structure(r, MODEL, 5000, 1), "outside the room's ground"),
    (lambda r: ops.set_structure(r, "nope", x=1), "no structure 'nope'"),
    (lambda r: ops.set_structure(r, "crossing", x="east"), "x must be a number"),
    (lambda r: ops.set_structure(r, "crossing", scale=0), "scale must be between"),
    (lambda r: ops.remove_structure(r, "nope"), "no structure 'nope'"),
])
def test_bad_structure_edits_are_refused_with_a_useful_error(change, message: str) -> None:
    with pytest.raises(ops.OpError, match=message):
        change(_room())


def test_the_structure_ops_are_shared_with_ai_tools_and_described_in_words() -> None:
    names = set(authoring.operations())
    assert {"place_structure", "set_structure", "remove_structure"} <= names
    catalogue = {op["op"]: op for op in authoring.describe()}
    assert "structure_id" in str(catalogue["set_structure"])
    before = _room()
    after, _ = ops.place_structure(ops.set_structure(before, "crossing", x=600, rotation=90), MODEL, 64, 64)
    lines = authoring._structure_lines("Start", ops.structures(before), ops.structures(after))
    assert lines == ["Start: places structure 'stone_crossing' (assets/models/stone_crossing.glb) at (2.0 m, 2.0 m)",
                     "Start: moves structure 'crossing' (16.0 m, 12.0 m) -> (18.8 m, 12.0 m, turned 90 degrees)"]


def test_a_model_must_exist_and_be_a_usable_glb(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "ok.glb").write_bytes(CROSSING.read_bytes())
    (tmp_path / "assets" / "bad.glb").write_bytes(b"not a model")
    assert model_problem(tmp_path, "assets/ok.glb") is None
    assert "There is no model 'assets/missing.glb'" in model_problem(tmp_path, "assets/missing.glb")
    assert "not a GLB file" in model_problem(tmp_path, "assets/bad.glb")


def test_authoring_applies_structure_changes_to_a_project_and_refuses_a_missing_model(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO / "tooling"))
    import hd2d_floors_demo

    project_dir = hd2d_floors_demo.build(tmp_path / "proj")
    from engine.authoring_session import open_project

    project = open_project(project_dir)
    made = authoring.apply(project, [{"op": "place_structure", "model": MODEL, "x": 224, "y": 640},
                                     {"op": "set_structure", "structure_id": "@0", "rotation": 90}])
    placed = [s for s in ops.structures(project.scene()) if s["id"] != "crossing"]
    assert placed and placed[0]["rotation"] == 90.0 and placed[0]["x"] == 224.0
    assert placed[0]["id"] in str(made), "the new id is reported back"
    with pytest.raises(authoring.ChangeError, match="no model 'assets/models/missing.glb'"):
        authoring.apply(project, [{"op": "place_structure", "model": "assets/models/missing.glb", "x": 1, "y": 1}])
    project.undo()
    assert [s["id"] for s in ops.structures(project.scene())] == ["crossing"], "one undo step for the batch"


def test_the_editor_camera_keeps_the_games_view_and_its_rays_hit_what_is_drawn() -> None:
    game = Camera(32.0, 30.0, 15.0, False)
    game.target = (16.0, 12.0, 0.8)
    p = math.radians(32.0)
    assert game.eye() == pytest.approx((16.0, 12.0 - math.cos(p) * 15, 0.8 + math.sin(p) * 15)), "yaw 0: as before"
    editor = Camera(40.0, 30.0, 20.0, False, yaw=90.0)
    editor.target = (10.0, 5.0, 0.0)
    origin, direction = editor.ray(0.0, 0.0, 16 / 9)
    hit = ground_point(origin, direction)
    assert hit == pytest.approx((10.0, 5.0), abs=1e-6), "the middle of the picture is the target"
    assert editor.right() == pytest.approx((0.0, -1.0, 0.0), abs=1e-9), "turned east: right is south"


def test_picking_uses_the_drawn_triangles_and_tells_structures_from_characters() -> None:
    model = load_glb(CROSSING)
    st = parse_hd2d({"structures": [{"id": "crossing", "model": "m.glb", "x": 512, "y": 384, "rotation": 90}]}).structures[0]
    drawn = _placement(st.x / 32, st.y / 32, st.elevation / 32, st.rotation, st.scale)
    flat = [v for row in placement(st) for v in row]
    assert flat == pytest.approx([v for row in drawn for v in row]), "picking places it exactly as the renderer draws it"
    picker = Picker()
    # straight down onto the (turned) west platform's top: model (-6, 0) -> turned (0, -6) -> world (16, 6)
    hit = picker.pick((16.0, 6.0, 10.0), (0.0, 0.0, -1.0), [st], {"m.glb": model})
    assert hit is not None and hit.kind == "structure" and hit.target == "crossing" and hit.point[2] == pytest.approx(2.0)
    person = SimpleNamespace(center_x=16 * 32, bottom=1.5 * 32, width=32, height=48, mesh_entity_data={"elevation": 0})
    # looking north at the platform's south face with a person standing in front of it: the person is nearer
    hit = picker.pick((16.0, -10.0, 0.75), (0.0, 1.0, 0.0), [st], {"m.glb": model}, [person])
    assert hit is not None and hit.kind == "sprite" and hit.target is person
    behind = SimpleNamespace(center_x=16 * 32, bottom=12.0 * 32, width=32, height=48, mesh_entity_data={})
    hit = picker.pick((16.0, -10.0, 0.75), (0.0, 1.0, 0.0), [st], {"m.glb": model}, [behind])
    assert hit is not None and hit.kind == "structure", "a character hidden behind the structure isn't picked"
