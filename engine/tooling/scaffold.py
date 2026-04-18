"""Scaffolding helpers for generating new Mesh content."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict

from .. import json_io
from ..encounter_sets import get_theme_manager
from ..scene_loader import SceneLoader
from ..scene_serializer import compact_scene_payload


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

# Template definitions for new scenes
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "empty": {
        "description": "A minimal empty scene.",
        "entities": [],
    },
    "topdown": {
        "description": "A standard top-down scene with a player controller.",
        "entities": [
            {
                "name": "Player",
                "x": 400,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController", "CameraFollow"],
                "behaviour_config": {
                    "PlayerController": {"speed": 150.0},
                    "CameraFollow": {"zoom": 1.0},
                },
            }
        ],
    },
    "dialogue-playground": {
        "description": "A scene demonstrating dialogue interactions.",
        "entities": [
            {
                "name": "Player",
                "x": 200,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController"],
            },
            {
                "name": "Guide",
                "x": 400,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "npc",
                "behaviours": ["Dialogue"],
                "dialogue": {
                    "speaker": "Guide",
                    "lines": ["Hello there!", "Welcome to the dialogue playground."],
                },
            },
        ],
    },
    "overworld": {
        "description": "An outdoor area with a player spawn and one exit.",
        "entities": [
            {
                "name": "Player",
                "x": 400,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController", "CameraFollow"],
            },
            {
                "name": "Exit_To_Somewhere",
                "x": 700,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "door",
                "behaviours": ["SceneTransition"],
                "behaviour_config": {
                    "SceneTransition": {
                        "target_scene": "scenes/target.json",
                        "spawn_point": "Spawn_From_Overworld"
                    }
                }
            }
        ]
    },
    "interior": {
        "description": "An indoor room with an entrance and an exit.",
        "entities": [
            {
                "name": "Player",
                "x": 100,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController", "CameraFollow"],
            },
            {
                "name": "Entrance",
                "x": 50,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "spawn_point",
                "behaviours": []
            },
            {
                "name": "Exit",
                "x": 700,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "door",
                "behaviours": ["SceneTransition"],
                "behaviour_config": {
                    "SceneTransition": {
                        "target_scene": "scenes/outside.json",
                        "spawn_point": "Spawn_From_Interior"
                    }
                }
            }
        ]
    },
    "dungeon": {
        "description": "A dungeon level with entrance and boss placeholder.",
        "entities": [
            {
                "name": "Player",
                "x": 100,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController", "CameraFollow"],
            },
            {
                "name": "Dungeon_Entrance",
                "x": 50,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "spawn_point",
                "behaviours": []
            },
            {
                "name": "Boss_Placeholder",
                "x": 700,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "enemy",
                "behaviours": ["Health", "Patrol"],
                "behaviour_config": {
                    "Health": {"max_hp": 100.0},
                    "Patrol": {"points": [[700, 300], [700, 400]]}
                }
            }
        ]
    },
    "perk-shrine": {
        "description": "A scene with a perk shrine.",
        "entities": [
            {
                "name": "Player",
                "x": 200,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController"],
            },
            {
                "name": "Shrine",
                "x": 400,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "interactable",
                "behaviours": ["OfferPerkChoice"],
                "behaviour_config": {
                    "OfferPerkChoice": {
                        "text": "Touch the shrine to receive a blessing.",
                        "speaker": "Ancient Shrine",
                        "pool": [],
                        "once": True
                    }
                }
            }
        ]
    },
    "ruins": {
        "description": "A crumbled ruins area with ancient structures.",
        "entities": [
            {
                "name": "Player",
                "x": 400,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController", "CameraFollow"],
            },
            {
                "name": "Ruins_Entrance",
                "x": 50,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "spawn_point",
                "behaviours": []
            },
            {
                "name": "To_Dungeon",
                "x": 750,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "door",
                "behaviours": ["SceneTransition"],
                "behaviour_config": {
                    "SceneTransition": {
                        "target_scene": "scenes/target.json",
                        "spawn_point": "Spawn_From_Ruins"
                    }
                }
            }
        ]
    },
    "deep-dungeon": {
        "description": "A dark, multi-layered dungeon environment.",
        "entities": [
            {
                "name": "Player",
                "x": 400,
                "y": 500,
                "sprite": "assets/placeholder.png",
                "tag": "player",
                "behaviours": ["PlayerController", "CameraFollow"],
            },
            {
                "name": "Ladder_Up",
                "x": 400,
                "y": 550,
                "sprite": "assets/placeholder.png",
                "tag": "door",
                "behaviours": ["SceneTransition"],
                "behaviour_config": {
                    "SceneTransition": {
                        "target_scene": "scenes/surface.json",
                        "spawn_point": "Spawn_From_Depths"
                    }
                }
            },
            {
                "name": "Ladder_Down",
                "x": 400,
                "y": 50,
                "sprite": "assets/placeholder.png",
                "tag": "door",
                "behaviours": ["SceneTransition"],
                "behaviour_config": {
                    "SceneTransition": {
                        "target_scene": "scenes/deeper.json",
                        "spawn_point": "Spawn_From_Upper"
                    }
                }
            }
        ]
    },
}


def generate_scene_data(path: str, template_name: str = "empty", extra_args: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    """Generate scene data dict based on a template."""
    target_path = Path(path)
    template = TEMPLATES.get(template_name)
    if not template:
        print(f"[Mesh][Scaffold] ERROR: Unknown template '{template_name}'. Available: {', '.join(TEMPLATES.keys())}")
        return None

    loader = SceneLoader()
    # Start with a minimal valid scene structure
    base_scene = {
        "name": target_path.stem.replace("_", " ").title(),
        "version": 1,
        "description": template.get("description", ""),
        "settings": {},
        "layers": [],
        "entities": list(template.get("entities", [])), # Copy list
    }

    # Inject Metadata
    if extra_args:
        if "scene_kind" in extra_args:
            base_scene["settings"]["scene_kind"] = extra_args["scene_kind"]
        if "region_template" in extra_args:
            base_scene["settings"]["region_template"] = extra_args["region_template"]
        if "encounter_set" in extra_args and extra_args["encounter_set"]:
            base_scene["settings"]["encounter_set_id"] = extra_args["encounter_set"]
        theme_id = None
        if "region_theme" in extra_args and extra_args["region_theme"]:
            theme_id = extra_args["region_theme"]
            base_scene["settings"]["region_theme"] = theme_id

        if "difficulty" in extra_args:
            difficulty = extra_args["difficulty"]
            base_scene["settings"]["encounter_budget_profile"] = difficulty
            # Default base budget for dungeons
            if template_name == "dungeon" or template_name == "deep-dungeon":
                if extra_args.get("with_boss"):
                    base_scene["settings"]["encounter_group_budgets"] = {
                        "default": 100,
                        "boss_guard": 50
                    }
                else:
                    base_scene["settings"]["encounter_budget"] = 10
            elif template_name == "ruins":
                base_scene["settings"]["encounter_budget"] = 8

            # Pacing Defaults
            if extra_args.get("with_boss"):
                # Reserve budget for boss
                reserves = {"easy": 2, "normal": 3, "hard": 4}
                base_scene["settings"]["boss_budget_reserve"] = reserves.get(difficulty, 3)

                # Elite caps
                caps = {"easy": 0, "normal": 1, "hard": 2}
                base_scene["settings"]["elite_cap"] = caps.get(difficulty, 1)

        # Handle Encounter Layouts
        layout = extra_args.get("encounter_layout") if extra_args else None
        if layout:
            base_scene["settings"]["use_theme_spawns"] = True
            base_budget = base_scene["settings"].get("encounter_budget", 10)

            splits = {}
            if layout == "standard":
                splits = {"entry": 0.4, "mid": 0.6}
            elif layout == "bossed":
                splits = {"entry": 0.3, "mid": 0.45, "boss_guard": 0.25}
            elif layout == "gauntlet":
                splits = {"wave_1": 0.333, "wave_2": 0.333, "wave_3": 0.334}

            if splits:
                # Calculate budgets
                group_budgets = {}
                remaining = base_budget
                keys = list(splits.keys())
                for i, key in enumerate(keys):
                    if i == len(keys) - 1:
                        val = remaining # Ensure sum is exact
                    else:
                        val = int(base_budget * splits[key])

                    group_budgets[key] = val
                    remaining -= val

                base_scene["settings"]["encounter_group_budgets"] = group_budgets

                # Inject Placeholders
                # Add 2 placeholders per group
                y_offset = 100
                for group in keys:
                    base_scene["entities"].append({
                        "prefab_id": "theme_enemy_placeholder",
                        "x": 200,
                        "y": y_offset,
                        "encounter_group": group
                    })
                    base_scene["entities"].append({
                        "prefab_id": "theme_enemy_placeholder",
                        "x": 300,
                        "y": y_offset,
                        "encounter_group": group
                    })
                    y_offset += 100

        # Load Theme Data
        if theme_id:
            try:
                themes_path = Path("assets/data/themes.json")
                if themes_path.exists():
                    themes = json.loads(themes_path.read_text(encoding="utf-8"))
                    if theme_id in themes:
                        theme_data = themes[theme_id]

                        # Apply Lighting Hint
                        if "lighting_hint" in theme_data:
                            base_scene["settings"]["lighting_hint"] = theme_data["lighting_hint"]

                        # Apply Ambient Audio
                        if "ambient_audio_key" in theme_data:
                            base_scene["settings"]["ambient_audio"] = theme_data["ambient_audio_key"]
            except Exception as e:
                _log_swallow("SCAF-002", f"Failed to apply theme '{theme_id}': {e}")
                print(f"[Mesh][Scaffold] Warning: Failed to apply theme '{theme_id}': {e}")

    # Handle Boss Injection
    if extra_args and extra_args.get("with_boss") and template_name == "dungeon":
        prefix = extra_args.get("region_prefix", "Region")
        boss_name = f"{prefix.title()}_Boss"

        # Remove placeholder if present
        base_scene["entities"] = [e for e in base_scene["entities"] if e.get("name") != "Boss_Placeholder"]

        # Determine Boss Theme Props
        boss_sprite = "assets/placeholder.png"
        boss_drops = [{"gold": 100, "min_quantity": 50, "max_quantity": 100, "chance": 1.0}]

        if extra_args.get("region_theme"):
             try:
                themes_path = Path("assets/data/themes.json")
                if themes_path.exists():
                    themes = json.loads(themes_path.read_text(encoding="utf-8"))
                    theme_data = themes.get(extra_args["region_theme"], {})
                    if "default_drop_table_id" in theme_data:
                        # In a real system, we'd look up the table. Here we just tag it.
                        boss_drops.append({"table_id": theme_data["default_drop_table_id"], "chance": 1.0})
             except Exception:
                _log_swallow("SCAF-001", "engine/tooling/scaffold.py pass-only blanket swallow")
                pass

        # Add Boss
        base_scene["entities"].append({
            "name": boss_name,
            "x": 600,
            "y": 300,
            "sprite": boss_sprite,
            "tag": "enemy",
            "behaviours": ["Health", "EnemyAI", "DropTable"],
            "behaviour_config": {
                "Health": {
                    "max_health": 100,
                    "current_health": 100
                },
                "EnemyAI": {
                    "speed": 80.0,
                    "damage": 10.0,
                    "detect_radius": 400.0
                },
                "DropTable": {
                    "seed": 12345,
                    "drops": boss_drops
                }
            }
        })

    # Handle Perk Shrine Configuration
    if extra_args and template_name == "perk-shrine":
        perks = extra_args.get("perks", [])
        if perks:
            # Find the Shrine entity
            for entity in base_scene["entities"]:
                if "OfferPerkChoice" in entity.get("behaviours", []):
                    if "behaviour_config" not in entity:
                        entity["behaviour_config"] = {}
                    if "OfferPerkChoice" not in entity["behaviour_config"]:
                        entity["behaviour_config"]["OfferPerkChoice"] = {}

                    entity["behaviour_config"]["OfferPerkChoice"]["pool"] = perks
    # Apply defaults to ensure the file is fully populated
    full_scene = loader.apply_scene_defaults(base_scene)

    # Compact the scene to remove redundant defaults
    final_scene = compact_scene_payload(full_scene)
    return final_scene


def create_scene(path: str, template_name: str = "empty", extra_args: Dict[str, Any] | None = None, force: bool = False) -> bool:
    """Generate a new scene JSON file based on a template."""
    target_path = Path(path)
    if target_path.exists() and not force:
        print(f"[Mesh][Scaffold] ERROR: File '{path}' already exists. Use --force to overwrite.")
        return False

    final_scene = generate_scene_data(path, template_name, extra_args)
    if not final_scene:
        return False

    # Ensure parent directories exist
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        json_io.write_json_atomic(target_path, final_scene)
        print(f"[Mesh][Scaffold] Created new scene at '{path}' using template '{template_name}'")
        return True
    except OSError as exc:
        _log_swallow("SCAF-003", f"Failed to write scene file: {exc}")
        print(f"[Mesh][Scaffold] ERROR: Failed to write scene file: {exc}")
        return False


def create_behaviour(name: str, force: bool = False) -> bool:
    """Generate a new behaviour Python file."""
    # Convert Name to snake_case for the filename
    # e.g. "MyBehaviour" -> "my_behaviour"
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    snake_name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    filename = f"{snake_name}.py"
    target_path = Path("engine/behaviours") / filename

    if target_path.exists() and not force:
        print(f"[Mesh][Scaffold] ERROR: File '{target_path}' already exists. Use --force to overwrite.")
        return False

    class_name = name
    # Ensure class name is valid identifier (basic check)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", class_name):
        print(f"[Mesh][Scaffold] ERROR: Invalid behaviour name '{class_name}'")
        return False

    content = f'''"""{class_name} behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Behaviour
from .registry import register_behaviour

if TYPE_CHECKING:
    from arcade import Sprite
    from engine.game import GameWindow


@register_behaviour(
    "{class_name}",
    description="TODO: Add description for {class_name}.",
    config_fields=[
        # TODO: Add configuration fields here
        # {{
        #     "name": "example_field",
        #     "description": "An example configuration field",
        #     "type": "float",
        #     "default": 1.0,
        # }},
    ],
)
class {class_name}(Behaviour):
    """TODO: Implement behaviour logic."""

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window)
        # TODO: Initialize state from config
        # self.example_field = config.get("example_field", 1.0)

    def update(self, dt: float) -> None:
        """Called every frame."""
        # TODO: Add per-frame logic
        pass

    def on_added(self) -> None:
        """Called when the behaviour is attached to an entity."""
        pass

    def on_removed(self) -> None:
        """Called when the behaviour is removed from an entity."""
        pass
'''

    try:
        with target_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
        print(f"[Mesh][Scaffold] Created new behaviour '{class_name}' at '{target_path}'")
        return True
    except OSError as exc:
        _log_swallow("SCAF-004", f"Failed to write behaviour file: {exc}")
        print(f"[Mesh][Scaffold] ERROR: Failed to write behaviour file: {exc}")
        return False


def create_quest(name: str, target_file: str = "assets/data/quests.json") -> bool:
    """Append a new quest to the quests registry."""
    path = Path(target_file)
    if not path.exists():
        print(f"[Mesh][Scaffold] Creating new quest registry at '{target_file}'")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = []
    else:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    print(f"[Mesh][Scaffold] ERROR: '{target_file}' is not a list of quests.")
                    return False
        except Exception as e:
            _log_swallow("SCAF-005", f"Failed to read '{target_file}': {e}")
            print(f"[Mesh][Scaffold] ERROR: Failed to read '{target_file}': {e}")
            return False

    quest_id = name.lower().replace(" ", "_")

    # Check for duplicates
    if any(q.get("id") == quest_id for q in data):
        print(f"[Mesh][Scaffold] ERROR: Quest '{quest_id}' already exists in '{target_file}'.")
        return False

    new_quest = {
        "id": quest_id,
        "title": name.replace("_", " ").title(),
        "description": "TODO: Add description",
        "state": "inactive",
        "tags": [],
        "requirements": {}
    }

    data.append(new_quest)

    try:
        json_io.write_json_atomic(path, data)
        print(f"[Mesh][Scaffold] Added quest '{quest_id}' to '{target_file}'")
        return True
    except Exception as e:
        _log_swallow("SCAF-006", f"Failed to write '{target_file}': {e}")
        print(f"[Mesh][Scaffold] ERROR: Failed to write '{target_file}': {e}")
        return False


# NPC Templates
NPC_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "guard": {
        "name": "Guard",
        "sprite": "assets/sprites/guard.png",
        "tag": "npc",
        "behaviours": ["Dialogue"],
        "dialogue": {
            "speaker": "Guard",
            "lines": ["Halt!", "Move along citizen."]
        }
    },
    "merchant": {
        "name": "Merchant",
        "sprite": "assets/sprites/merchant.png",
        "tag": "npc",
        "behaviours": ["Dialogue", "Vendor"],
        "dialogue": {
            "speaker": "Merchant",
            "lines": ["Finest wares in the city!", "Take a look."]
        },
        "behaviour_config": {
            "Vendor": {
                "inventory": ["potion", "sword"]
            }
        }
    },
    "quest_giver": {
        "name": "Quest Giver",
        "sprite": "assets/sprites/quest_giver.png",
        "tag": "npc",
        "behaviours": ["Dialogue"],
        "dialogue": {
            "speaker": "Quest Giver",
            "lines": ["I have a task for you.", "Will you help me?"]
        }
    }
}

def get_npc_template(role: str) -> Dict[str, Any] | None:
    return NPC_TEMPLATES.get(role.lower())

def create_npc(role: str, target_scene: str | None = None, x: int = 0, y: int = 0) -> bool:
    """Create an NPC entity and optionally insert it into a scene."""
    role = role.lower()

    if role not in NPC_TEMPLATES:
        print(f"[Mesh][Scaffold] ERROR: Unknown role '{role}'. Available: {', '.join(NPC_TEMPLATES.keys())}")
        return False

    entity: Dict[str, Any] = NPC_TEMPLATES[role].copy()
    entity["x"] = x
    entity["y"] = y

    if target_scene:
        path = Path(target_scene)
        if not path.exists():
            print(f"[Mesh][Scaffold] ERROR: Target scene '{target_scene}' not found.")
            return False

        try:
            with path.open("r", encoding="utf-8") as f:
                scene_data = json.load(f)

            # Append entity
            if "entities" not in scene_data:
                scene_data["entities"] = []
            scene_data["entities"].append(entity)

            # Compact and save
            loader = SceneLoader()
            full_scene = loader.apply_scene_defaults(scene_data)
            compacted = compact_scene_payload(full_scene)

            json_io.write_json_atomic(path, compacted)

            print(f"[Mesh][Scaffold] Added {role} NPC to '{target_scene}' at ({x}, {y})")
            return True

        except Exception as e:
            _log_swallow("SCAF-007", f"ERROR updating scene: {e}")
            print(f"[Mesh][Scaffold] ERROR updating scene: {e}")
            return False
    else:
        # Just print the JSON
        print(json.dumps(entity, indent=2))
        return True


def extract_prefab(prefab_id: str, scene_path: str, entity_name: str, remove_source: bool = False, target_file: str = "assets/prefabs.json") -> bool:
    """Extract an entity from a scene into prefabs.json."""
    path = Path(scene_path)
    if not path.exists():
        print(f"[Mesh][Scaffold] ERROR: Scene '{scene_path}' not found.")
        return False

    try:
        with path.open("r", encoding="utf-8") as f:
            scene_data = json.load(f)

        # Find entity
        entities = scene_data.get("entities", [])
        target_entity = None
        target_index = -1

        for i, ent in enumerate(entities):
            if ent.get("name") == entity_name:
                target_entity = ent
                target_index = i
                break

        if not target_entity:
            print(f"[Mesh][Scaffold] ERROR: Entity '{entity_name}' not found in '{scene_path}'")
            return False

        # Prepare prefab data
        # We should strip x, y from the prefab definition usually, as they are instance specific
        prefab_entity = target_entity.copy()
        if "x" in prefab_entity:
            del prefab_entity["x"]
        if "y" in prefab_entity:
            del prefab_entity["y"]

        new_prefab = {
            "id": prefab_id,
            "display_name": entity_name,
            "entity": prefab_entity
        }

        # Update prefabs.json
        prefabs_path = Path(target_file)
        if prefabs_path.exists():
            with prefabs_path.open("r", encoding="utf-8") as f:
                prefabs = json.load(f)
        else:
            prefabs = []

        # Check if ID exists
        existing_idx = next((i for i, p in enumerate(prefabs) if p["id"] == prefab_id), -1)
        if existing_idx >= 0:
            print(f"[Mesh][Scaffold] Updating existing prefab '{prefab_id}'")
            prefabs[existing_idx] = new_prefab
        else:
            prefabs.append(new_prefab)

        json_io.write_json_atomic(prefabs_path, prefabs)

        print(f"[Mesh][Scaffold] Extracted prefab '{prefab_id}' from '{entity_name}'")

        # Remove source if requested
        if remove_source:
            entities.pop(target_index)

            # Compact and save scene
            loader = SceneLoader()
            full_scene = loader.apply_scene_defaults(scene_data)
            compacted = compact_scene_payload(full_scene)

            json_io.write_json_atomic(path, compacted)
            print(f"[Mesh][Scaffold] Removed source entity from '{scene_path}'")

        return True

    except Exception as e:
        _log_swallow("SCAF-008", f"ERROR extracting prefab: {e}")
        print(f"[Mesh][Scaffold] ERROR extracting prefab: {e}")
        return False


def place_prefab(
    prefab_id: str | None,
    target_scene: str,
    x: int,
    y: int,
    prefabs_file: str = "assets/prefabs.json",
    from_encounter_set: str | None = None,
    as_placeholder: bool = False
) -> bool:
    """Insert a prefab into a scene."""

    # Resolve ID
    variant_id = None
    if from_encounter_set:
        tm = get_theme_manager()
        es = tm.get_encounter_set(from_encounter_set)
        if not es:
            print(f"[Mesh][Scaffold] ERROR: Encounter set '{from_encounter_set}' not found.")
            return False
        if not es.enemy_prefab_ids:
            print(f"[Mesh][Scaffold] ERROR: Encounter set '{from_encounter_set}' has no prefabs.")
            return False
        prefab_id = random.choice(es.enemy_prefab_ids)
        variant_id = es.variant_id
        print(f"[Mesh][Scaffold] Selected prefab '{prefab_id}' from set '{from_encounter_set}' (variant: {variant_id})")

    if not prefab_id:
        print("[Mesh][Scaffold] ERROR: No prefab ID provided.")
        return False

    # Load prefabs to verify existence (optional, but good for safety)
    prefabs_path = Path(prefabs_file)
    if not prefabs_path.exists():
        print(f"[Mesh][Scaffold] ERROR: Prefabs file not found at {prefabs_path}")
        return False

    try:
        with prefabs_path.open("r", encoding="utf-8") as f:
            prefabs = json.load(f)
    except Exception as e:
        _log_swallow("SCAF-009", f"ERROR loading prefabs: {e}")
        print(f"[Mesh][Scaffold] ERROR loading prefabs: {e}")
        return False

    # Find prefab
    prefab = next((p for p in prefabs if p["id"] == prefab_id), None)
    if not prefab:
        print(f"[Mesh][Scaffold] ERROR: Prefab '{prefab_id}' not found.")
        return False

    # Create entity reference
    entity = {
        "prefab_id": prefab_id,
        "x": x,
        "y": y
    }
    if variant_id:
        entity["variant_id"] = variant_id

    if as_placeholder:
        entity["sprite"] = "assets/placeholder.png"

    # Load scene
    path = Path(target_scene)
    if not path.exists():
        print(f"[Mesh][Scaffold] ERROR: Target scene '{target_scene}' not found.")
        return False

    try:
        with path.open("r", encoding="utf-8") as f:
            scene_data = json.load(f)

        if "entities" not in scene_data:
            scene_data["entities"] = []

        scene_data["entities"].append(entity)

        # Compact and save
        loader = SceneLoader()
        full_scene = loader.apply_scene_defaults(scene_data)
        compacted = compact_scene_payload(full_scene)

        json_io.write_json_atomic(path, compacted)

        print(f"[Mesh][Scaffold] Placed prefab '{prefab_id}' into '{target_scene}' at ({x}, {y})")

        # Validate
        from .validate_all import UnifiedValidator
        validator = UnifiedValidator(Path("."), strict_compact=True)
        if not validator.validate_scene(path):
            print("[Mesh][Scaffold] WARNING: Validation failed for modified scene.")
            validator.print_report()
            return False

        return True

    except Exception as e:
        _log_swallow("SCAF-010", f"ERROR placing prefab: {e}")
        print(f"[Mesh][Scaffold] ERROR placing prefab: {e}")
        return False
