"""Milestone 16 Stage 6A: the HD-2D RPG template candidate (engine.hd2d.starter_village), its starter kit
(assets/hd2d_starter) and the pieces it added: a kit installed into the model catalogue, lamp heights, and finding the
floor under a click in 3D. Headless; the playable and editable workflow is tests/test_hd2d_starter_gpu.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import project_ops as ops
from engine.hd2d import catalog
from engine.hd2d.glb import load_glb
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import NAV_HALF, World
from engine.physics_runtime import footprint
from engine.project_scaffold import create_project, ensure_starter_files
from engine.project_templates import list_templates

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "assets" / "hd2d_starter"
ROOMS = ("packs/core_regions/scenes/start.json", "packs/core_regions/scenes/cottage.json")


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("hd2d") / "Village"
    create_project(root, "Village", "hd2d_rpg")
    return root


def _rooms(project: Path) -> dict[str, dict]:
    return {rel: json.loads((project / rel).read_text(encoding="utf-8")) for rel in ROOMS}


def test_the_template_is_developer_only() -> None:
    assert "hd2d_rpg" in [t.id for t in list_templates()]
    assert "hd2d_rpg" not in [t.id for t in list_templates(launcher_only=True)], "not in the launcher until Stage 6B"


def test_the_project_has_the_kit_and_only_mesh_art(project: Path) -> None:
    listed = {a.id: a for a in catalog.assets(project)}
    kit = json.loads((KIT / "catalog.json").read_text(encoding="utf-8"))
    assert set(listed) == {m["id"] for m in kit["models"]} and len(listed) == 14
    assert all(a.catalogued and not a.missing and a.source == {"kit": "Mesh HD-2D starter kit 1",
                                                                "sha256": a.source["sha256"]} for a in listed.values())
    sprites = sorted(p.name for p in (project / "assets" / "sprites").iterdir())
    assert sprites == ["door.png", "hd2d_hero.png", "hd2d_merchant.png", "hd2d_villager.png", "starter_hero.png",
                       "starter_sign.png", "starter_villager.png"]
    assert not (project / "assets" / "sprites" / "animated_player.png").exists(), "no unverified legacy art"


def test_nothing_in_the_project_points_outside_it(project: Path) -> None:
    for path in project.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        for needle in (str(REPO), REPO.as_posix(), "tooling/", "hd2d_assets", ":\\\\", ":/"):
            assert needle not in text, f"{path.relative_to(project)} names {needle!r}"
    for rel in ROOMS:
        hd = parse_hd2d(json.loads((project / rel).read_text(encoding="utf-8"))["settings"]["hd2d"])
        for st in hd.structures:
            assert (project / st.model).is_file()
        if hd.ground and hd.ground.texture:
            assert (project / hd.ground.texture).is_file()


def test_every_character_door_and_arrival_has_somewhere_to_stand(project: Path) -> None:
    for rel, scene in _rooms(project).items():
        hd = parse_hd2d(scene["settings"]["hd2d"])
        world = World(hd, {st.model: load_glb(project / st.model) for st in hd.structures})
        for e in scene["entities"]:
            auto = (e.get("components") or {}).get("collider", {}).get("auto") or e.get("prefab_id") == "player"
            height = 32 if e.get("tag") in ("sign", "door", "spawn_point") else 48
            feet = e["y"] + (footprint(32, height)["offset_y"] if auto else 0)
            z = float(e.get("elevation", 0) or 0) / 32
            assert world.stand(e["x"] / 32, feet / 32, z, *NAV_HALF) is not None, (rel, e.get("name"), e["id"])


def test_the_village_has_what_the_starter_promises(project: Path) -> None:
    village, inside = _rooms(project).values()
    ids = {st["id"] for st in village["settings"]["hd2d"]["structures"]}
    assert {"bridge", "stairs_west", "stairs_east", "cottage", "shop", "lamp_west"} <= ids
    hd = parse_hd2d(village["settings"]["hd2d"])
    world = World(hd, {st.model: load_glb(project / st.model) for st in hd.structures})
    bridge = next(st for st in hd.structures if st.id == "bridge")
    under = world.stand(bridge.x / 32, bridge.y / 32, 0.0, *NAV_HALF)
    on = world.stand(bridge.x / 32, bridge.y / 32, 2.0, *NAV_HALF)
    assert under == (0.0, "ground") and on is not None and on[1] == "bridge/col_deck", "walk across or under it"
    talkers = {e.get("name") for e in village["entities"] + inside["entities"] if "Dialogue" in (e.get("behaviours") or [])}
    assert {"Elder", "Mara", "Sign", "Tomas"} <= talkers
    for e in village["entities"] + inside["entities"]:  # each character says its own lines
        dialogue = (e.get("behaviour_config") or {}).get("Dialogue", {}).get("dialogue")
        if dialogue and e.get("name") != "Sign":
            assert dialogue["speaker"] == e["name"], (e["name"], dialogue["speaker"])
    lines = [(e.get("behaviour_config") or {}).get("Dialogue", {}).get("dialogue", {}).get("nodes", {}).get("root", {}).get("text")
             for e in village["entities"] + inside["entities"] if "Dialogue" in (e.get("behaviours") or [])]
    assert len(set(lines)) == len(lines), "nobody shares another's lines"
    doors = [e for e in village["entities"] + inside["entities"] if e.get("tag") == "door"]
    assert sorted(d["behaviour_config"]["SceneTransition"]["target_scene"] for d in doors) == ["cottage", "start"]
    lamps = [light for light in village["lights"] if light.get("type") != "ambient"]
    assert len(lamps) == 2 and all(light["elevation"] == 80.0 for light in lamps)
    assert village["settings"]["hd2d"]["sun"] and "player" in (e.get("prefab_id") for e in village["entities"])
    assert parse_hd2d(village["settings"]["hd2d"]).sky == parse_hd2d({}).sky, "daylight outside"
    assert max(parse_hd2d(inside["settings"]["hd2d"]).sky) < 0.1, "dark around the cottage's inside"
    with pytest.raises(ValueError, match="sky must be a colour"):
        parse_hd2d({"sky": "blue"})


def test_existing_templates_keep_their_files(tmp_path: Path) -> None:
    create_project(tmp_path / "blank", "Blank", "blank")
    assert (tmp_path / "blank" / "assets" / "sprites" / "starter_hero.png").is_file(), "2D templates keep their art"
    assert not (tmp_path / "blank" / "assets" / "sprites" / "animated_player.png").exists(), "and no unverified sheet"
    assert not (tmp_path / "blank" / "assets" / "models").exists()


def test_studio_never_adds_the_legacy_sheet_to_a_project_that_doesnt_use_it(project: Path, tmp_path: Path) -> None:
    ensure_starter_files(project)
    assert not (project / "assets" / "sprites" / "animated_player.png").exists()
    old = tmp_path / "old"
    create_project(old, "Old", "blank")
    assert not (old / "assets" / "sprites" / "animated_player.png").exists()
    prefabs = old / "assets" / "prefabs.json"  # the shared player lives here
    prefabs.write_text(prefabs.read_text(encoding="utf-8").replace("starter_hero.png", "animated_player.png"),
                       encoding="utf-8")
    ensure_starter_files(old)
    assert (old / "assets" / "sprites" / "animated_player.png").is_file(), "an older project that names it gets it"


def test_a_kit_never_overwrites(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    catalog.import_model(root, REPO / "tooling" / "hd2d_assets" / "cottage.glb")  # a model called 'cottage'
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    with pytest.raises(catalog.CatalogError, match="'cottage' is already in this project"):
        catalog.install_kit(root, KIT)
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == before, "nothing was added"


def test_a_lamp_has_a_height() -> None:
    scene, index = ops.add_light({"entities": []}, 64, 64)
    scene = ops.set_light(scene, index, elevation=80, intensity=1.6)
    assert scene["lights"][index]["elevation"] == 80.0 and scene["lights"][index]["intensity"] == 1.6
    with pytest.raises(ops.OpError):
        ops.set_light(scene, index, elevation=-1)


def test_a_click_ray_finds_the_nearest_floor(project: Path) -> None:
    scene = _rooms(project)[ROOMS[0]]
    hd = parse_hd2d(scene["settings"]["hd2d"])
    world = World(hd, {st.model: load_glb(project / st.model) for st in hd.structures})
    bridge = next(st for st in hd.structures if st.id == "bridge")
    x, y = bridge.x / 32, bridge.y / 32
    down = world.walkable_hit((x, y, 10.0), (0.0, 0.0, -1.0))
    assert down is not None and down[1] == "bridge/col_deck" and down[0][2] == pytest.approx(2.0), "the deck first"
    up = world.walkable_hit((x, y, 1.0), (0.0, 0.0, -1.0))
    assert up is not None and up[1] == "ground", "from under the deck: the ground"
    assert world.walkable_hit((x, y, 10.0), (0.0, 0.0, 1.0)) is None, "looking up: nothing"


def test_the_template_follows_the_hd2d_visual_standard(project: Path) -> None:
    """docs/reviews/milestone16_hd2d_visual_direction.md: a long-lens camera at a fixed angle that never shows past
    the room, the art at an exact 2x outdoors and 3x indoors (720 lines), the sun from the south-west, and the
    characters (and Studio's Person) in the HD-2D style."""
    import math

    village, inside = _rooms(project).values()
    for scene, pitch, view, bounds in ((village, 30.0, 11.25, [0.0, 0.0, 1280.0, 1408.0]),
                                       (inside, 55.0, 7.5, [144.0, 96.0, 368.0, 288.0])):
        camera = parse_hd2d(scene["settings"]["hd2d"]).camera
        assert (camera.pitch, camera.fov, camera.ortho, camera.follow) == (pitch, 12.0, False, "player")
        assert 2 * camera.distance * math.tan(math.radians(camera.fov / 2)) == pytest.approx(view, abs=0.01)
        assert camera.bounds == tuple(bounds)
    assert village["settings"]["hd2d"]["sun"]["direction"] == [-0.45, -0.55, 0.70], "walls facing the camera lit"
    sheets = {(e.get("name"), e.get("sprite")) for e in village["entities"] + inside["entities"]
              if e.get("tag") == "npc"}  # the player is a thin reference to the player prefab, below
    prefabs = json.loads((project / "assets" / "prefabs.json").read_text(encoding="utf-8"))
    sheets |= {(p["id"], p["entity"].get("sprite")) for p in prefabs if p.get("id") in ("person", "player")}
    assert all(sheet and "/hd2d_" in sheet for _name, sheet in sheets), sheets
    assert {name for name, _sheet in sheets} >= {"Elder", "Mara", "Tomas", "person", "player"}
