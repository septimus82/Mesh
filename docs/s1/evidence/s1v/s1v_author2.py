"""S1v: add WolfDrop2 (Health + DropTable healing_potion) via mesh author apply to each Studio-editable project."""
import contextlib, io, json, sys
from pathlib import Path
from mesh_cli.main import main as mesh
BASE = Path(sys.argv[1])
for name in ("n_blank", "n_adventure", "n_starter", "n_hd2d_rpg", "n_monster"):
    root = BASE / name
    lay = json.loads((root / "s1v_layout.json").read_text(encoding="utf-8"))
    px, py = lay["player_start"]
    x, y = px + 400, py + 480
    ch = [{"op": "place_blank", "room": "start", "name": "WolfDrop2", "x": x, "y": y},
          {"op": "set_picture", "room": "start", "entity_id": "@0", "sprite": "assets/sprites/starter_sign.png"},
          {"op": "add_behaviour", "room": "start", "entity_id": "@0", "behaviour": "Health"},
          {"op": "add_behaviour", "room": "start", "entity_id": "@0", "behaviour": "DropTable"},
          {"op": "set_behaviour_param", "room": "start", "entity_id": "@0", "behaviour": "DropTable", "param": "drops",
           "value": [{"item_id": "healing_potion", "chance": 1.0}]}]
    f = BASE / "c2.json"; f.write_text(json.dumps(ch), encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = mesh(["author", "apply", str(f), "--project", str(root)])
    f.unlink()
    lay["objects"]["WolfDrop2"] = [x, y]
    (root / "s1v_layout.json").write_text(json.dumps(lay, indent=1), encoding="utf-8")
    print(name, code, json.loads(out.getvalue()).get("ok"))
