import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from engine.tooling.doctor import DoctorRunner
from engine.tooling.explain import ExplainRunner
from engine.tooling.pipeline_runner import run_pipeline_result
from engine import json_io
from engine.tooling.plan_types import Action, Plan


class WizardContext:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.plan_actions: List[Action] = []
        self.root = Path(".")
        self.pack_id = args.pack

        if self.pack_id:
            # Assume packs are in packs/ directory
            self.root = Path("packs") / self.pack_id

    def add_action(self, type: str, args: Dict[str, Any], description: str):
        self.plan_actions.append(Action(type, args, description))

    def to_posix(self, value: str | Path) -> str:
        if isinstance(value, Path):
            return value.as_posix()
        return str(value).replace("\\", "/")

    def resolve_path(self, relative_path: str) -> Path:
        return self.root / relative_path

def wizard_command(args: argparse.Namespace) -> int:
    """Run a wizard to generate a plan (and optionally run the pipeline)."""

    if args.preset:
        _expand_preset(args)

    if args.subcommand == "macro":
        _handle_macro(args)
        return 0

    ctx = WizardContext(args)

    # 0. Init Pack if needed
    if ctx.pack_id and not ctx.root.exists():
        is_wip = args.profile != "release-ready"
        ctx.add_action("init_pack", {
            "path": ctx.to_posix(ctx.root),
            "id": ctx.pack_id,
            "wip": is_wip
        }, f"Initialize content pack '{ctx.pack_id}'")

    if args.subcommand == "new-questline":
        _plan_new_questline(ctx)
    elif args.subcommand == "new-region":
        _plan_new_region(ctx)
    elif args.subcommand == "new-puzzle":
        _plan_new_puzzle(ctx)
    elif args.subcommand in ["shrine", "new-perk-shrine"]:
        _plan_new_perk_shrine(ctx)
    else:
        print(f"[Mesh][Wizard] Unknown subcommand: {args.subcommand}")
        return 1

    # Build Plan Object
    plan = Plan(
        wizard=args.subcommand,
        version=1,
        inputs=vars(args),
        actions=ctx.plan_actions
    )

    # Write plan (always; wizard is an author, not an executor).
    plan_path = args.plan or str(_default_plan_path(args))
    _write_plan(plan, plan_path)

    # Show plan JSON if requested
    if args.dry_run:
        _print_plan(plan)

    world_path = getattr(args, "world", None) or getattr(args, "into_world", None) or "worlds/main_world.json"
    pipeline_cmd = f"mesh pipeline --plan {plan_path} --world {world_path} --ai-safe"
    print("Next step:")
    print(f"  {pipeline_cmd}")

    # --apply is deprecated; keep as alias for running pipeline.
    run_requested = (getattr(args, "run", None) == "__pipeline__") or bool(getattr(args, "apply", False))
    if args.dry_run or not run_requested:
        return 0

    validate_strict = args.profile == "release-ready"
    validate_check_refs = args.profile == "release-ready"
    pipeline_result = run_pipeline_result(
        plan_path=plan_path,
        path=world_path,
        ai_safe=True,
        dry_run=False,
        strict=validate_strict,
        strict_compact=False,
        check_reachability=False,
        check_orphans=False,
        check_refs=validate_check_refs,
        demo=False,
        preset=None,
    )
    if pipeline_result.exit_code == 0:
        return 0

    doctor = DoctorRunner()
    doctor_result = doctor.run_result(world=world_path)
    report = doctor_result.to_doctor_report_dict()
    explainer = ExplainRunner()
    explainer.store_last_failure(doctor_result)

    print(doctor.format_report(report, quiet=False, json_output=False), end="")
    print(explainer.explain_result(doctor_result, json_output=False), end="")
    return int(pipeline_result.exit_code)

def _handle_macro(args: argparse.Namespace) -> None:
    if args.list:
        _list_macros()
        return

    if args.run:
        _run_macro(args)
        return

    print("[Mesh][Wizard] Use --list or --run <name>")

def _list_macros() -> None:
    config = _load_config()
    macros = config.get("wizard_macros", {})
    print("[Mesh][Wizard] Available Macros:")
    for name, data in macros.items():
        print(f"  - {name}: {data.get('wizard')} ({len(data.get('inputs', {}))} inputs)")

def _run_macro(args: argparse.Namespace) -> None:
    config = _load_config()
    macros = config.get("wizard_macros", {})
    name = args.run

    if name not in macros:
        print(f"[Mesh][Wizard] Macro '{name}' not found.")
        return

    macro = macros[name]
    wizard_type = macro.get("wizard")
    inputs = macro.get("inputs", {})

    print(f"[Mesh][Wizard] Running macro '{name}' ({wizard_type})...")

    # Parse vars
    vars_dict = {}
    if hasattr(args, "vars") and args.vars:
        for v in args.vars:
            if "=" in v:
                key, val = v.split("=", 1)
                vars_dict[key] = val

    # Construct args from inputs with substitution
    new_args = argparse.Namespace(**vars(args))
    new_args.subcommand = wizard_type

    for k, v in inputs.items():
        # Convert keys like "name-prefix" to "name_prefix"
        key = k.replace("-", "_")

        # Substitute if string
        final_value = v
        if isinstance(v, str) and "{{" in v and "}}" in v:
            for var_key, var_val in vars_dict.items():
                final_value = final_value.replace(f"{{{{{var_key}}}}}", var_val)

        setattr(new_args, key, final_value)

    # Recurse
    wizard_command(new_args)

def _load_config() -> Dict[str, Any]:
    try:
        raw = json.loads(Path("config.json").read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}

def _expand_preset(args: argparse.Namespace) -> None:
    config = _load_config()
    presets = config.get("wizard_presets", {})
    if args.preset not in presets:
        print(f"[Mesh][Wizard] Preset '{args.preset}' not found.")
        return

    preset_data = presets[args.preset]
    print(f"[Mesh][Wizard] Applying preset '{args.preset}'...")

    if "template" in preset_data and not args.template:
        args.template = preset_data["template"]
    if "theme" in preset_data and not args.theme:
        args.theme = preset_data["theme"]
    if "encounter_set" in preset_data and not args.encounter_set:
        args.encounter_set = preset_data["encounter_set"]
    if "with_boss" in preset_data:
        args.with_boss = preset_data["with_boss"]
    if "with_puzzle" in preset_data:
        args.with_puzzle = preset_data["with_puzzle"]

def _plan_new_region(ctx: WizardContext) -> None:
    args = ctx.args
    prefix = args.name_prefix
    region_template = args.template or "hub-interior-dungeon"

    # 1. Define Scenes based on Template
    scenes = {}
    scene_kinds = {} # Map key -> kind (hub, interior, dungeon, etc)

    if region_template == "hub-interior-dungeon":
        scenes = {
            "hub": f"{prefix}_hub",
            "interior": f"{prefix}_interior",
            "dungeon": f"{prefix}_dungeon"
        }
        scene_kinds = {
            "hub": "hub",
            "interior": "interior",
            "dungeon": "dungeon"
        }
    elif region_template == "ruins":
        scenes = {
            "hub": f"{prefix}_hub",
            "path": f"{prefix}_path",
            "dungeon": f"{prefix}_dungeon"
        }
        scene_kinds = {
            "hub": "hub",
            "path": "path", # Path acts as overworld connector
            "dungeon": "dungeon"
        }
    elif region_template == "deep-dungeon":
        scenes = {
            "entry": f"{prefix}_entry",
            "depths": f"{prefix}_depths"
        }
        scene_kinds = {
            "entry": "interior", # Entry is like an interior/antechamber
            "depths": "dungeon"
        }
    else:
        print(f"[Mesh][Wizard] Unknown region template: {region_template}")
        return

    scene_paths = {}
    for key, name in scenes.items():
        path = ctx.resolve_path(f"scenes/{name}.json")
        scene_paths[key] = path

        # Determine scaffold template
        kind = scene_kinds.get(key, "empty")
        scaffold_template = "empty"
        if kind == "hub":
            scaffold_template = "overworld"
        elif kind == "interior":
            scaffold_template = "interior"
        elif kind == "dungeon":
            scaffold_template = "dungeon"
        elif kind == "overworld":
            scaffold_template = "overworld"

        # Special handling for ruins/deep-dungeon specific scaffold templates if we wanted,
        # but reusing generic ones with metadata is cleaner for now,
        # UNLESS we want specific layouts.
        # The prompt asked for "ruins" and "deep-dungeon" templates in scaffold.
        # So we should use them if applicable.

        if region_template == "ruins":
            scaffold_template = "ruins" if key == "hub" else ("overworld" if key == "path" else "dungeon")
        elif region_template == "deep-dungeon":
            scaffold_template = "deep-dungeon" if key == "entry" else "dungeon"

        ctx.add_action("create_scene", {
            "path": ctx.to_posix(path),
            "template": scaffold_template,
            "with_boss": args.with_boss if kind == "dungeon" else False,
            "region_prefix": prefix,
            "scene_kind": kind,
            "region_template": region_template,
            "region_theme": args.theme,
            "encounter_set": args.encounter_set,
            "difficulty": args.difficulty
        }, f"Create {key} scene '{name}'")

    # 2. Place NPCs
    # Only place default NPCs for the standard template for now, or adapt logic
    if region_template == "hub-interior-dungeon":
        # Merchant in Hub
        ctx.add_action("add_npc", {
            "scene_path": ctx.to_posix(scene_paths["hub"]),
            "name": f"{prefix}_Merchant",
            "role": "merchant",
            "quest_id": None
        }, "Add Merchant to Hub")

        # Guard in Hub
        ctx.add_action("add_npc", {
            "scene_path": ctx.to_posix(scene_paths["hub"]),
            "name": f"{prefix}_Guard",
            "role": "guard",
            "quest_id": None
        }, "Add Guard to Hub")

        # QuestGiver in Interior
        ctx.add_action("add_npc", {
            "scene_path": ctx.to_posix(scene_paths["interior"]),
            "name": f"{prefix}_Elder",
            "role": "quest_giver",
            "quest_id": f"{prefix}_fetch_quest"
        }, "Add Elder to Interior")

    # For other templates, maybe add minimal NPCs?
    if region_template == "ruins" and "hub" in scene_paths:
         ctx.add_action("add_npc", {
            "scene_path": ctx.to_posix(scene_paths["hub"]),
            "name": f"{prefix}_Explorer",
            "role": "quest_giver",
            "quest_id": f"{prefix}_explore_quest"
        }, "Add Explorer to Ruins Hub")

    # 3. Create Quests
    quests_path = ctx.resolve_path("assets/data/quests.json")

    if region_template == "hub-interior-dungeon":
        ctx.add_action("create_quest", {
            "path": ctx.to_posix(quests_path),
            "id": f"{prefix}_fetch_quest",
            "title": f"{prefix.title()} Fetch",
            "type": "fetch"
        }, "Create Fetch Quest")

        ctx.add_action("create_quest", {
            "path": ctx.to_posix(quests_path),
            "id": f"{prefix}_kill_quest",
            "title": f"{prefix.title()} Hunt",
            "type": "kill"
        }, "Create Kill Quest")
    elif region_template == "ruins":
         ctx.add_action("create_quest", {
            "path": ctx.to_posix(quests_path),
            "id": f"{prefix}_explore_quest",
            "title": f"Explore {prefix.title()}",
            "type": "fetch" # Placeholder
        }, "Create Explore Quest")

    # 3b. Add Puzzle (Optional)
    if args.with_puzzle:
        # Find a dungeon scene
        dungeon_key = next((k for k, v in scene_kinds.items() if v == "dungeon"), None)
        if dungeon_key:
            ctx.add_action("add_puzzle_switch_door", {
                "scene_path": ctx.to_posix(scene_paths[dungeon_key]),
                "id_prefix": f"{prefix}_dungeon_puzzle",
                "switch": {"x": 600, "y": 600},
                "door": {"x": 700, "y": 600},
                "reward": {"x": 700, "y": 700, "gold": 100}
            }, "Add Dungeon Puzzle")

    # 3c. Add Perk Shrine (Optional)
    if args.perks:
        # Find a suitable scene (hub or entry)
        shrine_key = "hub" if "hub" in scenes else ("entry" if "entry" in scenes else None)

        # Create a separate shrine scene and link it
        shrine_name = f"{prefix}_shrine"
        shrine_path = ctx.resolve_path(f"scenes/{shrine_name}.json")
        ctx.add_action("create_scene", {
            "path": ctx.to_posix(shrine_path),
            "template": "perk-shrine",
            "perks": args.perks.split(",")
        }, "Create Shrine Scene")

        # Link it from somewhere
        link_from_key = "hub" if "hub" in scenes else ("entry" if "entry" in scenes else None)
        if link_from_key:
            ctx.add_action("wire_world", {
                "world_path": ctx.to_posix(args.into_world),
                "scene_path": ctx.to_posix(shrine_path),
                "scene_id": shrine_name,
                "link_from": scenes[link_from_key]
            }, "Link Shrine")


    # 4. Wire World & Links
    if args.into_world:
        # Register all scenes
        for key, name in scenes.items():
            ctx.add_action("wire_world", {
                "world_path": ctx.to_posix(args.into_world),
                "scene_path": ctx.to_posix(scene_paths[key]),
                "scene_id": name
            }, f"Register {name} in world")

        # Link Logic based on Template
        if region_template == "hub-interior-dungeon":
            # Link Hub <-> Interior
            ctx.add_action("wire_world", {
                "world_path": ctx.to_posix(args.into_world),
                "scene_path": ctx.to_posix(scene_paths["interior"]),
                "scene_id": scenes["interior"],
                "link_from": scenes["hub"]
            }, "Link Hub <-> Interior")

            # Link Hub <-> Dungeon
            ctx.add_action("wire_world", {
                "world_path": ctx.to_posix(args.into_world),
                "scene_path": ctx.to_posix(scene_paths["dungeon"]),
                "scene_id": scenes["dungeon"],
                "link_from": scenes["hub"]
            }, "Link Hub <-> Dungeon")

        elif region_template == "ruins":
            # Hub <-> Path
            ctx.add_action("wire_world", {
                "world_path": ctx.to_posix(args.into_world),
                "scene_path": ctx.to_posix(scene_paths["path"]),
                "scene_id": scenes["path"],
                "link_from": scenes["hub"]
            }, "Link Hub <-> Path")

            # Path <-> Dungeon
            ctx.add_action("wire_world", {
                "world_path": ctx.to_posix(args.into_world),
                "scene_path": ctx.to_posix(scene_paths["dungeon"]),
                "scene_id": scenes["dungeon"],
                "link_from": scenes["path"]
            }, "Link Path <-> Dungeon")

        elif region_template == "deep-dungeon":
            # Entry <-> Depths
            ctx.add_action("wire_world", {
                "world_path": ctx.to_posix(args.into_world),
                "scene_path": ctx.to_posix(scene_paths["depths"]),
                "scene_id": scenes["depths"],
                "link_from": scenes["entry"]
            }, "Link Entry <-> Depths")

        # Auto-wire transitions (if profile is safe or release-ready)
        if args.profile in ["safe", "release-ready"]:
            ctx.add_action("auto_wire_transitions", {
                "world_path": ctx.to_posix(args.into_world)
            }, "Auto-wire transitions")

    # 5. Polish
    profile = args.profile
    for path in scene_paths.values():
        ctx.add_action("polish_scene", {
            "path": ctx.to_posix(path),
            "compact_only": profile == "fast"
        }, f"Polish {path.name}")


def _plan_new_questline(ctx: WizardContext) -> None:
    args = ctx.args

    # 1. Create Scene
    scene_name = f"{args.name_prefix}_scene.json"
    scene_path = ctx.resolve_path(f"scenes/{scene_name}")

    ctx.add_action("create_scene", {
        "path": ctx.to_posix(scene_path),
        "template": args.scene or "empty"
    }, f"Create scene '{scene_name}'")

    # 2. Add NPC
    role = args.npc_role or "quest_giver"
    ctx.add_action("add_npc", {
        "scene_path": ctx.to_posix(scene_path),
        "name": f"{args.name_prefix}_NPC",
        "role": role,
        "quest_id": f"{args.name_prefix}_quest"
    }, f"Add NPC '{args.name_prefix}_NPC' to scene")

    # 3. Create Quest
    quest_id = f"{args.name_prefix}_quest"
    quests_path = ctx.resolve_path("assets/data/quests.json")

    ctx.add_action("create_quest", {
        "path": ctx.to_posix(quests_path),
        "id": quest_id,
        "title": f"{args.name_prefix.replace('_', ' ').title()} Quest",
        "type": args.quest_type or "fetch"
    }, f"Create quest '{quest_id}'")

    # 4. World Wiring
    if args.into_world:
        ctx.add_action("wire_world", {
            "world_path": ctx.to_posix(args.into_world),
            "scene_path": ctx.to_posix(scene_path),
            "scene_id": args.name_prefix, # Use prefix as ID? Or derive from name
            "link_from": args.link_from
        }, f"Wire scene into world '{args.into_world}'")

    # 5. Polish
    profile = args.profile
    ctx.add_action("polish_scene", {
        "path": ctx.to_posix(scene_path),
        "compact_only": profile == "fast"
    }, "Polish scene")

def _plan_new_perk_shrine(ctx: WizardContext) -> None:
    args = ctx.args
    name = args.name
    perks = args.perks.split(",") if args.perks else []

    # 1. Create Shrine Scene
    scene_name = f"{name}.json"
    scene_path = ctx.resolve_path(f"scenes/{scene_name}")

    ctx.add_action("create_scene", {
        "path": ctx.to_posix(scene_path),
        "template": "perk-shrine",
        "perks": perks
    }, f"Create perk shrine scene '{scene_name}'")

    # 2. Wire into World
    if args.into_world:
        ctx.add_action("wire_world", {
            "world_path": ctx.to_posix(args.into_world),
            "scene_path": ctx.to_posix(scene_path),
            "scene_id": name,
            "link_from": args.link_from
        }, f"Wire shrine into world '{args.into_world}'")

    # 3. Polish
    profile = args.profile
    ctx.add_action("polish_scene", {
        "path": ctx.to_posix(scene_path),
        "compact_only": profile == "fast"
    }, "Polish scene")

def _plan_new_puzzle(ctx: WizardContext) -> None:
    args = ctx.args
    scene_path = args.scene
    if not scene_path:
        print("[Mesh][Wizard] Error: --scene is required for new-puzzle")
        return

    # Resolve path if it's just a name
    if not scene_path.endswith(".json"):
        scene_path += ".json"

    # If it's a relative path, try to resolve it
    path = Path(scene_path)
    if not path.is_absolute():
        # Try to find it in ctx.root/scenes or just ctx.root
        if (ctx.root / "scenes" / scene_path).exists():
            path = ctx.root / "scenes" / scene_path
        elif (ctx.root / scene_path).exists():
            path = ctx.root / scene_path
        else:
            # Default to scenes/
            path = ctx.root / "scenes" / scene_path

    ctx.add_action("add_puzzle_switch_door", {
        "scene_path": ctx.to_posix(path),
        "id_prefix": args.name_prefix or "puzzle",
        "switch": {"x": 400, "y": 400},
        "door": {"x": 500, "y": 400},
        "reward": {"x": 500, "y": 500, "gold": 50}
    }, f"Add puzzle to '{path.name}'")

def _write_plan(plan: Plan, path: str) -> None:
    json_io.write_json_atomic(path, asdict(plan))
    print(f"[Mesh][Wizard] Plan written to {path}")

def _print_plan(plan: Plan) -> None:
    print(json.dumps(asdict(plan), indent=2))

def _default_plan_path(args: argparse.Namespace) -> Path:
    slug_parts = [args.subcommand]
    if getattr(args, "pack", None):
        slug_parts.append(str(args.pack))
    slug = "_".join(slug_parts).replace("/", "_").replace("\\", "_")
    return Path(".mesh/plan_history") / f"wizard_{slug}.json"

def add_wizard_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("subcommand", choices=["new-region", "macro", "shrine", "new-perk-shrine", "new-questline", "new-puzzle"], help="Wizard command to run")
    parser.add_argument("--name-prefix", help="Prefix for generated IDs")
    parser.add_argument("--name", help="Name for the new content")
    parser.add_argument("--perks", help="List of perk IDs to include (comma separated)")
    parser.add_argument("--apply", action="store_true", help="(Deprecated) Alias for --run pipeline")
    parser.add_argument("--scene", help="Scene template or path")
    parser.add_argument("--pack", help="Content pack ID")
    parser.add_argument("--plan", help="Output plan path")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--into-world", help="World file to wire into")
    parser.add_argument("--world", help="World file to validate/run pipeline against")
    parser.add_argument("--link-from", help="Scene ID to link from")
    parser.add_argument("--profile", default="safe", help="Execution profile")
    parser.add_argument("--npc-role", help="Role for new NPC")
    parser.add_argument("--quest-type", help="Type of quest")
    parser.add_argument("--vars", nargs="*", help="Variables for macro")
    parser.add_argument("--run", nargs="?", const="__pipeline__", help="Run the pipeline (or a macro when used with 'macro')")
    parser.add_argument("--list", action="store_true", help="List macros")
    parser.add_argument("--with-boss", action="store_true", help="Include boss")
    parser.add_argument("--with-puzzle", action="store_true", help="Include puzzle")
    parser.add_argument("--template", help="Region template (hub-interior-dungeon, ruins, deep-dungeon)")
    parser.add_argument("--theme", help="Region theme ID")
    parser.add_argument("--encounter-set", help="Encounter Set ID")
    parser.add_argument("--preset", help="Wizard preset ID")
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard"], default="normal", help="Encounter difficulty")

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Content Wizard")
    add_wizard_arguments(parser)
    args = parser.parse_args(argv)

    try:
        return int(wizard_command(args))
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
