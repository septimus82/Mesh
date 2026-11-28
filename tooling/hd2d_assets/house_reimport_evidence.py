"""M2-1 evidence: the Blender house (build_house.py) imported into a new HD-2D RPG project, placed twice, drawn in a
hidden window, reimported after its Blender edit (house_v2.glb) and drawn again; then a cut-off export refused.

    py -3.13 tooling/hd2d_assets/house_reimport_evidence.py OUT_DIR

Writes OUT_DIR/before.png, after.png and report.json (the plan, the files that changed, the refusal, hashes). Set
MESH_USER_DIR / MESH_PROJECTS_DIR / APPDATA to scratch folders to keep the run out of the owner's settings.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
HOUSE, HOUSE_V2 = HERE / "house.glb", HERE / "house_v2.glb"
SCENE = "packs/core_regions/scenes/houses.json"
COPIES = ((208.0, 352.0), (432.0, 352.0))  # px; the player stands south of them, the camera looks north
PLAYER = (320.0, 200.0)


def _hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _room(project: Path, model: str) -> dict[str, Any]:
    """The template's village light and camera over a bare 20 x 20 m lawn, with the player and two houses."""
    from engine import project_ops as ops

    start = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
    hd2d = {k: start["settings"]["hd2d"][k] for k in ("ambient", "camera", "sun")}
    hd2d["camera"] = {**hd2d["camera"], "bounds": [0.0, 0.0, 640.0, 640.0]}
    hd2d["ground"] = {**start["settings"]["hd2d"]["ground"], "to": [640.0, 640.0]}
    player = next(e for e in start["entities"] if e["id"].startswith("start_player"))
    scene = {**start, "name": "houses", "lights": [], "entities": [{**player, "x": PLAYER[0], "y": PLAYER[1]}],
             "settings": {**start["settings"], "world_width": 640.0, "world_height": 640.0, "hd2d": hd2d}}
    for x, y in COPIES:
        scene, _sid = ops.place_structure(scene, model, x, y)
    return scene


def check(out: Path) -> dict[str, Any]:
    from scene_snapshot import snapshot

    from engine.hd2d import catalog
    from engine.project_scaffold import create_project

    out.mkdir(parents=True, exist_ok=True)
    project, art = out / "HouseDemo", out / "blender_exports"
    if project.exists() or art.exists():
        raise SystemExit(f"{out} already holds a run (HouseDemo/, blender_exports/); choose an empty folder.")
    create_project(project, "HouseDemo", "hd2d_rpg")
    art.mkdir()
    export = art / "house.glb"
    export.write_bytes(HOUSE.read_bytes())
    asset = catalog.import_model(project, export, category="Buildings", license="Original (Mesh, build_house.py)")
    scene = _room(project, asset.model)
    (project / SCENE).write_text(json.dumps(scene, indent=2), encoding="utf-8")
    rooms = {"houses": scene}

    report: dict[str, Any] = {"imported": asset.as_dict(), "structures": scene["settings"]["hd2d"]["structures"]}
    report["before_draw"] = snapshot(project, SCENE, out / "before.png", player=PLAYER)["camera"]
    before = _hashes(project)

    export.write_bytes(HOUSE_V2.read_bytes())  # the creator's edit, exported again from Blender
    plan = catalog.plan_reimport(project, asset.id, rooms=rooms)
    report["plan"] = {"changes": plan.changes, "warnings": plan.warnings, "wrote": sorted(
        k for k, v in _hashes(project).items() if before.get(k) != v)}
    catalog.reimport_model(project, asset.id, rooms=rooms)
    after = _hashes(project)
    report["reimport_changed"] = sorted(k for k in after.keys() | before.keys() if after.get(k) != before.get(k))
    report["after_draw"] = snapshot(project, SCENE, out / "after.png", player=PLAYER)["camera"]

    data = HOUSE_V2.read_bytes()
    export.write_bytes(data[: len(data) // 2])  # an export cut off part-way
    refused = catalog.plan_reimport(project, asset.id, rooms=rooms)
    try:
        catalog.reimport_model(project, asset.id, rooms=rooms)
        report["broken"] = {"refused": False}
    except catalog.CatalogError as exc:
        report["broken"] = {"refused": True, "problem": refused.inspection.problem, "error": str(exc)}
    report["broken"]["project_unchanged"] = _hashes(project) == after
    report["sha256"] = {"house.glb": hashlib.sha256(HOUSE.read_bytes()).hexdigest(),
                        "house_v2.glb": hashlib.sha256(HOUSE_V2.read_bytes()).hexdigest(),
                        "before.png": hashlib.sha256((out / "before.png").read_bytes()).hexdigest(),
                        "after.png": hashlib.sha256((out / "after.png").read_bytes()).hexdigest()}
    text = json.dumps(report, indent=2).replace(json.dumps(str(out))[1:-1], "OUT_DIR")  # no machine paths
    (out / "report.json").write_text(text + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]).resolve()), indent=2))
