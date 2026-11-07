"""M17-L1 check: Lakeside's way out and back, walked with the arrow keys in the real game (hidden window).
Lakeside → south passage → Village; Village → east road passage → Lakeside; where the player arrives each time.
Usage: transitions.py PROJECT OUT.json"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-lva")
sys.path.insert(0, r"D:\Games\Mesh-lva\tooling")
project, out = Path(sys.argv[1]), Path(sys.argv[2])
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env_tr" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

from hd2d_demo import HiddenGame  # noqa: E402
from hd2d_floors_demo import _feet, hold_key  # noqa: E402
from m20a_terrain_study import _put  # noqa: E402

game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
row = {}
try:
    game.load("packs/core_regions/scenes/lakeside.json")
    game.step(20)
    k = game.arcade.key
    p = _put(game, 30.0, 5.5)
    hold_key(game, p, k.DOWN, 1, 0.2, 600)
    game.step(60)
    row["lakeside_south_passage_leads_to"] = game.window.scene_controller.current_scene_path
    row["arrived_in_village_at_m"] = [round(v, 2) for v in _feet(game.player())]
    p = _put(game, 33.0, 7.0)
    hold_key(game, p, k.RIGHT, 0, 39.5, 600)
    game.step(60)
    row["village_east_passage_leads_to"] = game.window.scene_controller.current_scene_path
    row["arrived_in_lakeside_at_m"] = [round(v, 2) for v in _feet(game.player())]
    row["lakeside_lights_enabled"] = [lt.get("enabled", True) for lt in
                                      json.loads((project / "packs/core_regions/scenes/lakeside.json").read_text(encoding="utf-8"))["lights"]]
    hd = game.window.hd2d_renderer
    row["lamps_lit_in_renderer"] = len(hd.lighting.lamps) if hd is not None and hasattr(hd.lighting, "lamps") else None
finally:
    game.close()
out.write_text(json.dumps(row, indent=1), encoding="utf-8")
print(json.dumps(row, indent=1))
