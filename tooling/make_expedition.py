"""Build mesh_net/expedition/ (the N7 hub and expedition rooms) with Mesh's own authoring tools, reproducibly.

A new blank project (engine.project_scaffold: Mesh Studio's New Project), then the edits Mesh Studio performs:
the start room becomes the Adventurer's Hub; "Add room" twice (engine.project_ops.new_room + add_map, as
studio_project.add_room); "Add door to a room" (link_rooms) shown as invisible passages (set_door); walls painted,
objects placed, pictures picked, behaviours added and set. The two ruins rooms carry the world file's existing
``tags`` entry "expedition", which mesh_net.world reads as "one instance per party".

Run ``python tooling/make_expedition.py`` to rewrite the package; tests/test_mesh_net_world.py checks the
committed files equal a fresh build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "mesh_net" / "expedition"
SCENES = "packs/core_regions/scenes"
WORLD = "packs/core_regions/worlds/main.json"
HUB = f"{SCENES}/start.json"
PREFABS = "assets/prefabs.json"
HUB_LABEL, RUINS_1, RUINS_2 = "Adventurer's Hub", "Ancient Ruins — Layer 1", "Ancient Ruins — Layer 2"


def build() -> dict[str, str]:
    """{project-relative path: file text} for the world file, the three rooms, their maps and the prefabs."""
    from engine import project_ops as ops
    from engine.project_scaffold import create_project
    from engine.project_templates import VILLAGER_SHEET

    with TemporaryDirectory(prefix="mesh-expedition-") as temp:
        root = Path(temp)
        create_project(root, "Mesh expedition")
        hub = json.loads((root / HUB).read_text(encoding="utf-8"))
        prefabs = json.loads((root / PREFABS).read_text(encoding="utf-8"))
        world = json.loads((root / WORLD).read_text(encoding="utf-8"))
        hub_map_path = ops.map_file_paths(HUB)[0]
        maps = {hub_map_path: (root / hub_map_path).read_text(encoding="utf-8")}
    shared = next(p["entity"] for p in prefabs if p.get("id") == ops.PLAYER_PREFAB)

    # The hub: the start room, its player given a sword (Combat), the map's edge walled.
    player = ops.shared_player_ids(hub)[0]
    hub = ops.expand_players(hub, shared)
    hub = ops.set_entity_fields(hub, player, x=128.0, y=256.0)
    hub = ops.add_behaviour(hub, player, "Combat")
    hub = ops.set_behaviour_param(hub, player, "Combat", "cooldown", 0.5)
    hub = ops.paint_tiles(hub, ops.WALLS, _edge(ops, 24, 16), ops.STARTER_WALL)
    hub["name"] = HUB_LABEL
    world["scenes"]["start"]["label"] = HUB_LABEL
    hub, definition = ops.split_players(hub, [player], shared)
    assert definition is not None
    prefabs = [ops.player_prefab_entry(definition), *[p for p in prefabs if p.get("id") != ops.PLAYER_PREFAB]]
    template = ops.thin_player(next(e for e in hub["entities"] if e.get("prefab_id") == ops.PLAYER_PREFAB))

    rooms = {}
    for label in (RUINS_1, RUINS_2):  # studio_project.add_room
        world, scene, key, path = ops.new_room(world, label, SCENES, template)
        scene, map_path, skeleton = ops.add_map(scene, path, width=24, height=16, ground=ops.STARTER_FLOOR,
                                                border=ops.STARTER_WALL)
        maps[map_path] = json.dumps(skeleton, indent=2, sort_keys=True) + "\n"
        world["scenes"][key]["tags"] = ["expedition"]
        rooms[label] = [scene, key, path]
    (r1, k1, p1), (r2, k2, p2) = rooms[RUINS_1], rooms[RUINS_2]

    # Layer 1: a wall across the room with a gate a lever opens; a bandit beyond it guards the way down.
    r1 = ops.paint_tiles(r1, ops.WALLS, [(13, row) for row in range(1, 15) if row not in (7, 8)], ops.STARTER_WALL)
    r1 = _lever_and_gate(ops, r1, k1, (352, 352), (432, 256), "ruins_1_gate")
    r1 = _enemy(ops, r1, k1, VILLAGER_SHEET, "Bandit", (608, 352), hp=3, gold=10, seed=7)
    # Layer 2: its own lever and gate, and its own enemy.
    r2 = _lever_and_gate(ops, r2, k2, (224, 384), (480, 416), "ruins_2_gate")
    r2 = _enemy(ops, r2, k2, VILLAGER_SHEET, "Guardian", (480, 256), hp=2, gold=25, seed=3)

    # Doors, as Studio's "Add door to a room" makes them, shown as invisible passages (an area to walk into).
    hub, r1 = ops.link_rooms(hub, "start", HUB_LABEL, (704.0, 256.0), r1, k1, RUINS_1, (64.0, 256.0))
    r1, r2 = ops.link_rooms(r1, k1, RUINS_1, (704.0, 256.0), r2, k2, RUINS_2, (64.0, 256.0))
    hub, r1, r2 = (_passages(ops, s) for s in (hub, r1, r2))
    for scene, label in ((r1, RUINS_1), (r2, RUINS_2)):
        scene["name"] = label

    def text(doc: object) -> str:
        return json.dumps(doc, indent=2, sort_keys=True) + "\n"

    return {WORLD: text(world), HUB: text(hub), p1: text(r1), p2: text(r2), PREFABS: text(prefabs), **maps}


def _edge(ops, width: int, height: int) -> list[tuple[int, int]]:
    return [c for c in ops.rect_cells((0, 0), (width - 1, height - 1)) if c[0] in (0, width - 1) or c[1] in (0, height - 1)]


def _lever_and_gate(ops, scene, key, lever_at, gate_at, event):
    scene, lever = ops.place_blank(scene, key, "Lever", *lever_at)
    scene = ops.set_picture(scene, lever, "assets/sprites/starter_sign.png")
    scene = ops.add_behaviour(scene, lever, "SwitchInteract")
    scene = ops.set_behaviour_param(scene, lever, "SwitchInteract", "event_id", event)
    scene = ops.set_behaviour_param(scene, lever, "SwitchInteract", "one_shot", True)
    scene, gate = ops.place_blank(scene, key, "Gate", *gate_at)
    scene = ops.set_picture(scene, gate, "assets/sprites/door.png")
    scene = ops.set_solid(scene, gate, True)
    scene = ops.add_behaviour(scene, gate, "DoorLock")
    return ops.set_behaviour_param(scene, gate, "DoorLock", "unlock_event", event)


def _enemy(ops, scene, key, sheet, name, at, *, hp, gold, seed):
    scene, enemy = ops.place_blank(scene, key, name, *at)
    scene = ops.set_picture(scene, enemy, sheet)
    scene = ops.set_animation(scene, enemy, ops.character_clips(
        sheet, 32, 48, 4, {"down": 0, "left": 1, "right": 2, "up": 3}, walk_count=4, sheet_rows=4))
    scene = ops.set_entity_fields(scene, enemy, tag="enemy")
    scene = ops.set_solid(scene, enemy, True)
    scene = ops.set_collider(scene, enemy, "box", auto=True)
    scene = ops.add_behaviour(scene, enemy, "Health")
    scene = ops.set_behaviour_param(scene, enemy, "Health", "max_hp", hp)
    scene = ops.set_behaviour_param(scene, enemy, "Health", "hp", hp)
    scene = ops.add_behaviour(scene, enemy, "DropTable")
    scene = ops.set_behaviour_param(scene, enemy, "DropTable", "drops", [{"chance": 1.0, "gold": gold}])
    return ops.set_behaviour_param(scene, enemy, "DropTable", "seed", seed)


def _passages(ops, scene):
    for entity in list(scene["entities"]):
        if entity.get("tag") == "door":
            scene = ops.set_door(scene, entity["id"], style="passage")
    return scene


def main() -> None:
    from mesh_net.world import EXPEDITION_FILES

    OUT.mkdir(exist_ok=True)
    for rel, text in build().items():
        (OUT / EXPEDITION_FILES[rel]).write_text(text, encoding="utf-8", newline=chr(10))


if __name__ == "__main__":
    main()
