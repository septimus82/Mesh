"""Milestone 16 Stage 5B, proven in a hidden window: a creator's Blender models imported, browsed, placed, edited,
reimported and play-tested through Mesh Studio's own window events (tooling/hd2d_asset_pipeline_demo.py), and pixel
art drawn sharp. GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),  # Studio's text fields (pre-existing)
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
STAIRS = REPO / "tooling" / "hd2d_assets" / "stairs.glb"
NEAREST = 9728


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    import hd2d_asset_pipeline_demo as demo

    report = demo.check(tmp_path_factory.mktemp("pipeline"))
    return {s["step"]: s for s in report["steps"]} | {"performance": report["performance"], "gl": report["gl"]}


def test_models_import_through_studio_with_their_report(run: dict) -> None:
    imp = run["import"]
    assert "Collision: 1 solid, 6 wall." in imp["cottage_report"]
    assert "Place in scene" in imp["cottage_page_after_import"]
    assert any(line.startswith("Made sharp: ") for line in imp["stairs_report"])
    by_id = {e["id"]: e for e in imp["catalog"]}
    assert by_id["cottage"]["category"] == "Buildings" and by_id["cottage"]["license"].startswith("Original")
    assert by_id["stairs"]["collision"] == {"solid": 2, "floor": 0, "wall": 2} and by_id["stairs"]["pixels"] == "sharp"
    assert imp["files"] == ["assets/models/catalog.json", "assets/models/cottage.glb", "assets/models/previews/cottage.png",
                            "assets/models/previews/stairs.png", "assets/models/stairs.glb", "assets/models/stone_crossing.glb"]


def test_the_browser_lists_searches_and_shows_details(run: dict) -> None:
    browse = run["browse"]
    assert {t.split("  ")[0] for t in browse["listed"]} >= {"Cottage", "Stairs", "Stone Crossing"}
    assert {t.split("  ")[0] for t in browse["search_stair"]} == {"Stairs", "Stairs and bridges"}
    assert any("copies in this room" in t for t in browse["details"])


def test_copies_share_the_model_and_move_and_turn(run: dict) -> None:
    place = run["place_move_turn"]
    a, b, s = place["ids"]
    assert (a, b, s) == ("cottage", "cottage_2", "stairs") and place["one_file_for_both_cottages"]
    assert place["picked_by_clicking_its_roof"] == b
    assert place["moved_turned"]["rotation"] == 90.0 and place["moved_turned"]["x"] != place["placed"][b]["x"]


def test_pixel_art_is_sampled_nearest_in_edit_and_in_play(run: dict) -> None:
    assert run["place_move_turn"]["stairs_texture_filters_in_edit"] == [[NEAREST, NEAREST]]
    assert run["play"]["stairs_texture_filters_in_play"] == [[NEAREST, NEAREST]]


def test_an_ai_proposes_by_catalogue_id_and_the_person_accepts(run: dict) -> None:
    ai = run["ai"]
    assert ["stairs", "Stairs and bridges"] in [list(m) for m in ai["models_listed_for_ai"]]
    assert any("places structure 'stairs_2'" in line for line in ai["summary"])
    assert ai["refused"] and "no model 'tower'" in ai["refused"]["message"]
    assert ai["baker"] is not None and ai["accepted_structures"] == 5


def test_save_and_reopen_keep_everything(run: dict) -> None:
    assert run["save_reopen"]["same_structures"] is True


def test_reimport_updates_every_copy_and_warns_first(run: dict) -> None:
    re_ = run["reimport"]
    assert "New solid collider 'col_porch'." in re_["plan"] and "New wall collider 'col_hearth'." in re_["plan"]
    assert any("would have" in t and "nowhere to stand" in t.replace("\n", " ") for t in re_["plan"]), "the hearth"
    assert re_["porch_floors"] == ["cottage/col_porch", "cottage_2/col_porch"] and re_["ids_and_places_kept"]
    assert re_["stand_on_new_porch"][1] == "cottage/col_porch" and re_["stand_in_new_hearth"] is None
    before, after = re_["gl_before"], re_["gl_after"]
    assert after["framebuffer"] == before["framebuffer"] and after["program"] == before["program"]
    assert after["texture"] - before["texture"] == 1, "one new material (the porch's cobbles); the old ones freed"


def test_a_broken_export_is_refused_and_undo_works(run: dict) -> None:
    fail = run["failure_and_undo"]
    assert fail["refusal"] and fail["reimport_button_disabled"] and fail["project_files_unchanged"]
    assert fail["stairs_dragged"]["x"] != fail["stairs_before"]["x"] and fail["stairs_after_undo"] == fail["stairs_before"]


def test_play_walks_up_the_imported_staircase(run: dict) -> None:
    landing = run["play"]["walk"][-1]
    assert landing["elevation_m"] == pytest.approx(2.0, abs=0.05) and landing["floor"] == "stairs/col_landing"
    assert run["play"]["mode_after_stop"] == "edit"


def test_no_gpu_objects_pile_up(run: dict) -> None:
    gl = run["gl"]
    assert gl["end"]["framebuffer"] <= gl["start"]["framebuffer"] and gl["end"]["program"] <= gl["start"]["program"] + 1


def test_smooth_exports_blur_and_sharp_copies_do_not(tmp_path: Path) -> None:
    """The same staircase, drawn by the game from Blender's smooth (Linear) export and from the sharpened copy, with
    the same camera: blurring makes in-between colours, so the smooth one shows many more distinct colours."""
    import hd2d_demo

    from engine.hd2d import catalog, glb

    project = hd2d_demo.build(tmp_path / "game")
    sharp = catalog.import_model(project, STAIRS, name="sharp")
    doc, binary = glb.split_glb(STAIRS.read_bytes())
    doc.setdefault("asset", {})["extras"] = {"copy": "smooth"}  # other bytes: not a duplicate of the first import
    smooth_source = tmp_path / "stairs_smooth.glb"
    smooth_source.write_bytes(glb.join_glb(doc, binary))
    smooth = catalog.import_model(project, smooth_source, name="smooth", pixels="as exported")
    scene_path = project / hd2d_demo.SCENES / "start.json"
    base = json.loads(scene_path.read_text(encoding="utf-8"))
    spawn = next(e for e in base["entities"] if e.get("prefab_id") == "player")
    colours = {}
    game = hd2d_demo.HiddenGame(project, size=(640, 480))
    try:
        for label, model in (("sharp", sharp.model), ("smooth", smooth.model)):
            scene = json.loads(json.dumps(base))
            hd = scene["settings"]["hd2d"]
            hd["structures"] = [{"id": "steps", "model": model, "x": spawn["x"], "y": spawn["y"] + 96}]
            hd["camera"] = {"pitch": 35, "fov": 30, "distance": 6, "follow": "player"}
            scene_path.write_text(json.dumps(scene), encoding="utf-8")
            game.load(f"{hd2d_demo.SCENES}/start.json")
            game.step(30)
            colours[label] = len(set(game.draw().convert("RGB").getdata()))
    finally:
        game.close()
    assert colours["smooth"] > 1.5 * colours["sharp"], colours
