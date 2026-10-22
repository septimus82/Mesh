"""Project templates for Mesh Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.swallowed_exceptions import _log_swallow

from . import json_io
from .logging_tools import get_logger

_LOG = get_logger("engine.project_templates")


@dataclass
class Template:
    id: str
    title: str
    description: str
    launcher: bool = False  # offered when creating a game in the Mesh launcher
    preview: str = ""  # engine-relative picture of the template's first room (tooling/make_template_previews.py)


# To add a genre: one entry here and one builder in _BUILDERS. The launcher lists every
# template with launcher=True, in this order.
_TEMPLATES = [
    Template("blank", "Blank Project",
             "An empty grass map and a player who can walk around. Nothing else: "
             "build your own game from scratch.",
             launcher=True, preview="assets/templates/blank.png"),
    Template("adventure", "Top-down Adventure",
             "A small village to explore: a hero you walk with WASD, a villager who talks, "
             "a house you can enter, trees and water in your way. Esc opens the menu to save and load.",
             launcher=True, preview="assets/templates/adventure.png"),
    Template("starter", "Starter Room", "Walkable player and a Guide NPC who says hello."),
    Template("monster", "Monster Test Game", "Blank room plus the companion-monster test data (species, moves, battle sprites, sounds)."),
    # Older scene layout (top-level "layers"); Mesh Studio can't edit these. Kept for the CLI.
    Template("lighting_playground", "Lighting Playground", "Scene with lights, occluders, and fog preset."),
    Template("demo_slice", "Demo Slice", "Interactive scene with NPC, quest, and gameplay mechanics."),
]


def list_templates(*, launcher_only: bool = False) -> list[Template]:
    """The project templates; ``launcher_only`` keeps the ones offered to beginners."""
    return [t for t in _TEMPLATES if t.launcher or not launcher_only]


def apply_template(root: Path, template_id: str) -> None:
    """Apply the specified template to the project at root.

    This assumes base scaffolding (folders, config.json, world file) is already in place.
    """
    _LOG.info("Applying template '%s' to %s", template_id, root)
    builder = _BUILDERS.get(template_id)
    if builder is None:
        _LOG.warning("Unknown template '%s', defaulting to blank", template_id)
        builder = _apply_blank
    builder(root)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    json_io.write_json_atomic(path, data)


def _blank_scene() -> dict[str, Any]:
    return {
        "name": "Start Scene",
        "schema_version": 1,
        "version": 1,
        "entities": [
            {
                "id": "start_player_128_128_0_0",
                "name": "Player",
                "tag": "player",
                "x": 128.0,
                "y": 128.0,
                "sprite": "assets/sprites/animated_player.png",
                "sprite_sheet": {
                    "columns": 4,
                    "rows": 2,
                    "frame_width": 64,
                    "frame_height": 64,
                },
                "animations": {
                    "idle": {"fps": 4, "frames": [0, 1, 2, 3], "loop": True},
                    "walk": {"fps": 8, "frames": [4, 5, 6, 7], "loop": True},
                },
                "behaviours": ["PlayerController", "CameraFollow"],
                "behaviour_config": {
                    "CameraFollow": {"padding": 12, "zoom": 1.0},
                },
            },
        ],
    }


def _apply_blank(root: Path) -> None:
    from .project_ops import STARTER_GRASS, add_map  # noqa: PLC0415  # keep scaffolding import-light

    scene, map_path, skeleton = add_map(_blank_scene(), _START, width=24, height=16, ground=STARTER_GRASS)
    _write_json(root / map_path, skeleton)
    _write_json(root / _START, scene)
    _write_person_prefab(root)


_START = "packs/core_regions/scenes/start.json"


def _write_person_prefab(root: Path) -> None:
    # The "Person" object in Mesh Studio (and Creator Mode's "Add Person").
    json_io.write_json_atomic(
        root / "assets/prefabs.json",
        [{"id": "person", "display_name": "Person", "tags": ["npc", "person"], "entity": _person_entity("Person", "Hello!")}],
    )


def _person_entity(name: str, line: str) -> dict[str, Any]:
    """A talkable NPC: the starter Guide and the shipped ``person`` prefab share this shape."""
    return {
        "name": name,
        "tag": "npc",
        "sprite": "assets/sprites/animated_player.png",
        "sprite_sheet": {"columns": 4, "rows": 2, "frame_width": 64, "frame_height": 64},
        "animations": {"idle": {"fps": 2, "frames": [0, 1], "loop": True}},
        "behaviours": ["Dialogue"],
        "behaviour_config": {
            "Dialogue": {"dialogue": {"speaker": name, "start": "root", "nodes": {"root": {"text": line}}}},
        },
    }


def _apply_starter(root: Path) -> None:
    scene = _blank_scene()
    scene["name"] = "Starter Room"
    guide = _person_entity("Guide", "Hi! Welcome to your new Mesh game.\nWalk with WASD, talk with E.")
    scene["entities"].append({"id": "start_guide_320_128_0_0", **guide, "x": 320.0, "y": 128.0})
    # A grass field to paint on in Mesh Studio (the tileset is copied by create_project).
    from .project_ops import STARTER_GRASS, add_map  # noqa: PLC0415  # keep scaffolding import-light

    scene, map_path, skeleton = add_map(scene, _START, width=24, height=16, ground=STARTER_GRASS)
    _write_json(root / map_path, skeleton)
    _write_json(root / _START, scene)
    _write_person_prefab(root)


def _apply_adventure(root: Path) -> None:
    """A village with a house you can enter, built with the same validated operations as the editor."""
    from . import project_ops as ops  # noqa: PLC0415  # keep scaffolding import-light

    grass, flowers, path, wood, carpet = 1, 2, 3, 5, 7  # the starter tileset's gids
    brick, wood_wall, fence, rock, bush, tree, water = 10, 11, 12, 13, 14, 15, 16

    village = _blank_scene()
    village["name"] = "Village"
    guide = _person_entity("Guide", "Welcome to the village! The house up the path is open: walk into its door.\n"
                                    "Press Esc for the menu, where you can save and load your game.")
    village["entities"].append({"id": "start_guide_320_128_0_0", **guide, "x": 320.0, "y": 128.0})
    village, map_path, skeleton = ops.add_map(village, _START, width=24, height=16, ground=grass)
    _write_json(root / map_path, skeleton)

    def paint(scene: dict[str, Any], layer: str, cells: list[tuple[int, int]], tile: int) -> dict[str, Any]:
        return ops.paint_tiles(scene, layer, cells, tile)

    village = paint(village, ops.GROUND, ops.rect_cells((11, 7), (12, 15)), path)  # up to the house
    village = paint(village, ops.GROUND, ops.rect_cells((2, 12), (21, 12)), path)  # across the village
    village = paint(village, ops.GROUND, [(4, 10), (5, 10), (15, 10), (16, 14), (8, 14), (19, 9)], flowers)
    village = paint(village, ops.WALLS, ops.rect_cells((9, 3), (14, 6)), brick)  # the house
    village = paint(village, ops.WALLS, ops.rect_cells((17, 5), (20, 7)), water)  # a pond
    village = paint(village, ops.WALLS, ops.rect_cells((1, 9), (6, 9)), fence)
    village = paint(village, ops.WALLS, [(2, 2), (4, 1), (6, 3), (19, 2), (21, 3), (22, 10), (1, 14), (21, 14)], tree)
    village = paint(village, ops.WALLS, [(16, 2), (7, 7), (14, 14)], bush)
    village = paint(village, ops.WALLS, [(3, 6), (20, 10)], rock)

    world = json.loads((root / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
    world["scenes"]["start"]["label"] = "Village"
    player = next(e for e in village["entities"] if e.get("tag") == "player")
    world, house, house_key, house_path = ops.new_room(world, "House", "packs/core_regions/scenes", player)
    house, house_map, house_skeleton = ops.add_map(house, house_path, width=14, height=10, ground=wood, border=wood_wall)
    _write_json(root / house_map, house_skeleton)
    house = paint(house, ops.GROUND, ops.rect_cells((5, 4), (8, 6)), carpet)
    house = paint(house, ops.WALLS, [(2, 2), (11, 2)], rock)  # a stool and a chest, near enough
    elder = _person_entity("Grandma", "Come in, dear! Mind the carpet.\nThe way out is the door behind me.")
    house["entities"].append({"id": f"{house_key}_grandma_288_224_0_0", **elder, "x": 288.0, "y": 224.0})
    # Doors: in front of the house's south wall, and at the back of the room. Each arrival
    # spot is 96 px below its door, on the path and inside the room respectively.
    village, house = ops.link_rooms(village, "start", "Village", (384.0, 272.0), house, house_key, "House", (224.0, 272.0))

    _write_json(root / _START, village)
    _write_json(root / house_path, house)
    _write_json(root / "packs/core_regions/worlds/main.json", world)
    _write_person_prefab(root)


def _apply_lighting_playground(root: Path) -> None:
    # Scene with lights and occluders
    scene = {
        "format_version": 1,
        "scene_id": "start",
        "name": "Lighting Playground",
        "world_ambient_light": [50, 50, 60],
        "layers": {
            "background": [
                # Simple floor
                 {"x": 100, "y": 100, "texture": "floor_tile", "layer": "background"}
            ],
            "entities": [
                # Player spawn
                {"type": "player_spawn", "x": 200, "y": 200},
                # Wall (Occluder)
                {"type": "wall", "x": 300, "y": 300, "width": 50, "height": 200},
            ],
            "lights": [
                {
                    "type": "point_light",
                    "x": 400, "y": 300,
                    "radius": 150,
                    "color": [255, 200, 100]
                },
                {
                    "type": "point_light",
                    "x": 100, "y": 100,
                    "radius": 100,
                    "color": [100, 100, 255]
                }
            ]
        }
    }
    _write_json(root / "packs/core_regions/scenes/start.json", scene)

    # Update config to ensure lighting is on
    config_path = root / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["lighting_enabled"] = True
            _write_json(config_path, config)
        except Exception:
            _log_swallow("PROJ-001", "engine/project_templates.py pass-only blanket swallow")
            pass


def _apply_demo_slice(root: Path) -> None:
    # Quest logic
    quest = {
        "id": "intro_quest",
        "title": "Hello World",
        "steps": [
            {"id": "talk_npc", "description": "Talk to the Guide"}
        ]
    }
    _write_json(root / "packs/core_regions/quests/intro.json", quest)

    # Scene with NPC
    scene = {
        "format_version": 1,
        "scene_id": "start",
        "name": "Demo Village",
        "layers": {
             "entities": [
                {"type": "player_spawn", "x": 100, "y": 100},
                {
                    "type": "npc",
                    "x": 300, "y": 100,
                    "name": "Guide",
                    "interaction": {
                        "type": "dialogue",
                        "text": "Welcome to Mesh Engine!",
                        "quest_trigger": "intro_quest"
                    }
                }
             ]
        }
    }
    _write_json(root / "packs/core_regions/scenes/start.json", scene)


_BUILDERS = {
    "blank": _apply_blank,
    "adventure": _apply_adventure,
    "starter": _apply_starter,
    "monster": _apply_blank,  # the monster data itself is copied by create_project
    "lighting_playground": _apply_lighting_playground,
    "demo_slice": _apply_demo_slice,
}
