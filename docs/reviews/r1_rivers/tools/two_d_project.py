"""A 2D project (the 'starter' template) with a puddle and a natural pond beside the player, written with project_ops
(for comparing a 2D room's water across engine checkouts with scene_snapshot)."""
import json
import os
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
OUT = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river\twod")
sys.path[:0] = [str(REPO)]
ENV = OUT.parent / "env"
os.environ.update({"MESH_USER_DIR": str(ENV / "u"), "MESH_PROJECTS_DIR": str(ENV / "p"), "APPDATA": str(ENV / "a"),
                   "XDG_DATA_HOME": str(ENV / "x")})
from engine import project_ops as ops  # noqa: E402
from engine.project_scaffold import create_project  # noqa: E402

root = OUT / "proj2d"
create_project(root, "Two D", template_id="starter")
config = json.loads((root / "config.json").read_text(encoding="utf-8"))
world = json.loads((root / config["world_file"]).read_text(encoding="utf-8"))
start = world["scenes"][world["start_scene"]]["path"]
path = root / start
scene = json.loads(path.read_text(encoding="utf-8"))
assert "hd2d" not in (scene.get("settings") or {}), "a 2D room"
player = next(e for e in scene["entities"] if e.get("prefab_id") == "player" or e.get("tag") == "player")
px, py = float(player["x"]), float(player["y"])
scene, a = ops.place_blank(scene, Path(start).stem, "Puddle", px + 96, py)
scene = ops.set_water(scene, a, preset="puddle", width=96, height=56)
scene, b = ops.place_blank(scene, Path(start).stem, "Pond", px - 140, py + 40)
scene = ops.set_water(scene, b, preset="natural_pond", width=200, height=120)
path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
print(start)
