"""A fresh HD-2D RPG project in scratch (the template's own code), with night and night-without-lamp-shadows copies of
its village made by the engine's set_hd2d_sun op: scene settings only, new files, the original start.json kept."""
import json
import os
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh")
M17 = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\m17")
sys.path.insert(0, str(REPO))
os.environ.update({"MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
                   "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg")})
from engine.project_ops import set_hd2d_sun  # noqa: E402
from engine.project_scaffold import create_project  # noqa: E402

project = M17 / "projects" / "starter"
if not project.exists():
    create_project(project, "Starter", "hd2d_rpg")
scenes = project / "packs" / "core_regions" / "scenes"
village = json.loads((scenes / "start.json").read_text(encoding="utf-8"))
night = set_hd2d_sun(village, preset="night")
(scenes / "start_night.json").write_text(json.dumps(night), encoding="utf-8")
off = json.loads(json.dumps(night))
for light in off["lights"]:
    if light.get("type") != "ambient":
        light["shadows"] = False
(scenes / "start_night_lampshadows_off.json").write_text(json.dumps(off), encoding="utf-8")
print("lights", [(l.get("id"), l.get("x"), l.get("y"), l.get("elevation")) for l in night["lights"]])
print("lamp posts", [(s["id"], s["x"], s["y"]) for s in night["settings"]["hd2d"]["structures"] if "lamp" in s["model"]])
print("crates", [(s["id"], s["x"], s["y"]) for s in night["settings"]["hd2d"]["structures"] if "crate" in s["model"]])
