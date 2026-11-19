import json, os, sys, shutil
from pathlib import Path
S = Path(sys.argv[1]); label = sys.argv[2]
os.environ["MESH_USER_DIR"] = str(S / "user"); os.environ["MESH_PROJECTS_DIR"] = str(S / "projects")
os.environ["MESH_GL_SMOKE"] = "1"
sys.path.insert(0, "<repo>"); sys.path.insert(0, "<repo>/tooling")
from engine.project_scaffold import create_project
proj = S / f"game_{label}"
if proj.exists(): shutil.rmtree(proj)
create_project(proj, "Dup", "starter")
ROOM = "packs/core_regions/scenes/start.json"
p = proj / ROOM; scene = json.loads(p.read_text(encoding="utf-8"))
print("authored entities:", [(e.get("id"), e.get("name"), e.get("x"), e.get("y")) for e in scene["entities"]])
tmpl = next(e for e in scene["entities"] if e.get("prefab_id") != "player" and e.get("id"))
dups = []
for i, (x, y, hp) in enumerate([(300.0, 200.0, 30), (500.0, 260.0, 11)]):
    d = json.loads(json.dumps(tmpl)); d["id"] = "orc"; d["name"] = "orc"; d["x"] = x; d["y"] = y; d["tags"] = [f"hp{hp}"]; dups.append(d)
scene["entities"] += dups
p.write_text(json.dumps(scene, indent=2), encoding="utf-8")
from hd2d_demo import HiddenGame
g = HiddenGame(proj)
try:
    g.load(ROOM); g.step(5)
    sc = g.window.scene_controller
    orcs = [s for s in sc.all_sprites if (s.mesh_entity_data or {}).get("id") == "orc"]
    print("live orcs:", [(round(s.center_x), round(s.center_y), s.mesh_entity_data.get("tags")) for s in orcs])
    orcs[0].center_x += 17; orcs[1].center_y += 23
    print("moved orcs:", [(round(s.center_x), round(s.center_y)) for s in orcs])
    assert g.window.save_manager.save_game("dup")
    save = json.loads(Path(g.window.save_manager.get_save_path("dup")).read_text(encoding="utf-8"))
    print("saved orcs:", [(e["x"], e["y"], e.get("tags")) for e in save["entities"] if e.get("id") == "orc"])
finally:
    g.close()
g2 = HiddenGame(proj)
try:
    g2.load(ROOM); g2.step(2)
    assert g2.window.save_manager.load_game("dup"); g2.step(4)
    orcs = [s for s in g2.window.scene_controller.all_sprites if (s.mesh_entity_data or {}).get("id") == "orc"]
    print("reloaded orcs:", [(round(s.center_x), round(s.center_y), s.mesh_entity_data.get("tags")) for s in orcs])
finally:
    g2.close()
