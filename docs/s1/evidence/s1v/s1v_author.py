"""S1v: author the test content into generated projects through Studio's ops, `mesh author apply` and MCP.

usage: py -3.13 s1v_author.py BASE
Writes BASE/<project>/s1v_layout.json (what was placed where) for the play driver.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

BASE = Path(sys.argv[1])
import engine  # noqa: E402

print("engine from", engine.__file__)
from engine import project_ops as ops  # noqa: E402
from engine.editor import project_ownership  # noqa: E402
from engine.mcp_server import tools  # noqa: E402
from engine.studio_project import Project  # noqa: E402
from mesh_cli.main import main as mesh  # noqa: E402

ROOM_PATH = "packs/core_regions/scenes/start.json"
STOCK = [{"item_id": "healing_potion", "price": 5, "quantity": 3}]
PLAYER_TOOL = {"n_blank": "studio", "n_adventure": "author", "n_starter": "mcp", "n_hd2d_rpg": "studio",
               "n_monster": "author"}


def author_cli(root: Path, changes: list[dict]) -> dict:
    f = root.parent / f"{root.name}_changes.json"
    f.write_text(json.dumps(changes), encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = mesh(["author", "apply", str(f), "--project", str(root)])
    f.unlink()
    res = json.loads(out.getvalue() or "{}")
    return {"exit": code, "ok": res.get("ok"), "message": res.get("message"), "summary": (res.get("summary") or [])[:3]}


def health_cfg(root: Path, name: str) -> object:
    for path in [root / ROOM_PATH]:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for e in doc["entities"]:
            if e.get("name") == name:
                return (e.get("behaviour_config") or {}).get("Health")
    return None


def player_cfg(root: Path) -> dict:
    pre = json.loads((root / "assets/prefabs.json").read_text(encoding="utf-8"))
    ent = next(p["entity"] for p in pre if p.get("id") == ops.PLAYER_PREFAB)
    return {"behaviours": ent.get("behaviours"), "Health": (ent.get("behaviour_config") or {}).get("Health"),
            "Combat": (ent.get("behaviour_config") or {}).get("Combat")}


def studio_project(root: Path):
    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    held = project_ownership.acquire(root, project_ownership.STUDIO)
    return held, Project.open(root, world)


def do_project(name: str) -> None:
    root = BASE / name
    print(f"\n=== {name}")
    start = json.loads((root / ROOM_PATH).read_text(encoding="utf-8"))
    player = ops.legacy_player(start) or next(e for e in start["entities"] if "player" in str(e.get("id")))
    px, py = float(player["x"]), float(player["y"])
    P = lambda dx, dy: (px + dx, py + dy)  # noqa: E731
    layout = {"player_start": [px, py], "objects": {}}

    # ---------------- Studio path: Project + the ops the inspector/picker call ----------------
    held, proj = studio_project(root)
    try:
        key = proj.current
        made = {}

        def place(label, at):
            box = {}

            def change(s):
                s2, eid = ops.place_blank(s, key, label, *at)
                box["id"] = eid
                return s2
            proj.edit_scene(change)
            made[label] = box["id"]
            layout["objects"][label] = list(at)
            return box["id"]

        e = place("WolfS", P(200, 0))
        proj.edit_scene(lambda s: ops.set_picture(s, e, "assets/sprites/starter_sign.png"))
        proj.edit_scene(lambda s: ops.add_behaviour(s, e, "Health"))           # picker: "Has health"
        proj.edit_scene(lambda s: ops.set_behaviour_param(s, e, "Health", "max_hp", 50))  # basics: "Health"
        for label, at, setup in (
            ("Potion", P(0, 160), [("PickupCollectible", {"item_id": "healing_potion", "item_amount": 1})]),
            ("MerchantS", P(0, 320), [("Vendor", {"stock": STOCK}), ("Interactable", {"interact_event": "open_shop"})]),
            ("MerchantPlain", P(0, 480), [("Vendor", {"stock": STOCK})]),
            ("Button", P(400, 0), [("SwitchInteract", {"event_id": "chest_open"})]),
            ("Chest", P(400, 160), [("RewardChest", {"unlock_event": "chest_open", "item_id": "healing_potion"})]),
            ("WolfDrop", P(400, 320), [("Health", {}), ("DropTable", {"drops": [{"item_id": "healing_potion", "chance": 1.0}]})]),
        ):
            eid = place(label, at)
            proj.edit_scene(lambda s, eid=eid: ops.set_picture(s, eid, "assets/sprites/starter_sign.png"))
            for beh, params in setup:
                proj.edit_scene(lambda s, eid=eid, beh=beh: ops.add_behaviour(s, eid, beh))
                for k, v in params.items():
                    proj.edit_scene(lambda s, eid=eid, beh=beh, k=k, v=v: ops.set_behaviour_param(s, eid, beh, k, v))
        z = place("ObjZone", P(600, 0))
        proj.edit_scene(lambda s: ops.set_trigger_zone(s, z, width=64, height=64, set_flags=["objective_done"]))
        vault = proj.add_room("Vault")
        annex = proj.add_room("Annex")
        if PLAYER_TOOL.get(name) == "studio":
            pid = next(e2["id"] for e2 in proj.scene(key)["entities"] if e2["id"] == player["id"])
            proj.edit_scene(lambda s: ops.add_behaviour(s, pid, "Health"))
            proj.edit_scene(lambda s: ops.add_behaviour(s, pid, "Combat"))
        proj.save(owner=held)
    finally:
        held.release()
    layout["rooms"] = {"vault": vault, "annex": annex}

    # ---------------- mesh author apply ----------------
    changes = [
        {"op": "place_blank", "room": "start", "name": "WolfA", "x": P(200, 160)[0], "y": P(200, 160)[1]},
        {"op": "set_picture", "room": "start", "entity_id": "@0", "sprite": "assets/sprites/starter_sign.png"},
        {"op": "add_behaviour", "room": "start", "entity_id": "@0", "behaviour": "Health"},
        {"op": "set_behaviour_param", "room": "start", "entity_id": "@0", "behaviour": "Health", "param": "max_hp", "value": 50},
        {"op": "place_blank", "room": "start", "name": "WolfM", "x": P(200, 320)[0], "y": P(200, 320)[1]},
        {"op": "set_picture", "room": "start", "entity_id": "@4", "sprite": "assets/sprites/starter_sign.png"},
        {"op": "link_rooms", "key_a": "start", "at_a": list(P(600, 200)), "key_b": vault, "at_b": [320, 240]},
        {"op": "link_rooms", "key_a": "start", "at_a": list(P(600, 400)), "key_b": annex, "at_b": [320, 240]},
    ]
    layout["objects"].update({"WolfA": list(P(200, 160)), "WolfM": list(P(200, 320))})
    if PLAYER_TOOL.get(name) == "author":
        changes += [{"op": "add_behaviour", "room": "start", "entity_id": "Player", "behaviour": "Health"},
                    {"op": "add_behaviour", "room": "start", "entity_id": "Player", "behaviour": "Combat"}]
    print("  mesh author apply #1:", author_cli(root, changes))
    doc = json.loads((root / ROOM_PATH).read_text(encoding="utf-8"))
    doors = {e["name"]: e["id"] for e in doc["entities"] if e.get("tag") == "door" and e["name"] in ("Door to Vault", "Door to Annex")}
    layout["doors"] = doors
    for d in doors:
        ent = next(x for x in doc["entities"] if x.get("name") == d)
        layout["objects"][d] = [ent["x"], ent["y"]]
    # #653: Studio-supported gate (ConditionalActivator via set_show_when) on the Vault door ...
    held, proj = studio_project(root)
    try:
        proj.edit_scene(lambda s: ops.set_show_when(s, doors["Door to Vault"], ["objective_done"], []))
        proj.save(owner=held)
    finally:
        held.release()
    # ... and the load-time entity-level form through mesh author set_entity_fields on the Annex door.
    print("  mesh author set_entity_fields require_flags:", author_cli(root, [
        {"op": "set_entity_fields", "room": "start", "entity_id": doors["Door to Annex"],
         "fields": {"require_flags": ["objective_done"]}}]))
    # MCP: apply_changes (authoring changes) can do the same on a sign; apply_ops set_behaviour_params adds Health.
    r = tools.apply_changes([
        {"op": "place_blank", "room": "start", "name": "GatedSign", "x": P(600, 560)[0], "y": P(600, 560)[1]},
        {"op": "set_picture", "room": "start", "entity_id": "@0", "sprite": "assets/sprites/starter_sign.png"},
        {"op": "set_entity_fields", "room": "start", "entity_id": "@0", "fields": {"require_flags": ["objective_done"]}},
    ], root=str(root))
    print("  MCP apply_changes set_entity_fields require_flags:", r.get("ok"), r.get("message"))
    layout["objects"]["GatedSign"] = list(P(600, 560))
    ops_list = [{"type": "set_behaviour_params", "scene_path": ROOM_PATH, "entity_id": "WolfM",
                 "behaviour_name": "Health", "params": {"max_hp": 50}}]
    if PLAYER_TOOL.get(name) == "mcp":
        ops_list += [{"type": "set_behaviour_params", "scene_path": ROOM_PATH, "entity_id": "Player",
                      "behaviour_name": "Health", "params": {}},
                     {"type": "set_behaviour_params", "scene_path": ROOM_PATH, "entity_id": "Player",
                      "behaviour_name": "Combat", "params": {}}]
    r = tools.apply_ops(operations=ops_list, root=str(root))
    print("  MCP apply_ops set_behaviour_params:", r.get("ok"), r.get("mode"), (r.get("results") or [{}])[0].get("message"))

    for w in ("WolfS", "WolfA", "WolfM", "WolfDrop"):
        print(f"  written Health {w}:", health_cfg(root, w))
    print(f"  shared player ({PLAYER_TOOL.get(name)}):", player_cfg(root))
    doc = json.loads((root / ROOM_PATH).read_text(encoding="utf-8"))
    print("  doors:", [(e["name"], {k: e.get(k) for k in ("require_flags",)}, e.get("behaviours"),
                       (e.get("behaviour_config") or {}).get("ConditionalActivator")) for e in doc["entities"]
                      if e.get("name") in ("Door to Vault", "Door to Annex", "GatedSign")])
    (root / "s1v_layout.json").write_text(json.dumps(layout, indent=1), encoding="utf-8")


for name in PLAYER_TOOL:
    try:
        do_project(name)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("  FAILED:", exc)

# Older-layout templates: can the tools author there at all?
for name in ("n_lighting_playground", "n_demo_slice"):
    root = BASE / name
    print(f"\n=== {name}")
    print("  mesh author place_blank:", author_cli(root, [{"op": "place_blank", "room": "start", "name": "X", "x": 10, "y": 10}]))
    r = tools.apply_ops(operations=[{"type": "set_behaviour_params", "scene_path": ROOM_PATH, "entity_id": "Guide",
                                     "behaviour_name": "Health", "params": {"max_hp": 50}}], root=str(root))
    print("  MCP apply_ops:", r.get("ok"), [x.get("message") for x in r.get("results") or []][:2])
