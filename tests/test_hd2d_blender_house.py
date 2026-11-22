"""M2-1: one Blender building, imported and safely reimported. ``tooling/hd2d_assets/house.glb`` and ``house_v2.glb``
are Blender's exports of ``build_house.py`` (CI has no Blender; see docs/reviews/m2_blender_building/README.md). The
house is imported through the project's catalogue, placed twice in an HD-2D room, edited in Blender (north wall 1 m
north, roof higher and terracotta) and reimported: both copies change, collision follows, no other file changes, and
a broken export or a failed swap leaves the project byte-identical."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engine import project_ops as ops
from engine.hd2d import catalog, glb, settings, world
from engine.hd2d.catalog import CatalogError

pytestmark = pytest.mark.integration  # writes projects and previews

ASSETS = Path(__file__).resolve().parents[1] / "tooling" / "hd2d_assets"
HOUSE, HOUSE_V2, STAIRS = ASSETS / "house.glb", ASSETS / "house_v2.glb", ASSETS / "stairs.glb"
COLLIDERS = {"col_floor": "solid", "col_lintel": "wall", **{f"col_wall_{n}": "wall" for n in
                                                          ("north", "west", "east", "south_w", "south_e")}}
COPIES = {"house": (5.0, 10.0), "house_2": (15.0, 10.0)}  # where place_structure puts them, in metres
KEEPER = {"id": "keeper", "name": "Keeper", "x": 15.0 * 32, "y": (10.0 + 2.35) * 32}  # behind house_2: v2's north wall


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, Path]:
    """A project with the stairs and the house imported, the house placed twice in ``village`` and an unrelated room;
    and the creator's export folder (outside the project) holding ``house.glb`` as first exported."""
    root, art = tmp_path / "project", tmp_path / "blender_exports"
    root.mkdir()
    art.mkdir()
    (art / "house.glb").write_bytes(HOUSE.read_bytes())
    catalog.import_model(root, STAIRS, category="Stairs and bridges")
    house = catalog.import_model(root, art / "house.glb", category="Buildings")
    village: dict = {"settings": {"hd2d": {"ground": {"from": [0, 0], "to": [640, 640]}}}, "entities": [KEEPER]}
    for x, y in COPIES.values():
        village, _sid = ops.place_structure(village, house.model, x * 32, y * 32)
    other = {"settings": {"hd2d": {"ground": {"from": [0, 0], "to": [320, 320]},
                                   "structures": [{"id": "stairs", "model": "assets/models/stairs.glb", "x": 160, "y": 160}]}}}
    (root / "scenes").mkdir()
    for name, scene in (("village", village), ("other", other)):
        (root / "scenes" / f"{name}.json").write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return root, art


def _rooms(root: Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "scenes").glob("*.json"))}


def _world(root: Path) -> world.World:
    """The village's collision as the game builds it, from the files now in the project."""
    hd2d = settings.parse_hd2d(_rooms(root)["village"]["settings"]["hd2d"])
    return world.World(hd2d, {st.model: glb.load_glb(root / st.model) for st in hd2d.structures})


def _stand(w: world.World, sid: str, dx: float, dy: float, z: float = 0.1) -> tuple[float, str] | None:
    x, y = COPIES[sid]
    found = w.stand(x + dx, y + dy, z, *world.NAV_HALF)
    return None if found is None else (round(found[0], 2), found[1])


def test_the_committed_house_is_blenders_export_of_the_build_script() -> None:
    for path, deep, ridge, roof in ((HOUSE, 3.0, 3.2, "roof_slate"), (HOUSE_V2, 4.0, 3.9, "roof_terracotta")):
        doc, _binary = glb.split_glb(path.read_bytes())
        assert doc["asset"]["generator"].startswith("Khronos glTF Blender I/O")
        assert [m["name"] for m in doc["materials"]] == ["floorboards", "stone", "timber", roof]
        model, report = glb.inspect_glb(path)
        assert {c.node: c.kind for c in model.colliders} == COLLIDERS
        assert report.collision == {"solid": 1, "floor": 0, "wall": 6} and report.floors == ["col_floor"]
        lo, hi = model.bounds()
        assert [round(v, 2) for v in (*lo, *hi)] == [-2.25, -1.75, 0.0, 2.25, deep - 1.25, ridge]
        assert len(path.read_bytes()) < 32_000, "keep the committed exports small"


def test_reimport_updates_every_copy_and_collision_and_nothing_else(project: tuple[Path, Path]) -> None:
    root, art = project
    before_world = _world(root)
    for sid in COPIES:
        assert _stand(before_world, sid, 0.0, 0.0) == (0.1, f"{sid}/col_floor"), "on the floor, through the doorway's room"
        assert _stand(before_world, sid, 0.0, 2.0, z=0.0) == (0.0, "ground"), "behind the house: open ground"
        assert _stand(before_world, sid, 0.0, 1.4) is None, "inside the north wall"
    before = _files(root)

    (art / "house.glb").write_bytes(HOUSE_V2.read_bytes())  # the creator edits the house in Blender and exports again
    plan = catalog.plan_reimport(root, "house", rooms=_rooms(root))
    assert plan.ok and plan.inspection.source == art / "house.glb", "the recorded source is the default"
    assert plan.changes == ["Size 4.5 x 3.5 x 3.2 m -> 4.5 x 4.5 x 3.9 m.",
                            "Collider 'col_floor' (solid) changed shape.",
                            "Collider 'col_wall_east' (wall) changed shape.",
                            "Collider 'col_wall_north' (wall) changed shape.",
                            "Collider 'col_wall_west' (wall) changed shape."]
    assert any("Keeper" in w and "nowhere to stand" in w for w in plan.warnings), "the keeper is in the moved wall"
    assert _files(root) == before, "planning writes nothing"

    done = catalog.reimport_model(root, "house", rooms=_rooms(root))
    after = _files(root)
    changed = sorted(k for k in after.keys() | before.keys() if after.get(k) != before.get(k))
    assert changed == ["assets/models/catalog.json", "assets/models/house.glb", "assets/models/previews/house.png"]
    assert after["assets/models/house.glb"] == HOUSE_V2.read_bytes(), "Closest textures, flat roof: stored as exported"

    entries = {e["id"]: e for e in json.loads(after[catalog.CATALOG])["models"]}
    old_entries = {e["id"]: e for e in json.loads(before[catalog.CATALOG])["models"]}
    assert entries["stairs"] == old_entries["stairs"], "the other model's entry is untouched"
    _model, report = glb.inspect_glb(root / "assets/models/house.glb")
    assert (entries["house"]["collision"], entries["house"]["floors"]) == (report.collision, report.floors)
    assert {k: v for k, v in entries["house"].items() if k != "source"} == \
           {k: v for k, v in old_entries["house"].items() if k != "source"}, "id, name, preview path and facts kept"
    assert entries["house"]["source"]["sha256"] != old_entries["house"]["source"]["sha256"]
    assert (done.asset.id, done.asset.model) == ("house", "assets/models/house.glb")

    after_world = _world(root)
    for sid in COPIES:  # both copies: the scene still names the one file, which now holds the edit
        assert _stand(after_world, sid, 0.0, 0.0) == (0.1, f"{sid}/col_floor")
        assert _stand(after_world, sid, 0.0, 1.4) == (0.1, f"{sid}/col_floor"), "the old wall's place is floor now"
        assert _stand(after_world, sid, 0.0, 2.0) == (0.1, f"{sid}/col_floor"), "the house reaches 1 m further north"
        assert _stand(after_world, sid, 0.0, 2.4) is None, "inside the moved north wall"
        assert _stand(after_world, sid, 0.0, 3.0, z=0.0) == (0.0, "ground")
    assert after_world.walkable() < before_world.walkable()


@pytest.mark.parametrize("damage", ["cut off", "not a glb"])
def test_a_broken_export_is_refused_and_the_project_is_unchanged(project: tuple[Path, Path], damage: str) -> None:
    root, art = project
    before = _files(root)
    data = HOUSE_V2.read_bytes()
    (art / "house.glb").write_bytes(data[: len(data) // 2] if damage == "cut off" else b"not a model")
    plan = catalog.plan_reimport(root, "house", rooms=_rooms(root))
    assert not plan.ok and plan.inspection.problem
    with pytest.raises(CatalogError):
        catalog.reimport_model(root, "house", rooms=_rooms(root))
    assert _files(root) == before


def test_a_swap_that_fails_part_way_is_rolled_back(project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    root, _art = project
    before = _files(root)
    real, calls = os.replace, []

    def fail_on_third(src, dst):  # noqa: ANN001 - os.replace's arguments
        calls.append(dst)
        if len(calls) == 3:
            raise OSError("disk full (test)")
        real(src, dst)

    monkeypatch.setattr(os, "replace", fail_on_third)
    with pytest.raises(OSError, match="disk full"):
        catalog.reimport_model(root, "house", HOUSE_V2, rooms=_rooms(root))
    assert len(calls) == 3 and _files(root) == before, "the model and preview swapped in are put back"
