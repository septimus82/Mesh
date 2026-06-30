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


def list_templates() -> list[Template]:
    """Return a list of available project templates."""
    return [
        Template("blank", "Blank Project", "Minimal project with empty starting scene."),
        Template("lighting_playground", "Lighting Playground", "Scene with lights, occluders, and fog preset."),
        Template("demo_slice", "Demo Slice", "Interactive scene with NPC, quest, and gameplay mechanics."),
    ]


def apply_template(root: Path, template_id: str) -> None:
    """Apply the specified template to the project at root.
    
    This assumes base scaffolding (folders, config.json) is already in place.
    It will overwrite specific files like start.json or main.json depending on the template.
    """
    _LOG.info("Applying template '%s' to %s", template_id, root)
    if template_id == "blank":
        _apply_blank(root)
    elif template_id == "lighting_playground":
        _apply_lighting_playground(root)
    elif template_id == "demo_slice":
        _apply_demo_slice(root)
    else:
        _LOG.warning("Unknown template '%s', defaulting to blank", template_id)
        _apply_blank(root)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    json_io.write_json_atomic(path, data)


def _apply_blank(root: Path) -> None:
    scene = {
        "name": "Start Scene",
        "settings": {
            "background_color": "dark_blue_gray",
            "music": None,
            "music_volume": 1.0,
        },
        "layers": [
            {"name": "background"},
            {"name": "entities"},
            {"name": "foreground"},
        ],
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
    _write_json(root / "packs/core_regions/scenes/start.json", scene)


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
