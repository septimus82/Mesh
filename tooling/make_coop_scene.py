"""Build mesh_net/coop/ (the N6 co-op room) with Mesh's own authoring tools, reproducibly.

A new blank project (engine.project_scaffold, what Mesh Studio's New Project makes), then the same
engine.project_ops edits Mesh Studio's tools perform: paint walls, place objects, pick pictures, add behaviours
and set their settings. The room keeps Studio's layout: a thin player reference whose definition is the
project's shared ``player`` prefab. Run ``python tooling/make_coop_scene.py`` to rewrite the package files;
tests/test_mesh_net_scene.py checks the committed files equal a fresh build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "mesh_net" / "coop"
SCENE = "packs/core_regions/scenes/start.json"
MAP = "packs/core_regions/maps/start.json"
PREFABS = "assets/prefabs.json"
EVENT = "coop_gate_open"


def build() -> dict[str, str]:
    """{project-relative path: file text} for the room, its map and its prefabs."""
    from engine import project_ops as ops
    from engine.project_scaffold import create_project
    from engine.project_templates import VILLAGER_SHEET

    with TemporaryDirectory(prefix="mesh-coop-") as temp:
        root = Path(temp)
        create_project(root, "Mesh co-op gate")
        scene = json.loads((root / SCENE).read_text(encoding="utf-8"))
        prefabs = json.loads((root / PREFABS).read_text(encoding="utf-8"))
        map_text = (root / MAP).read_text(encoding="utf-8")
    shared = next(p["entity"] for p in prefabs if p.get("id") == ops.PLAYER_PREFAB)
    key = "start"

    player = ops.shared_player_ids(scene)[0]
    scene = ops.expand_players(scene, shared)
    scene = ops.set_entity_fields(scene, player, x=128.0, y=256.0)
    scene = ops.add_behaviour(scene, player, "Combat")
    scene = ops.set_behaviour_param(scene, player, "Combat", "cooldown", 0.5)

    # Walls on the map's collision layer: the room's edge, and a wall at column 13 with a two-tile gap for the gate.
    edge = [c for c in ops.rect_cells((0, 0), (23, 15)) if c[0] in (0, 23) or c[1] in (0, 15)]
    divider = [(13, row) for row in range(1, 15) if row not in (7, 8)]
    scene = ops.paint_tiles(scene, ops.WALLS, edge + divider, ops.STARTER_WALL)

    scene, lever = ops.place_blank(scene, key, "Gate lever", 352, 352)
    scene = ops.set_picture(scene, lever, "assets/sprites/starter_sign.png")
    scene = ops.add_behaviour(scene, lever, "SwitchInteract")
    scene = ops.set_behaviour_param(scene, lever, "SwitchInteract", "event_id", EVENT)
    scene = ops.set_behaviour_param(scene, lever, "SwitchInteract", "one_shot", True)

    scene, gate = ops.place_blank(scene, key, "Gate", 432, 256)
    scene = ops.set_picture(scene, gate, "assets/sprites/door.png")
    scene = ops.set_solid(scene, gate, True)
    scene = ops.add_behaviour(scene, gate, "DoorLock")
    scene = ops.set_behaviour_param(scene, gate, "DoorLock", "unlock_event", EVENT)

    scene, bandit = ops.place_blank(scene, key, "Bandit", 608, 256)
    scene = ops.set_picture(scene, bandit, VILLAGER_SHEET)
    scene = ops.set_animation(scene, bandit, ops.character_clips(
        VILLAGER_SHEET, 32, 48, 4, {"down": 0, "left": 1, "right": 2, "up": 3}, walk_count=4, sheet_rows=4))
    scene = ops.set_entity_fields(scene, bandit, tag="enemy")
    scene = ops.set_solid(scene, bandit, True)
    scene = ops.set_collider(scene, bandit, "box", auto=True)
    scene = ops.add_behaviour(scene, bandit, "Health")
    scene = ops.set_behaviour_param(scene, bandit, "Health", "max_hp", 3)
    scene = ops.set_behaviour_param(scene, bandit, "Health", "hp", 3)
    scene = ops.add_behaviour(scene, bandit, "DropTable")
    scene = ops.set_behaviour_param(scene, bandit, "DropTable", "drops", [{"chance": 1.0, "gold": 10}])
    scene = ops.set_behaviour_param(scene, bandit, "DropTable", "seed", 7)
    scene["name"] = "Co-op Gate"

    scene, definition = ops.split_players(scene, [player], shared)
    assert definition is not None
    prefabs = [ops.player_prefab_entry(definition), *[p for p in prefabs if p.get("id") != ops.PLAYER_PREFAB]]

    def text(doc: object) -> str:
        return json.dumps(doc, indent=2, sort_keys=True) + "\n"

    return {SCENE: text(scene), MAP: map_text, PREFABS: text(prefabs)}


def main() -> None:
    from mesh_net.scene_room import COOP_FILES

    OUT.mkdir(exist_ok=True)
    for rel, text in build().items():
        (OUT / COOP_FILES[rel]).write_text(text, encoding="utf-8", newline=chr(10))


if __name__ == "__main__":
    main()
