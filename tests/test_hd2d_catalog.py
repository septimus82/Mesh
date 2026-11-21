"""Milestone 16 Stage 5B: a project's HD-2D model catalogue (engine.hd2d.catalog): importing Blender models safely,
listing them (old projects included), sharp pixel art, previews, reimporting with a report, and never leaving a
project half-written. Uses the original demonstration models in tooling/hd2d_assets (see PROVENANCE.md)."""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d import catalog, glb
from engine.hd2d.catalog import CatalogError

pytestmark = pytest.mark.fast

ASSETS = Path(__file__).resolve().parents[1] / "tooling" / "hd2d_assets"
COTTAGE, COTTAGE_V2, STAIRS, CROSSING = (ASSETS / f"{n}.glb" for n in ("cottage", "cottage_v2", "stairs", "stone_crossing"))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


@pytest.fixture
def art(tmp_path: Path) -> Path:
    """The creator's export folder, outside the project."""
    folder = tmp_path / "blender_exports"
    folder.mkdir()
    return folder


def _variant(src: Path, out: Path, change) -> Path:  # noqa: ANN001 - a function editing the glTF document
    doc, binary = glb.split_glb(src.read_bytes())
    change(doc)
    out.write_bytes(glb.join_glb(doc, binary))
    return out


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _samplers(path: Path) -> list[int]:
    doc, _ = glb.split_glb(path.read_bytes())
    return [doc["samplers"][t["sampler"]].get("magFilter", glb.GL_NEAREST) for t in doc["textures"]]


# ------------------------------------------------------------------------------------------------- import
def test_import_copies_the_model_with_its_preview_and_catalogue_entry(root: Path, art: Path) -> None:
    source = art / "cottage.glb"
    source.write_bytes(COTTAGE.read_bytes())
    asset = catalog.import_model(root, source, name="Cottage", category="Buildings", license="Original (test)")

    assert (asset.id, asset.model, asset.preview) == ("cottage", "assets/models/cottage.glb", "assets/models/previews/cottage.png")
    assert (root / asset.model).read_bytes() == COTTAGE.read_bytes(), "Closest textures: the bytes are kept as exported"
    assert asset.collision == {"solid": 1, "floor": 0, "wall": 6} and asset.floors == ["col_floor"]
    entry = json.loads((root / catalog.CATALOG).read_text(encoding="utf-8"))["models"][0]
    assert entry["source"]["file"] == str(source) and len(entry["source"]["sha256"]) == 64
    assert entry["license"] == "Original (test)" and entry["category"] == "Buildings"
    from PIL import Image

    with Image.open(root / asset.preview) as preview:
        assert preview.size == (160, 120) and preview.getbbox() is not None


def test_import_never_overwrites_and_refuses_the_same_file_twice(root: Path, art: Path) -> None:
    (root / catalog.MODELS_DIR).mkdir(parents=True)
    (root / catalog.MODELS_DIR / "cottage.glb").write_bytes(CROSSING.read_bytes())  # a different model, by hand
    first = catalog.import_model(root, COTTAGE)
    assert first.id == "cottage_2", "an existing file's name is taken"
    assert (root / catalog.MODELS_DIR / "cottage.glb").read_bytes() == CROSSING.read_bytes(), "untouched"
    with pytest.raises(CatalogError, match="already imported, as 'cottage_2'"):
        catalog.import_model(root, COTTAGE)
    renamed = art / "my_house.glb"
    renamed.write_bytes(COTTAGE.read_bytes())
    with pytest.raises(CatalogError, match="already imported"):
        catalog.import_model(root, renamed)  # the same bytes under another name


@pytest.mark.parametrize(("make", "message"), [
    (lambda art: art / "missing.glb", "There is no file"),
    (lambda art: (art / "scene.gltf").write_text("{}") and art / "scene.gltf", "glTF Binary (.glb)"),
    (lambda art: (art / "notes.txt").write_text("hi") and art / "notes.txt", "isn't a .glb"),
    (lambda art: (art / "broken.glb").write_bytes(COTTAGE.read_bytes()[:400]) and art / "broken.glb", "damaged"),
    (lambda art: (art / "junk.glb").write_bytes(b"not a model") and art / "junk.glb", "not a GLB"),
    (lambda art: _variant(COTTAGE, art / "skinned.glb", lambda d: d.update(skins=[{"joints": [0]}])), "armatures"),
    (lambda art: _variant(COTTAGE, art / "draco.glb", lambda d: d.update(extensionsRequired=["KHR_draco_mesh_compression"])),
     "Draco"),
])
def test_import_refuses_unusable_files_and_writes_nothing(root: Path, art: Path, make, message: str) -> None:  # noqa: ANN001
    source = make(art)
    found = catalog.inspect_source(root, source)
    assert not found.ok and message in (found.problem or "")
    with pytest.raises(CatalogError, match=message.replace("(", r"\(").replace(")", r"\)")):
        catalog.import_model(root, source)
    assert _files(root) == {}, "a refused import writes nothing"


def test_a_model_already_inside_the_project_is_catalogued_where_it_is(root: Path) -> None:
    inside = root / "art" / "stairs.glb"
    inside.parent.mkdir()
    inside.write_bytes(STAIRS.read_bytes())
    asset = catalog.import_model(root, inside, pixels="as exported")
    assert asset.model == "art/stairs.glb" and not (root / catalog.MODELS_DIR / "stairs.glb").exists()


def test_keep_pixels_sharp_fixes_smooth_textures_in_the_copy_only(root: Path, art: Path) -> None:
    source = art / "stairs.glb"
    source.write_bytes(STAIRS.read_bytes())
    found = catalog.inspect_source(root, source)
    assert sorted(found.sharpened) == ["cobbles", "floorboards", "timber"]
    assert found.report is not None
    assert any("Smooth (Linear) texture filtering" in w for w in found.report.warnings)
    asset = catalog.import_model(root, source)
    assert set(_samplers(root / asset.model)) == {glb.GL_NEAREST}
    assert all(p.material.nearest for p in glb.load_glb(root / asset.model).parts)
    assert source.read_bytes() == STAIRS.read_bytes(), "the creator's export is never changed"
    assert asset.pixels == "sharp"

    smooth = catalog.import_model(root, COTTAGE_V2, name="Smooth test")  # Closest already: nothing to fix
    assert (root / smooth.model).read_bytes() == COTTAGE_V2.read_bytes()


def test_as_exported_keeps_blenders_filtering(root: Path) -> None:
    asset = catalog.import_model(root, STAIRS, pixels="as exported")
    assert glb.GL_LINEAR in _samplers(root / asset.model)


def test_models_cannot_be_written_through_a_link_out_of_the_project(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (root / "assets").mkdir()
    link = root / catalog.MODELS_DIR
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(outside), str(link))
    with pytest.raises(CatalogError, match="outside the project"):
        catalog.import_model(root, COTTAGE)
    assert list(outside.iterdir()) == []


# ------------------------------------------------------------------------------------------------- listing
def test_older_projects_list_their_models_without_a_catalogue(root: Path) -> None:
    (root / catalog.MODELS_DIR).mkdir(parents=True)
    (root / catalog.MODELS_DIR / "stone_crossing.glb").write_bytes(CROSSING.read_bytes())
    (root / "exports").mkdir()
    (root / "exports" / "built.glb").write_bytes(CROSSING.read_bytes())  # build output: not a model
    listed = catalog.assets(root)
    assert [(a.id, a.model, a.name, a.catalogued) for a in listed] == [
        ("stone_crossing", "assets/models/stone_crossing.glb", "Stone Crossing", False)]
    assert not (root / catalog.CATALOG).exists(), "listing writes nothing"
    scene, sid = ops.place_structure({"settings": {"hd2d": {}}}, "assets/models/stone_crossing.glb", 64, 64)
    assert sid == "stone_crossing", "placing works as before"


def test_copies_share_one_file_and_a_missing_file_is_reported(root: Path) -> None:
    asset = catalog.import_model(root, COTTAGE)
    scene: dict = {"settings": {"hd2d": {}}}
    for x in (64, 256, 448):
        scene, _sid = ops.place_structure(scene, asset.model, x, 64)
    assert {s["model"] for s in ops.structures(scene)} == {asset.model}
    assert len(list((root / catalog.MODELS_DIR).glob("*.glb"))) == 1
    (root / asset.model).unlink()
    assert catalog.find(root, "cottage").missing


def test_a_corrupt_catalogue_is_reported_not_guessed(root: Path) -> None:
    (root / catalog.MODELS_DIR).mkdir(parents=True)
    (root / catalog.CATALOG).write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogError, match="catalog.json can't be read"):
        catalog.assets(root)


def test_properties_change_and_are_validated(root: Path) -> None:
    catalog.import_model(root, COTTAGE)
    asset = catalog.set_properties(root, "cottage", name="Baker's cottage", rotation="450", scale=2, notes="by the well")
    assert (asset.name, asset.rotation, asset.scale, asset.notes) == ("Baker's cottage", 90.0, 2.0, "by the well")
    for bad in ({"scale": 0}, {"scale": float("nan")}, {"rotation": "east"}, {"colour": "red"}):
        with pytest.raises(CatalogError):
            catalog.set_properties(root, "cottage", **bad)


# ------------------------------------------------------------------------------------------------- reimport
def _room(model: str, *entities: dict) -> dict:
    return {"settings": {"hd2d": {"structures": [{"id": "home", "model": model, "x": 320, "y": 320}],
                                  "ground": {"from": [0, 0], "to": [640, 640]}}}, "entities": list(entities)}


def test_reimport_reports_what_changes_and_keeps_every_copy(root: Path, art: Path) -> None:
    source = art / "cottage.glb"
    source.write_bytes(COTTAGE.read_bytes())
    asset = catalog.import_model(root, source)
    # a character standing inside the cottage where the edited version puts its hearth (east wall, model x 1.9 m)
    room = _room(asset.model, {"id": "baker", "name": "Baker", "x": 320 + 1.9 * 32, "y": 320})
    before_room = json.dumps(room, sort_keys=True)
    source.write_bytes(COTTAGE_V2.read_bytes())  # the creator edits it in Blender and exports again
    plan = catalog.plan_reimport(root, "cottage", rooms={"start": room})
    assert "New solid collider 'col_porch'." in plan.changes and "New wall collider 'col_hearth'." in plan.changes
    assert any(line.startswith("Size 5.6 x 4.6") for line in plan.changes)
    assert any("Baker" in w and "nowhere to stand" in w for w in plan.warnings)
    assert (root / asset.model).read_bytes() == COTTAGE.read_bytes(), "planning writes nothing"

    done = catalog.reimport_model(root, "cottage", rooms={"start": room})
    assert (root / asset.model).read_bytes() == COTTAGE_V2.read_bytes()
    assert done.asset.id == "cottage" and done.asset.model == asset.model
    assert sorted(done.asset.floors) == ["col_floor", "col_porch"]
    assert json.dumps(room, sort_keys=True) == before_room, "scenes are never edited by a reimport"


def test_a_failed_reimport_leaves_the_project_exactly_as_it_was(root: Path, art: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog.import_model(root, COTTAGE)
    before = _files(root)
    broken = art / "cottage.glb"
    broken.write_bytes(b"glTF" + struct.pack("<II", 2, 20) + b"\0" * 8)
    with pytest.raises(CatalogError):
        catalog.reimport_model(root, "cottage", broken)
    assert _files(root) == before

    calls: list[str] = []
    real = os.replace

    def fail_on_second(src, dst):  # noqa: ANN001 - os.replace's arguments
        calls.append(str(dst))
        if len(calls) == 2:
            raise OSError("disk full (test)")
        real(src, dst)

    monkeypatch.setattr(os, "replace", fail_on_second)
    with pytest.raises(OSError, match="disk full"):
        catalog.reimport_model(root, "cottage", COTTAGE_V2)
    assert _files(root) == before, "the files swapped before the failure are put back, staged files removed"


def test_reimporting_a_model_from_before_the_catalogue_gives_it_an_entry(root: Path) -> None:
    (root / catalog.MODELS_DIR).mkdir(parents=True)
    (root / catalog.MODELS_DIR / "house.glb").write_bytes(COTTAGE.read_bytes())
    done = catalog.reimport_model(root, "house", COTTAGE_V2)
    assert done.asset.catalogued and done.asset.model == "assets/models/house.glb" and done.asset.preview


# ------------------------------------------------------------------------------------------------- reading GLBs
def test_flat_blender_colours_are_drawn_not_grey(tmp_path: Path) -> None:
    def flat(doc: dict) -> None:
        pbr = doc["materials"][0]["pbrMetallicRoughness"]
        pbr.pop("baseColorTexture")
        pbr["baseColorFactor"] = [0.5, 0.0, 0.0, 1.0]

    model = glb.load_glb(_variant(COTTAGE, tmp_path / "flat.glb", flat))
    images = [p.material.image for p in model.parts if p.material.name == model.parts[0].material.name]
    assert images[0] is not None and images[0].getpixel((0, 0)) == (188, 0, 0, 255)  # 0.5 linear is 188 in sRGB


def test_the_import_report_warns_about_what_mesh_ignores(tmp_path: Path) -> None:
    def extras(doc: dict) -> None:
        doc["extensionsUsed"] = ["KHR_texture_transform", "KHR_materials_specular"]
        doc["cameras"] = [{"type": "perspective", "perspective": {"yfov": 0.8, "znear": 0.1}}]
        doc["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"] = doc["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]

    _model, report = glb.inspect_glb(_variant(COTTAGE, tmp_path / "extras.glb", extras))
    text = " ".join(report.warnings)
    assert "texture transforms" in text and "Ignored: 1 cameras" in text and "Vertex colours" in text
    assert "specular" not in text, "PBR extras Blender writes are harmless"


def test_previews_are_deterministic_pictures_of_the_textured_model() -> None:
    from engine.hd2d.thumbnail import render

    model = glb.load_glb(COTTAGE)
    first, second = render(model), render(model)
    assert first.tobytes() == second.tobytes()
    assert first.getpixel((0, 0))[3] == 0, "transparent around the model"
    colours = {c for c in first.getdata() if c[3]}
    assert len(colours) > 20, "textured, not flat"


# ------------------------------------------------------------------------------------------------- Studio project + AI
def test_studio_project_imports_and_ai_tools_place_by_catalogue_id(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Models", "blank")
    project = Project.open(root, "packs/core_regions/worlds/main.json")
    assert project is not None
    start = project.current
    project.edit_scene(lambda s: {**s, "settings": {**(s.get("settings") or {}), "hd2d": {}}}, start)
    asset = project.import_model(STAIRS, category="Stairs")
    assert "assets/models/previews/stairs.png" not in project.images(), "previews aren't pictures for objects"

    listed = authoring.models(project)
    assert [(m["id"], m["category"], m["collision"]) for m in listed] == [("stairs", "Stairs", {"solid": 2, "floor": 0, "wall": 2})]
    authoring.apply(project, [{"op": "place_structure", "model": "stairs", "x": 160, "y": 160}])
    assert ops.structures(project.scene(start))[0]["model"] == asset.model
    with pytest.raises(authoring.ChangeError, match="no model 'tower'"):
        authoring.apply(project, [{"op": "place_structure", "model": "tower", "x": 160, "y": 160}])
    with pytest.raises(ops.OpError, match="already imported"):
        project.import_model(STAIRS)


def test_damaged_glbs_are_refused_with_a_reason_never_another_error(tmp_path: Path) -> None:
    """Seeded damage to the glTF description (keys removed, values of the wrong type, indices out of range):
    reading it either works or raises GlbError naming the file, never KeyError/IndexError/TypeError."""
    import random

    doc0, binary = glb.split_glb(COTTAGE.read_bytes())
    rng = random.Random(55)
    junk = [None, -1, 10**6, "x", [], {}, 1.5]
    outcomes = {"ok": 0, "refused": 0}
    for i in range(150):
        doc = json.loads(json.dumps(doc0))
        for _ in range(rng.randint(1, 3)):
            section = rng.choice([k for k in ("nodes", "meshes", "accessors", "bufferViews", "materials", "textures",
                                              "images", "samplers", "scenes") if doc.get(k)])
            item = rng.choice(doc[section])
            if isinstance(item, dict) and item:
                key = rng.choice(list(item))
                if rng.random() < 0.4:
                    del item[key]
                else:
                    item[key] = rng.choice(junk)
        path = tmp_path / f"damaged_{i}.glb"
        path.write_bytes(glb.join_glb(doc, binary))
        try:
            glb.load_glb(path)
            outcomes["ok"] += 1
        except glb.GlbError as err:
            assert str(path) in str(err)
            outcomes["refused"] += 1
    assert outcomes["refused"] > 50


# ------------------------------------------------------------------------------------------------- Stage 5B hardening
def _junction(link: Path, outside: Path) -> None:
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(outside), str(link))


@pytest.mark.parametrize("pixels", ["sharp", "as exported"])
def test_importing_a_project_file_never_changes_it(root: Path, pixels: str) -> None:
    """A smooth-textured .glb already in the project: as exported it is catalogued where it is; with Keep pixels
    sharp the sharp version is a separate managed model. Either way the creator's file keeps its bytes."""
    local = root / "art" / "stairs.glb"
    local.parent.mkdir()
    local.write_bytes(STAIRS.read_bytes())
    asset = catalog.import_model(root, local, pixels=pixels)
    assert local.read_bytes() == STAIRS.read_bytes(), "the source file is untouched"
    if pixels == "sharp":
        assert asset.model == "assets/models/stairs.glb"
        assert set(_samplers(root / asset.model)) == {glb.GL_NEAREST}
    else:
        assert asset.model == "art/stairs.glb" and not (root / catalog.MODELS_DIR / "stairs.glb").exists()


def test_a_sharp_import_of_a_model_in_the_models_folder_gets_its_own_file(root: Path) -> None:
    (root / catalog.MODELS_DIR).mkdir(parents=True)
    existing = root / catalog.MODELS_DIR / "stairs.glb"
    existing.write_bytes(STAIRS.read_bytes())
    asset = catalog.import_model(root, existing)
    assert existing.read_bytes() == STAIRS.read_bytes()
    assert asset.model == "assets/models/stairs_2.glb", "the name is taken by the creator's file"


def test_staging_never_touches_an_unrelated_file_of_the_old_staging_name(root: Path) -> None:
    catalog.import_model(root, COTTAGE)
    old_style = root / catalog.MODELS_DIR / ".cottage.glb.mesh-staged"
    old_style.write_bytes(b"someone else's file")
    catalog.reimport_model(root, "cottage", COTTAGE_V2)
    assert old_style.read_bytes() == b"someone else's file"
    leftovers = [p.name for p in (root / catalog.MODELS_DIR).rglob("*.mesh-staged") if p != old_style]
    assert leftovers == []


@pytest.mark.parametrize("where", ["staging", "validation", "replacement"])
def test_a_failure_at_any_stage_leaves_the_project_as_it_was(root: Path, monkeypatch: pytest.MonkeyPatch, where: str) -> None:
    import tempfile

    catalog.import_model(root, COTTAGE)
    (root / catalog.MODELS_DIR / ".cottage.glb.mesh-staged").write_bytes(b"unrelated")
    before = _files(root)
    calls: list[int] = []
    if where == "staging":
        real_mkstemp = tempfile.mkstemp

        def mkstemp(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202 - tempfile.mkstemp's signature
            calls.append(1)
            if len(calls) == 2:
                raise OSError("no space for the second staged file (test)")
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr(catalog.tempfile, "mkstemp", mkstemp)
    elif where == "validation":
        def broken(path):  # noqa: ANN001, ANN202
            raise glb.GlbError(f"{path}: staged copy unreadable (test)")

        monkeypatch.setattr(catalog, "load_glb", broken)
        monkeypatch.setattr(catalog, "plan_reimport", catalog.plan_reimport)  # planning uses the real reader below
    else:
        real_replace = os.replace

        def replace(src, dst):  # noqa: ANN001, ANN202
            calls.append(1)
            if len(calls) == 2:
                raise OSError("replace failed (test)")
            real_replace(src, dst)

        monkeypatch.setattr(os, "replace", replace)
    if where == "validation":
        plan = catalog.plan_reimport(root, "cottage", COTTAGE_V2)  # checked with the real reader first
        monkeypatch.setattr(catalog, "plan_reimport", lambda *a, **k: plan)
    with pytest.raises((OSError, glb.GlbError)):
        catalog.reimport_model(root, "cottage", COTTAGE_V2)
    assert _files(root) == before, "byte-identical, unrelated staging-named file included; no staged files left"


@pytest.mark.parametrize("linked", ["assets", "assets/models/previews"])
def test_no_write_goes_through_a_link_out_of_the_project(root: Path, tmp_path: Path, linked: str) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    if linked == "assets/models/previews":
        catalog.import_model(root, STAIRS)
        before = _files(root)
        (root / linked).rename(root / "previews_moved")
        _junction(root / linked, outside)
        with pytest.raises(CatalogError, match="outside the project"):
            catalog.reimport_model(root, "stairs", STAIRS)
        assert (root / catalog.MODELS_DIR / "stairs.glb").read_bytes() == before["assets/models/stairs.glb"]
    else:
        _junction(root / linked, outside)
        with pytest.raises(CatalogError, match="outside the project"):
            catalog.import_model(root, COTTAGE)
    assert list(outside.iterdir()) == [], "nothing written outside"
