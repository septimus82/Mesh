"""Milestone 16 Stage 5B's acceptance demonstration, in a hidden window:
Blender -> export GLB -> import into Mesh Studio -> preview -> place -> edit -> reimport -> play.

    py -3.13 tooling/hd2d_asset_pipeline_demo.py check OUT_DIR [--blender D:/program/blender.exe]

``check`` builds an HD-2D project (the Stage 3 crossing room, from ``hd2d_floors_demo.build``) in OUT_DIR/project and
a creator's export folder OUT_DIR/blender_exports outside it. With ``--blender`` the two original models are built
and exported by Blender there (``tooling/hd2d_assets/build_*.py``); without it, the committed exports of the same
scripts are copied there. Then Mesh Studio is worked only through its own window events (typing into its fields,
clicking its buttons, the mouse in the 3D view, key presses), never by editing JSON or copying into the project:

1. import the cottage and the staircase (the staircase's smooth textures made sharp), with category and licence;
2. browse them (pictures, search) and look at the cottage's details;
3. place two cottages and the staircase; move one cottage and turn it;
4. an AI proposes a baker inside a cottage and a second staircase (by catalogue id); the person accepts;
5. save, close Mesh Studio and open the project again;
6. the creator edits the cottage in Blender (``--v2``: porch, hearth, chimney) and exports over the same file;
   Reimport shows what changes, warns that the baker would stand in the new hearth, and replaces the model:
   both cottages change, keep their ids and places, and gain the porch floor; GPU objects don't grow;
7. a broken export is refused before anything is written, and the project's files stay byte-identical;
   an edit is undone;
8. Play: the player walks to the staircase and up it onto the landing, 2 m up, then Stop.

Pictures and ``pipeline_check.json`` go to OUT_DIR. A browser with 40 models and a room with 30 structures are
timed at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
from hd2d_floors_demo import _feet, hold_key  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

ASSETS = REPO / "tooling" / "hd2d_assets"
PX = 32.0
STAIRS_AT = (14.0, 3.5)  # m: the staircase's origin (it climbs north from y - 2 to a landing 2 m up at y + 2 .. + 4)


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def export_from_blender(blender: Path | None, folder: Path, *, v2: bool = False) -> str:
    """The creator's exports (cottage.glb, stairs.glb) in ``folder``: built by Blender, or the committed copies."""
    folder.mkdir(parents=True, exist_ok=True)
    jobs = [("build_cottage.py", "cottage.glb", ["--v2"] if v2 else [])] + ([] if v2 else [("build_stairs.py", "stairs.glb", [])])
    for script, name, flags in jobs:
        if blender is not None:
            subprocess.run([str(blender), "--factory-startup", "-noaudio", "--background", "--python",
                            str(ASSETS / script), "--", str(folder / name), *flags],
                           check=True, capture_output=True, timeout=600)
        else:
            shutil.copy2(ASSETS / ("cottage_v2.glb" if v2 else name), folder / name)
    return "Blender (headless)" if blender is not None else "committed exports of the same scripts"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_files(project: Path) -> dict[str, str]:
    return {p.relative_to(project).as_posix(): _sha(p) for p in sorted((project / "assets" / "models").rglob("*"))
            if p.is_file()}


def check(out: Path, blender: Path | None = None) -> dict[str, Any]:
    import hd2d_floors_demo

    out.mkdir(parents=True, exist_ok=True)
    project = hd2d_floors_demo.build(out / "project")
    art = out / "blender_exports"
    report: dict[str, Any] = {"steps": [], "exports": export_from_blender(blender, art)}

    def step(name: str, **facts: Any) -> None:
        report["steps"].append({"step": name, **facts})

    d = StudioDriver(project)
    try:
        studio, view = d.studio, d.studio.hd2d
        k = d.arcade.key
        ctrl = k.MOD_CTRL
        gl_start = d.gl_counts()

        # 1. import the cottage and the staircase through Import 3D model
        d.button("Models...")
        d.button("Import 3D model...")
        d.type_into("model_path", str(art / "cottage.glb"))
        d.type_into("model_import_category", "Buildings")
        d.type_into("model_import_license", "Original (Stage 5B demo; tooling/hd2d_assets)")
        cottage_report = [t for t in d.labels() if "triangles" in t or "Collision" in t or "Textures" in t]
        d.picture(out / "01_import_cottage.png")
        d.button("Import")
        imported_cottage = studio.message
        cottage_page = [t for t in d.labels() if t.startswith(("Place in scene", "Reimport"))]
        d.button("< All models")
        d.button("Import 3D model...")
        d.type_into("model_path", str(art / "stairs.glb"))
        d.type_into("model_import_category", "Stairs and bridges")
        stairs_report = [t for t in d.labels() if "Smooth" in t or "Made sharp" in t or "Collision" in t]
        d.picture(out / "02_import_stairs_sharpened.png")
        d.button("Import")
        catalog_doc = json.loads((project / "assets/models/catalog.json").read_text(encoding="utf-8"))
        step("import", exports=report["exports"], cottage_report=cottage_report, cottage_message=imported_cottage,
             cottage_page_after_import=cottage_page,
             stairs_report=stairs_report, catalog=[{k_: e.get(k_) for k_ in ("id", "model", "category", "collision",
                                                                               "floors", "license", "pixels")}
                                                    for e in catalog_doc["models"]],
             files=sorted(_project_files(project)))

        # 2. browse: the list, a search, the cottage's details
        d.button("< All models")
        d.picture(out / "03_browser.png")
        listed = [t for t in d.labels() if t.startswith(("Cottage", "Stairs", "Stone Crossing"))]
        d.type_into("model_search", "stair")
        searched = [t for t in d.labels() if t.startswith(("Cottage", "Stairs", "Stone Crossing"))]
        d.picture(out / "04_search.png")
        d.type_into("model_search", "")
        d.button("Cottage", prefix=True)
        details = [t for t in d.labels() if "cop" in t and "this room" in t or t.startswith("Imported")]
        d.picture(out / "05_cottage_details.png")
        step("browse", listed=listed, search_stair=searched, details=details)

        # 3. place two cottages and the staircase; move one cottage and turn it
        d.button("Reset view")

        def place(asset_id: str, name: str, at: tuple[float, float], picture: str | None = None) -> str | None:
            if studio.panel != "structures":
                d.button("Models...")
            if view.chosen_model != asset_id:
                if view.chosen_model is not None:
                    d.button("< All models")
                d.button(name, prefix=True)
            d.button("Place in scene")
            spot = d.screen((at[0], at[1], 0.0))
            left, right, bottom, top = view._rect()
            assert left < spot[0] < right and bottom < spot[1] < top, f"{at} m is off the 3D view ({spot})"
            d.window.dispatch_event("on_mouse_motion", spot[0], spot[1], 0, 0)
            d.frame()
            if picture:
                d.picture(out / picture)
            d.click(*spot)
            return str(view.structure) if view.structure else None

        a = place("cottage", "Cottage", (5.0, 20.0), "06_placing_preview.png")
        b = place("cottage", "Cottage", (27.0, 20.0))
        s = place("stairs", "Stairs", (STAIRS_AT[0], STAIRS_AT[1]))
        placed = {sid: d.structure(sid) for sid in (a, b, s) if sid}
        edit_filters = _filters(d.renderer, "stairs.glb")
        d.picture(out / "07_placed.png")
        d.click(*d.screen((27.0, 20.0, 2.6)))  # pick the second cottage by its roof
        picked = view.structure
        d.drag(d.screen((27.0, 20.0, 0.0)), d.screen((26.0, 19.0, 0.0)))
        d.button("Turn +90")
        moved = d.structure(b or "")
        d.picture(out / "08_moved_and_turned.png")
        step("place_move_turn", ids=[a, b, s], placed=placed, picked_by_clicking_its_roof=picked, moved_turned=moved,
             stairs_texture_filters_in_edit=edit_filters,
             one_file_for_both_cottages=len({st["model"] for st in placed.values() if st["model"].endswith("cottage.glb")}) == 1)

        # 4. an AI proposes a baker inside cottage a (where the edit will put the hearth) and a second staircase
        hearth = (5.0 + 1.9, 20.0)
        proposal = studio.ai.stage_proposal_payload({"title": "A baker and more stairs", "source": "a test AI",
                                                     "changes": [
            {"op": "place_prefab", "prefab": "person", "x": hearth[0] * PX, "y": hearth[1] * PX},
            {"op": "place_structure", "model": "stairs", "x": 3.0 * PX, "y": 3.0 * PX}]})
        refused = studio.ai.stage_proposal_payload({"changes": [
            {"op": "place_structure", "model": "tower", "x": 100, "y": 100}]})
        listing = studio.ai.read_live_scene().get("models", [])
        studio.open_ai()
        d.frame()
        d.picture(out / "09_ai_proposal.png")
        d.button("Accept")
        structures_now = [dict(st) for st in (studio.project.scene().get("settings") or {})["hd2d"]["structures"]]
        baker = next((e for e in studio.project.scene().get("entities", [])
                      if abs(float(e.get("x", 0)) - hearth[0] * PX) < 1 and abs(float(e.get("y", 0)) - hearth[1] * PX) < 1), None)
        step("ai", summary=list(getattr(proposal, "summary", [])), refused=refused if isinstance(refused, dict) else None,
             models_listed_for_ai=[(m["id"], m["category"]) for m in listing], accepted_structures=len(structures_now),
             baker=None if baker is None else {"id": baker.get("id"), "name": baker.get("name"), "x": baker.get("x"), "y": baker.get("y")})

        # 5. save, close, reopen
        d.key(k.S, ctrl)
        saved = studio.message
    finally:
        d.close()
    d = StudioDriver(project)
    try:
        studio, view = d.studio, d.studio.hd2d
        k = d.arcade.key
        ctrl = k.MOD_CTRL
        reopened = {sid: d.structure(sid) for sid in (a, b, s) if sid}
        d.button("Models...")
        d.picture(out / "10_reopened_browser.png")
        step("save_reopen", saved_message=saved, same_structures=reopened == {**placed, b: moved} if b else None,
             browser=[t for t in d.labels() if t.startswith(("Cottage", "Stairs", "Stone Crossing"))])

        # 6. edit in Blender, export over the same file, reimport
        before_gl = d.gl_counts()
        export_from_blender(blender, art, v2=True)
        if view.chosen_model != "cottage":
            d.button("Cottage", prefix=True)
        d.button("Reimport...")
        plan_text = [t for t in d.texts() if t.startswith(("New ", "Collider", "Size", "Room ", "Same", "Reimport ", "From"))]
        d.picture(out / "11_reimport_plan.png")
        d.button("Reimport")
        reimport_message = studio.message
        world = d.window.hd2d_world
        porch_floors = sorted({sf.floor for sf in world.surfaces if sf.floor.endswith("/col_porch")})
        after = {sid: d.structure(sid) for sid in (a, b) if sid}
        porch_y = 20.0 - 2.6  # in front of cottage a's door
        on_porch = world.stand(5.0, porch_y, 0.15, 0.3, 0.19)
        in_hearth = world.stand(*hearth, 0.1, 0.3, 0.19)
        d.click(*d.screen((5.0, 20.0, 3.0)))  # the first cottage, by its roof
        d.key(k.F)  # frame it
        d.picture(out / "12_reimported.png")
        after_gl = d.gl_counts()
        step("reimport", plan=plan_text, message=reimport_message, porch_floors=porch_floors,
             ids_and_places_kept=after == {a: reopened.get(a or ""), b: reopened.get(b or "")},
             stand_on_new_porch=on_porch, stand_in_new_hearth=in_hearth, gl_before=before_gl, gl_after=after_gl,
             preview_changed=_sha(project / "assets/models/previews/cottage.png"))

        # 7. a broken export is refused before anything is written; an edit is undone
        files_before = _project_files(project)
        (art / "cottage.glb").write_bytes((art / "cottage.glb").read_bytes()[:500])  # a cut-off export
        d.button("Models...") if not d.has_button("Reimport...") else None
        d.button("Reimport...")
        refusal = [t for t in d.labels() if "damaged" in t]
        reimport_disabled = [w.disabled for w in d.studio.ui.walk_widgets()
                             if getattr(w, "text", None) == "Reimport" and hasattr(w, "disabled")] == [True]
        d.picture(out / "13_broken_export_refused.png")
        d.button("Cancel")
        files_after = _project_files(project)
        stairs_before = d.structure(s or "")
        d.button("Models...") if d.studio.panel == "structures" else None
        d.button("Reset view")
        landing = (STAIRS_AT[0], STAIRS_AT[1] + 3.0, 2.0)
        d.click(*d.screen(landing))  # the staircase's landing
        d.drag(d.screen(landing), d.screen((landing[0] + 1.0, landing[1], 2.0)))
        stairs_dragged = d.structure(s or "")
        d.key(k.Z, ctrl)
        stairs_undone = d.structure(s or "")
        step("failure_and_undo", refusal=refusal, reimport_button_disabled=reimport_disabled,
             project_files_unchanged=files_before == files_after, stairs_before=stairs_before,
             stairs_dragged=stairs_dragged, stairs_after_undo=stairs_undone)

        # repeated reimports (v1 / v2 / v1 ...), each through the same buttons: GPU objects must not grow
        counts = []
        for i in range(6):
            export_from_blender(blender, art, v2=i % 2 == 1)
            if studio.panel != "structures":
                d.button("Models...")
            if view.chosen_model != "cottage":
                if view.chosen_model is not None:
                    d.button("< All models")
                d.button("Cottage", prefix=True)
            d.button("Reimport...")
            d.button("Reimport")
            counts.append(d.gl_counts())
        step("repeated_reimport", gl_after_each=counts,
             floors_now=sorted({sf.floor for sf in d.window.hd2d_world.surfaces if sf.floor.startswith("cottage")}))
        d.button("Close") if studio.panel == "structures" else None

        # 8. Play: walk to the staircase and up it
        d.key(k.F4)
        player = d.game.player()
        walk = []

        def note(label: str) -> None:
            fx, fy = _feet(player)
            walk.append({"after": label, "feet_m": [round(fx, 2), round(fy, 2)],
                         "elevation_m": round(player.mesh_entity_data.get("elevation", 0.0) / PX, 2),
                         "floor": getattr(player, "mesh_hd2d_floor", None)})

        note("start")
        hold_key(d.game, player, k.DOWN, 1, 0.6, 400)
        note("south, below the staircase")
        hold_key(d.game, player, k.LEFT, 0, STAIRS_AT[0], 900)
        note("west, to the foot of the staircase")
        hold_key(d.game, player, k.UP, 1, STAIRS_AT[1] + 3.0, 600)
        note("north, up the steps onto the landing")
        d.picture(out / "14_play_on_the_landing.png")
        play_filters = _filters(d.window.hd2d_renderer, "stairs.glb")
        d.key(k.F4)
        step("play", walk=walk, mode_after_stop=studio.mode, stairs_texture_filters_in_play=play_filters)

        # performance: a browser with 40 models, a room with 30 structures
        report["performance"] = _performance(d, project, art)
        report["gl"] = {"start": gl_start, "before_reimport": before_gl, "after_reimport": after_gl,
                        "end": d.gl_counts()}
    finally:
        d.close()
    _write(out / "pipeline_check.json", report)
    return report


def _filters(renderer: Any, model_suffix: str) -> list[list[int]]:
    """The GPU filters (min, mag) of a model's textures as the renderer made them: NEAREST is 9728."""
    found = {tuple(texture.filter) for (model, _material), texture in renderer._materials.items()
             if model.endswith(model_suffix)}
    return [list(f) for f in sorted(found)]


def _performance(d: StudioDriver, project: Path, art: Path) -> dict[str, Any]:
    """Timings with a moderately full catalogue (40 models) and room (30 structures). The extra models are
    imported through the catalogue API (setup, not part of the demonstration)."""
    from engine import project_ops as ops
    from engine.hd2d import catalog, glb

    doc, binary = glb.split_glb((REPO / "tooling/hd2d_assets/cottage.glb").read_bytes())
    for i in range(38):
        doc.setdefault("asset", {})["extras"] = {"copy": i}  # different bytes: not a duplicate
        variant = art / f"house_{i:02d}.glb"
        variant.write_bytes(glb.join_glb(doc, binary))
        catalog.import_model(project, variant, category=f"Set {i % 4}")
    studio, view = d.studio, d.studio.hd2d

    def timed(fn, n: int = 6) -> float:  # noqa: ANN001 - a callable
        out = []
        for _ in range(n):
            t = time.perf_counter()
            fn()
            out.append((time.perf_counter() - t) * 1000)
        return round(statistics.median(out), 1)

    if studio.panel != "structures":
        d.button("Models...")
    view.choose_model(None)  # the list, not a model's page
    view._assets = None
    def reopen() -> None:
        view._assets = None  # the browser reads the catalogue again, as when it is opened
        studio._rebuild()
        d.frame()

    open_ms = timed(reopen)

    def ordinary() -> None:
        studio.panel = "inspect"  # Mesh Studio's ordinary right panel, measured the same way (rebuild and draw)
        studio._rebuild()
        d.frame()

    ordinary_ms = timed(ordinary)
    studio.panel = "structures"
    studio._rebuild()
    frame_ms = timed(lambda: d.frame(), 30)
    search_ms = timed(lambda: view.set_model_filter("set 2"), 6)
    view.set_model_filter("")
    select_ms = timed(lambda: (view.choose_model("house_05"), d.frame()), 6)
    scene = studio.project.scene()
    hd2d = scene["settings"]["hd2d"]
    for i in range(30 - len(hd2d["structures"])):
        studio._edit(lambda sc, i=i: ops.place_structure(sc, "assets/models/cottage.glb", (2 + (i % 6) * 5) * PX,
                                                         (2 + (i // 6) * 4.5) * PX)[0], "setup")
    count = len(studio.project.scene()["settings"]["hd2d"]["structures"])
    room_frame_ms = timed(lambda: d.frame(), 30)
    first = view.structures()[0].id
    commit_ms = timed(lambda: studio._edit(lambda sc: ops.set_structure(sc, first, rotation=(view.find(first).rotation + 15) % 360),
                                            "turn"), 6)
    return {"models_in_catalogue": len(view.models()), "structures_in_room": count,
            "browser_open_ms": open_ms, "ordinary_panel_ms": ordinary_ms, "browser_frame_ms": frame_ms, "search_ms": search_ms,
            "choose_model_ms": select_ms, "room_frame_ms": room_frame_ms, "edit_commit_ms": commit_ms}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check"])
    parser.add_argument("out", type=Path)
    parser.add_argument("--blender", type=Path, default=None)
    args = parser.parse_args()
    os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")
    print(json.dumps(check(args.out, args.blender), indent=2, default=str))
