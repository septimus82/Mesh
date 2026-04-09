from __future__ import annotations

import argparse
import bisect
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine import json_io

@dataclass(frozen=True, slots=True)
class ScaffoldSpec:
    location: str
    kind: str
    variant_letter: str
    gold: int

    world_prefix: str
    quest_prefix: str
    zone_suffix: str
    case_variant: str

    preset_name: str
    world_path: str
    scene_path: str


def add_golden_slice_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("golden-slice", help="Golden Slice tooling")
    subs = parser.add_subparsers(dest="golden_slice_command", help="Golden Slice subcommands")

    scaffold = subs.add_parser("scaffold", help="Scaffold a new Golden Slice variant (content + registration)")
    scaffold.add_argument("--location", required=True, help="Location id (e.g. hollowmere_outskirts)")
    scaffold.add_argument(
        "--kind",
        required=True,
        choices=["linear", "branching_choice", "puzzle_lite"],
        help="Variant archetype",
    )
    scaffold.add_argument("--variant", required=True, help="Variant letter (e.g. L)")
    scaffold.add_argument("--gold", required=True, type=int, help="Gold reward for the completion quest")
    scaffold.add_argument("--dry-run", action="store_true", help="Show planned writes without modifying files")
    scaffold.add_argument(
        "--register",
        action="store_true",
        help="Register the new preset in the canonical *_showcase_all source for picker discovery",
    )
    scaffold.set_defaults(func=golden_slice_scaffold_command)


def golden_slice_scaffold_command(args: argparse.Namespace) -> int:
    try:
        spec = _parse_spec(args)
        dry_run = bool(getattr(args, "dry_run", False))
        register = bool(getattr(args, "register", False))
        planned: list[tuple[str, str]] = []
        _scaffold(spec, base_dir=Path("."), dry_run=dry_run, planned=planned, register=register)
        if dry_run:
            if not planned:
                print("[Mesh][GoldenSlice][dry-run] no changes")
            else:
                for path, summary in planned:
                    print(f"[Mesh][GoldenSlice][dry-run] {path}: {summary}")
        return 0
    except ValueError as exc:
        print(f"[Mesh][GoldenSlice] ERROR: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001  # REASON: scaffold command failures should report the error and return a controlled nonzero exit code
        print(f"[Mesh][GoldenSlice] ERROR: {exc!r}")
        return 1


def _parse_spec(args: argparse.Namespace) -> ScaffoldSpec:
    location = str(getattr(args, "location", "") or "").strip().lower()
    if not location or not re.fullmatch(r"[a-z0-9_]+", location):
        raise ValueError("location must be snake_case (letters/digits/underscores).")

    kind = str(getattr(args, "kind", "") or "").strip()
    if kind not in {"linear", "branching_choice", "puzzle_lite"}:
        raise ValueError("kind must be one of: linear, branching_choice, puzzle_lite.")

    variant = str(getattr(args, "variant", "") or "").strip()
    if not re.fullmatch(r"[A-Za-z]", variant):
        raise ValueError("variant must be a single letter (A-Z).")
    variant_letter = variant.lower()

    gold = int(getattr(args, "gold", 0))
    if gold <= 0 or gold > 10_000:
        raise ValueError("gold must be a positive integer <= 10000.")

    if location in {"ridge_outpost", "ridge_outpost_dungeon"}:
        world_prefix = "golden_slice"
        quest_prefix = "ridge"
        zone_suffix = ""
        case_variant = variant_letter
    else:
        world_prefix = "golden_slice2"
        quest_prefix = "ridge2"
        zone_suffix = "2"
        case_variant = f"{variant_letter}2"

    preset_name = f"{world_prefix}_variant_{variant_letter}"
    world_path = f"worlds/{world_prefix}_variant_{variant_letter}.json"

    if location in {"ridge_outpost", "ridge_outpost_dungeon"}:
        scene_path = f"packs/core_regions/scenes/Ridge Outpost_dungeon_variant_{variant_letter}.json"
    else:
        scene_location = location[0].upper() + location[1:]
        scene_path = f"packs/core_regions/scenes/{scene_location}_variant_{variant_letter}.json"

    return ScaffoldSpec(
        location=location,
        kind=kind,
        variant_letter=variant_letter,
        gold=gold,
        world_prefix=world_prefix,
        quest_prefix=quest_prefix,
        zone_suffix=zone_suffix,
        case_variant=case_variant,
        preset_name=preset_name,
        world_path=world_path,
        scene_path=scene_path,
    )


def _scaffold(
    spec: ScaffoldSpec,
    *,
    base_dir: Path,
    dry_run: bool,
    planned: list[tuple[str, str]],
    register: bool,
) -> None:
    _write_scene(spec, base_dir=base_dir, dry_run=dry_run, planned=planned)
    _write_world(spec, base_dir=base_dir, dry_run=dry_run, planned=planned)
    _upsert_config_preset(spec, base_dir=base_dir, dry_run=dry_run, planned=planned, register=register)
    _upsert_quests(spec, base_dir=base_dir, dry_run=dry_run, planned=planned)
    _upsert_events(spec, base_dir=base_dir, dry_run=dry_run, planned=planned)
    _upsert_variant_contract_case(spec, base_dir=base_dir, dry_run=dry_run, planned=planned)


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} root must be an object.")
    return raw


def _write_json_file(
    path: Path,
    payload: Any,
    *,
    dry_run: bool,
    planned: list[tuple[str, str]],
) -> None:
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001  # REASON: pre-existing scaffold files with invalid JSON should fail fast as a controlled validation error
            raise ValueError(f"{path} exists but is not valid JSON: {exc}") from exc
        if existing == payload:
            return
        raise ValueError(f"{path} already exists with different content.")
    if dry_run:
        planned.append((path.as_posix(), "would create new file"))
        return
    json_io.write_json_atomic(path, payload)


def _write_scene(
    spec: ScaffoldSpec,
    *,
    base_dir: Path,
    dry_run: bool,
    planned: list[tuple[str, str]],
) -> None:
    variant = spec.variant_letter.upper()
    suffix = spec.zone_suffix
    start_zone = f"Variant{variant}StartZone{suffix}"
    goal_zone = f"Variant{variant}GoalZone{suffix}"
    on_start = f"variant_{spec.variant_letter}{suffix}_start"
    on_goal = f"variant_{spec.variant_letter}{suffix}_goal"

    entities: list[dict[str, Any]] = [
        {
            "name": "Player",
            "x": 100,
            "y": 300,
            "sprite": "assets/placeholder.png",
            "tag": "player",
            "behaviours": ["PlayerController", "Health", "Combat", "CameraFollow"],
        },
        {
            "name": "Entrance",
            "x": 50,
            "y": 300,
            "sprite": "assets/placeholder.png",
            "tag": "spawn_point",
            "behaviours": [],
        },
        {
            "name": start_zone,
            "x": 140,
            "y": 300,
            "sprite": "assets/placeholder.png",
            "tag": "trigger",
            "behaviours": ["TriggerZone"],
            "behaviour_config": {
                "TriggerZone": {
                    "trigger_radius": 48.0,
                    "trigger_target": "Player",
                    "on_trigger": on_start,
                }
            },
        },
    ]

    if spec.kind == "branching_choice":
        choice_a = f"Variant{variant}ChoiceAZone{suffix}"
        choice_b = f"Variant{variant}ChoiceBZone{suffix}"
        goal_a = f"Variant{variant}GoalAZone{suffix}"
        goal_b = f"Variant{variant}GoalBZone{suffix}"
        entities.extend(
            [
                {
                    "name": choice_a,
                    "x": 420,
                    "y": 260,
                    "sprite": "assets/placeholder.png",
                    "tag": "trigger",
                    "behaviours": ["TriggerZone"],
                    "behaviour_config": {
                        "TriggerZone": {
                            "trigger_radius": 48.0,
                            "trigger_target": "Player",
                            "on_trigger": f"variant_{spec.variant_letter}{suffix}_choice_a",
                        }
                    },
                },
                {
                    "name": choice_b,
                    "x": 420,
                    "y": 340,
                    "sprite": "assets/placeholder.png",
                    "tag": "trigger",
                    "behaviours": ["TriggerZone"],
                    "behaviour_config": {
                        "TriggerZone": {
                            "trigger_radius": 48.0,
                            "trigger_target": "Player",
                            "on_trigger": f"variant_{spec.variant_letter}{suffix}_choice_b",
                        }
                    },
                },
                {
                    "name": goal_a,
                    "x": 980,
                    "y": 260,
                    "sprite": "assets/placeholder.png",
                    "tag": "trigger",
                    "behaviours": ["TriggerZone"],
                    "behaviour_config": {
                        "TriggerZone": {
                            "trigger_radius": 56.0,
                            "trigger_target": "Player",
                            "on_trigger": f"variant_{spec.variant_letter}{suffix}_goal_a",
                        }
                    },
                },
                {
                    "name": goal_b,
                    "x": 980,
                    "y": 340,
                    "sprite": "assets/placeholder.png",
                    "tag": "trigger",
                    "behaviours": ["TriggerZone"],
                    "behaviour_config": {
                        "TriggerZone": {
                            "trigger_radius": 56.0,
                            "trigger_target": "Player",
                            "on_trigger": f"variant_{spec.variant_letter}{suffix}_goal_b",
                        }
                    },
                },
            ]
        )

    if spec.kind == "puzzle_lite":
        unlock_event = f"{spec.quest_prefix}_variant_{spec.variant_letter}_unlock"
        entities.extend(
            [
                {
                    "name": "ridge_variant_k_switch",
                    "x": 520,
                    "y": 300,
                    "sprite": "assets/placeholder.png",
                    "tag": "interactable",
                    "behaviours": ["SwitchInteract"],
                    "behaviour_config": {
                        "SwitchInteract": {
                            "event_id": unlock_event,
                            "one_shot": True,
                            "active_sprite": "",
                        }
                    },
                },
                {
                    "name": f"{spec.quest_prefix}_variant_{spec.variant_letter}_door",
                    "x": 640,
                    "y": 300,
                    "sprite": "assets/placeholder.png",
                    "tag": "solid",
                    "solid": True,
                    "behaviours": ["DoorLock"],
                    "behaviour_config": {
                        "DoorLock": {
                            "unlock_event": unlock_event,
                            "starts_locked": True,
                            "open_sprite": "",
                        }
                    },
                },
            ]
        )

    entities.append(
        {
            "mesh_name": f"{spec.location.split('_')[0].title()}_Boss",
            "x": 900,
            "y": 300,
            "tag": "enemy",
            "tags": ["boss"],
            "prefab_id": "slime_blob",
            "variant_id": "boss_variant_b",
            "behaviours": ["Health", "EnemyAI", "DropTable"],
            "behaviour_config": {
                "Health": {"max_hp": 100, "hp": 100},
                "EnemyAI": {"speed": 60.0, "detect_radius": 250.0},
                "DropTable": {
                    "seed": 9800 + ord(spec.variant_letter),
                    "drops": [
                        {"item_id": "warden_mace", "chance": 1.0},
                        {"gold": 10, "chance": 1.0},
                    ],
                },
            },
        }
    )

    if spec.kind != "branching_choice":
        entities.append(
            {
                "name": goal_zone,
                "x": 980,
                "y": 300,
                "sprite": "assets/placeholder.png",
                "tag": "trigger",
                "behaviours": ["TriggerZone"],
                "behaviour_config": {
                    "TriggerZone": {
                        "trigger_radius": 56.0,
                        "trigger_target": "Player",
                        "on_trigger": on_goal,
                    }
                },
            }
        )

    entities.append(
        {
            "name": "Exit",
            "x": 1000,
            "y": 300,
            "sprite": "assets/placeholder.png",
            "tag": "door",
            "behaviours": ["SceneTransition"],
            "behaviour_config": {"SceneTransition": {"target_scene": "packs/core_regions/scenes/Hollow Grove_hub.json"}},
        }
    )

    payload = {
        "name": f"{spec.location.replace('_', ' ').title()} (Variant {variant}{suffix})",
        "version": 1,
        "description": f"Scaffolded Golden Slice variant {variant}{suffix} ({spec.kind}).",
        "layers": [
            {
                "name": "entities",
                "entities": {
                    "1": {
                        "type": "prop",
                        "x": 0,
                        "y": 0,
                        "behaviours": {
                            "SceneTransition": {
                                "target_scene": "packs/core_regions/scenes/Hollow Grove_hub.json",
                                "spawn_point": "default",
                            }
                        },
                        "tags": ["auto_wired"],
                    }
                },
            }
        ],
        "entities": entities,
        "schema_version": 1,
    }

    _write_json_file(base_dir / spec.scene_path, payload, dry_run=dry_run, planned=planned)


def _write_world(
    spec: ScaffoldSpec,
    *,
    base_dir: Path,
    dry_run: bool,
    planned: list[tuple[str, str]],
) -> None:
    if spec.location in {"ridge_outpost", "ridge_outpost_dungeon"}:
        scene_key = "Ridge Outpost_dungeon"
    else:
        scene_key = spec.location[0].upper() + spec.location[1:]
    payload = {
        "id": f"{spec.world_prefix}_variant_{spec.variant_letter}",
        "start_scene": scene_key,
        "start_spawn": "default",
        "scenes": {
            scene_key: {
                "path": spec.scene_path.replace("\\", "/"),
                "label": f"{scene_key} ({spec.variant_letter.upper()}{spec.zone_suffix})",
                "tags": ["dungeon"],
            }
        },
    }
    _write_json_file(base_dir / spec.world_path, payload, dry_run=dry_run, planned=planned)


def _upsert_config_preset(
    spec: ScaffoldSpec,
    *,
    base_dir: Path,
    dry_run: bool,
    planned: list[tuple[str, str]],
    register: bool,
) -> None:
    config_path = base_dir / "config.json"
    if not config_path.exists():
        raise ValueError("config.json not found in current directory.")
    config = _read_json(config_path)

    presets = config.get("presets")
    if presets is None:
        presets = {}
        config["presets"] = presets
    if not isinstance(presets, dict):
        raise ValueError("config.json presets must be an object.")

    preset_payload = {
        "description": f"{spec.location.replace('_', ' ').title()}: {spec.kind} (scaffolded)",
        "notes": f"Scaffolded {spec.world_prefix} variant {spec.variant_letter.upper()}{spec.zone_suffix}",
        "lighting_showcase": False,
        "steps": [
            {
                "cmd": "pipeline",
                "args": [
                    "--plan",
                    "plans/golden_slice_noop.json",
                    "--world",
                    spec.world_path.replace("\\", "/"),
                    "--dry-run",
                    "--strict",
                    "--check-refs",
                ],
            },
            {
                "cmd": "pipeline",
                "args": [
                    "--plan",
                    "plans/golden_slice_noop.json",
                    "--world",
                    spec.world_path.replace("\\", "/"),
                    "--dry-run",
                    "--demo",
                ],
            },
        ],
    }

    added_preset = False
    registered = False

    existing = presets.get(spec.preset_name)
    if existing is not None and existing != preset_payload:
        raise ValueError(f"config.json preset '{spec.preset_name}' already exists with different content.")

    if existing is None:
        presets[spec.preset_name] = preset_payload
        added_preset = True

    if register:
        if spec.world_prefix == "golden_slice":
            showcase_all_name = "golden_slice_showcase_all"
        else:
            showcase_all_name = "golden_slice2_showcase_all"
        registered = _register_preset_in_showcase_all(
            presets=presets,
            showcase_all_name=showcase_all_name,
            preset_name=spec.preset_name,
        )

    config["presets"] = dict(sorted(presets.items(), key=lambda kv: kv[0]))
    new_text = json_io.dumps_stable(config) + "\n"
    old_text = config_path.read_text(encoding="utf-8")
    if new_text == old_text:
        return
    if dry_run:
        if added_preset:
            planned.append((config_path.as_posix(), f"would add preset '{spec.preset_name}' (sorted)"))
        if registered:
            planned.append(
                (
                    config_path.as_posix(),
                    f"would register '{spec.preset_name}' in {showcase_all_name} (sorted)",
                )
            )
        return
    json_io.write_json_atomic(config_path, config)


def _register_preset_in_showcase_all(*, presets: dict[str, Any], showcase_all_name: str, preset_name: str) -> bool:
    showcase_all = presets.get(showcase_all_name)
    if not isinstance(showcase_all, dict):
        raise ValueError(f"config.json missing preset '{showcase_all_name}' required for --register.")
    steps = showcase_all.get("steps")
    if steps is None:
        steps = []
        showcase_all["steps"] = steps
    if not isinstance(steps, list):
        raise ValueError(f"config.json preset '{showcase_all_name}' steps must be a list.")

    names: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError(f"config.json preset '{showcase_all_name}' has invalid step (expected object).")
        if step.get("cmd") != "run-preset":
            raise ValueError(f"config.json preset '{showcase_all_name}' must contain only run-preset steps.")
        args = step.get("args")
        if not isinstance(args, list) or len(args) != 1 or not isinstance(args[0], str) or not args[0].strip():
            raise ValueError(f"config.json preset '{showcase_all_name}' has invalid run-preset args.")
        names.append(args[0].strip())

    if len(names) != len(set(names)):
        raise ValueError(f"config.json preset '{showcase_all_name}' has duplicate run-preset entries.")
    if names != sorted(names):
        raise ValueError(f"config.json preset '{showcase_all_name}' run-preset entries must be sorted.")
    if preset_name in names:
        return False

    insert_at = bisect.bisect_left(names, preset_name)
    names.insert(insert_at, preset_name)
    showcase_all["steps"] = [{"cmd": "run-preset", "args": [name]} for name in names]
    return True


def _upsert_quests(
    spec: ScaffoldSpec,
    *,
    base_dir: Path,
    dry_run: bool,
    planned: list[tuple[str, str]],
) -> None:
    quests_path = base_dir / "assets/data/quests.json"
    if not quests_path.exists():
        raise ValueError("assets/data/quests.json not found in current directory.")
    root = _read_json(quests_path)
    quests = root.get("quests")
    if quests is None:
        quests = []
        root["quests"] = quests
    if not isinstance(quests, list):
        raise ValueError("assets/data/quests.json quests must be a list.")

    seen_ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for q in quests:
        if isinstance(q, dict) and isinstance(q.get("id"), str):
            qid = q["id"]
            if qid in seen_ids:
                raise ValueError(f"assets/data/quests.json already contains duplicate quest id '{qid}'.")
            seen_ids.add(qid)
            by_id[qid] = q

    variant = spec.variant_letter.upper()
    suffix = spec.zone_suffix
    added_ids: list[str] = []

    def _add_or_verify(entry: dict[str, Any]) -> None:
        qid = str(entry.get("id") or "").strip()
        if not qid:
            raise ValueError("Internal error: quest entry missing id.")
        existing = by_id.get(qid)
        if existing is not None:
            if existing == entry:
                return
            raise ValueError(f"Quest '{qid}' already exists with different content.")
        quests.append(entry)
        by_id[qid] = entry
        added_ids.append(qid)

    if spec.kind == "linear":
        quest_id = f"{spec.quest_prefix}_variant_{spec.variant_letter}_beacon"
        complete_flag = f"{spec.quest_prefix}_variant_{spec.variant_letter}_beacon_complete"
        start_zone = f"Variant{variant}StartZone{suffix}"
        goal_zone = f"Variant{variant}GoalZone{suffix}"
        _add_or_verify(
            {
                "id": quest_id,
                "title": f"{spec.location.replace('_', ' ').title()} Beacon",
                "description": "Reach the beacon beyond the boss.",
                "start_toast": "Beacon: Reach the Beacon",
                "complete_toast": "Beacon: Complete",
                "stages": [
                    {
                        "id": "reach_beacon",
                        "title": "Reach the Beacon",
                        "text": "Push past the boss and reach the beacon near the exit.",
                        "start_on_event": {"type": "entered_zone", "payload": {"zone": start_zone}},
                        "complete_on": {"type": "entered_zone", "payload": {"zone": goal_zone}},
                    }
                ],
                "reward": {"set_flags": {complete_flag: True}, "inc_counters": {"gold": int(spec.gold)}},
            }
        )

    if spec.kind == "branching_choice":
        intro_id = f"{spec.quest_prefix}_variant_{spec.variant_letter}_intro"
        intro_flag = f"{spec.quest_prefix}_variant_{spec.variant_letter}_intro_complete"
        choice_a_id = f"{spec.quest_prefix}_variant_{spec.variant_letter}_choice_a"
        choice_b_id = f"{spec.quest_prefix}_variant_{spec.variant_letter}_choice_b"
        choice_a_flag = f"{spec.quest_prefix}_variant_{spec.variant_letter}_choice_a_complete"
        choice_b_flag = f"{spec.quest_prefix}_variant_{spec.variant_letter}_choice_b_complete"

        start_zone = f"Variant{variant}StartZone{suffix}"
        choice_a_start = f"Variant{variant}ChoiceAZone{suffix}"
        choice_b_start = f"Variant{variant}ChoiceBZone{suffix}"
        goal_a = f"Variant{variant}GoalAZone{suffix}"
        goal_b = f"Variant{variant}GoalBZone{suffix}"

        _add_or_verify(
            {
                "id": intro_id,
                "title": f"{spec.location.replace('_', ' ').title()} Fork",
                "description": "Reach the fork and choose a signal path.",
                "start_toast": "Intro: Reach the Fork",
                "complete_toast": "Intro: Complete",
                "stages": [
                    {
                        "id": "reach_fork",
                        "title": "Reach the Fork",
                        "text": "Enter the fork zone to unlock Path A or Path B.",
                        "start_on_event": {"type": "entered_zone", "payload": {"zone": start_zone}},
                        "complete_on": {"type": "entered_zone", "payload": {"zone": start_zone}},
                    }
                ],
                "reward": {"set_flags": {intro_flag: True}, "inc_counters": {}},
            }
        )

        for quest_id, start_zone_id, goal_zone_id, flag, blocked in (
            (choice_a_id, choice_a_start, goal_a, choice_a_flag, choice_b_flag),
            (choice_b_id, choice_b_start, goal_b, choice_b_flag, choice_a_flag),
        ):
            label = "A" if quest_id.endswith("_a") else "B"
            _add_or_verify(
                {
                    "id": quest_id,
                    "title": f"{spec.location.replace('_', ' ').title()} Path {label}",
                    "description": f"Commit to Path {label} and secure the cache.",
                    "requires_flags": [intro_flag],
                    "blocks_flags": [blocked],
                    "start_toast": f"Choice: Path {label} - Secure the Cache",
                    "complete_toast": f"Choice: Path {label} - Complete",
                    "stages": [
                        {
                            "id": f"secure_cache_{label.lower()}",
                            "title": "Secure the Cache",
                            "text": f"Take Path {label} and secure the cache near the exit.",
                            "start_on_event": {"type": "entered_zone", "payload": {"zone": start_zone_id}},
                            "complete_on": {"type": "entered_zone", "payload": {"zone": goal_zone_id}},
                        }
                    ],
                    "reward": {"set_flags": {flag: True}, "inc_counters": {"gold": int(spec.gold)}},
                }
            )

    if spec.kind == "puzzle_lite":
        unlock_event = f"{spec.quest_prefix}_variant_{spec.variant_letter}_unlock"
        unlocked_flag = f"{spec.quest_prefix}_variant_{spec.variant_letter}_unlocked"
        puzzle_id = f"{spec.quest_prefix}_variant_{spec.variant_letter}_switch"
        goal_id = f"{spec.quest_prefix}_variant_{spec.variant_letter}_route"
        goal_flag = f"{spec.quest_prefix}_variant_{spec.variant_letter}_route_complete"

        start_zone = f"Variant{variant}StartZone{suffix}"
        goal_zone = f"Variant{variant}GoalZone{suffix}"

        _add_or_verify(
            {
                "id": puzzle_id,
                "title": f"{spec.location.replace('_', ' ').title()} Gate",
                "description": "Flip the switch to unlock the route.",
                "start_toast": "Switch: Flip the Switch",
                "complete_toast": "Switch: Gate Unlocked",
                "stages": [
                    {
                        "id": "flip_switch",
                        "title": "Flip the Switch",
                        "text": "Find the switch and activate it to unlock the door.",
                        "start_on_event": {"type": "entered_zone", "payload": {"zone": start_zone}},
                        "complete_on": {"type": unlock_event},
                    }
                ],
                "reward": {"set_flags": {unlocked_flag: True}, "inc_counters": {}},
            }
        )

        _add_or_verify(
            {
                "id": goal_id,
                "title": f"{spec.location.replace('_', ' ').title()} Route",
                "description": "Reach the exit after unlocking the door.",
                "requires_flags": [unlocked_flag],
                "start_toast": "Switch: Reach the Exit",
                "complete_toast": "Switch: Complete",
                "stages": [
                    {
                        "id": "reach_exit",
                        "title": "Reach the Exit",
                        "text": "Push past the boss and reach the exit.",
                        "start_on_event": {"type": unlock_event},
                        "complete_on": {"type": "entered_zone", "payload": {"zone": goal_zone}},
                    }
                ],
                "reward": {"set_flags": {goal_flag: True}, "inc_counters": {"gold": int(spec.gold)}},
            }
        )

    root["quests"] = sorted(
        quests,
        key=lambda q: (0, q.get("id", "")) if isinstance(q, dict) and isinstance(q.get("id"), str) else (1, ""),
    )
    new_text = json_io.dumps_stable(root) + "\n"
    old_text = quests_path.read_text(encoding="utf-8")
    if new_text == old_text:
        return
    if dry_run:
        if added_ids:
            planned.append((quests_path.as_posix(), f"would add quests {sorted(added_ids)} (sorted)"))
        else:
            planned.append((quests_path.as_posix(), "would sort quests by id"))
        return
    json_io.write_json_atomic(quests_path, root)


def _upsert_events(
    spec: ScaffoldSpec,
    *,
    base_dir: Path,
    dry_run: bool,
    planned: list[tuple[str, str]],
) -> None:
    if spec.kind != "puzzle_lite":
        return
    events_path = base_dir / "assets/data/events.json"
    if not events_path.exists():
        raise ValueError("assets/data/events.json not found in current directory.")
    root = _read_json(events_path)
    events = root.get("events")
    if events is None:
        events = []
        root["events"] = events
    if not isinstance(events, list):
        raise ValueError("assets/data/events.json events must be a list.")

    name = f"{spec.quest_prefix}_variant_{spec.variant_letter}_unlock"
    expected = {
        "name": name,
        "description": f"Fired when the Golden Slice puzzle switch for variant {spec.variant_letter.upper()}{spec.zone_suffix} is activated.",
        "payload": {"source": "object"},
    }

    seen_names: set[str] = set()
    for entry in events:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            ename = entry["name"]
            if ename in seen_names:
                raise ValueError(f"assets/data/events.json already contains duplicate event name '{ename}'.")
            seen_names.add(ename)
            if ename == name:
                if entry == expected:
                    return
                raise ValueError(f"Event '{name}' already exists with different content.")

    events.append(expected)
    root["events"] = sorted(
        events,
        key=lambda e: (0, e.get("name", "")) if isinstance(e, dict) and isinstance(e.get("name"), str) else (1, ""),
    )
    new_text = json_io.dumps_stable(root) + "\n"
    old_text = events_path.read_text(encoding="utf-8")
    if new_text == old_text:
        return
    if dry_run:
        planned.append((events_path.as_posix(), f"would add event '{name}' (sorted)"))
        return
    json_io.write_json_atomic(events_path, root)


def _variant_sort_key(variant: str) -> tuple[int, str]:
    text = str(variant or "").strip().lower()
    if not text:
        return (999, "")
    base = text[0]
    suffix = text[1:]
    try:
        num = int(suffix) if suffix else 0
    except ValueError:
        num = 0
    return (num, base)


def _render_case_block(spec: ScaffoldSpec) -> str:
    v = spec.variant_letter
    V = v.upper()
    suffix = spec.zone_suffix

    if spec.kind == "linear":
        return (
            "    GoldenSliceVariantCase(\n"
            f"        variant=\"{spec.case_variant}\",\n"
            "        kind=\"linear\",\n"
            f"        preset=\"{spec.preset_name}\",\n"
            f"        world=\"{spec.world_path}\",\n"
            f"        scene=\"{spec.scene_path}\",\n"
            f"        quest_id=\"{spec.quest_prefix}_variant_{v}_beacon\",\n"
            "        stage_id=\"reach_beacon\",\n"
            f"        start_zone=\"Variant{V}StartZone{suffix}\",\n"
            f"        goal_zone=\"Variant{V}GoalZone{suffix}\",\n"
            "        start_toast=\"Beacon: Reach the Beacon\",\n"
            "        complete_toast=\"Beacon: Complete\",\n"
            f"        gold={float(spec.gold):.1f},\n"
            f"        complete_flag=\"{spec.quest_prefix}_variant_{v}_beacon_complete\",\n"
            f"        on_trigger_start=\"variant_{v}{suffix}_start\",\n"
            f"        on_trigger_goal=\"variant_{v}{suffix}_goal\",\n"
            "    ),\n"
        )

    if spec.kind == "branching_choice":
        return (
            "    GoldenSliceVariantCase(\n"
            f"        variant=\"{spec.case_variant}\",\n"
            "        kind=\"branching_choice\",\n"
            f"        preset=\"{spec.preset_name}\",\n"
            f"        world=\"{spec.world_path}\",\n"
            f"        scene=\"{spec.scene_path}\",\n"
            "        quest_id=None,\n"
            "        stage_id=None,\n"
            f"        start_zone=\"Variant{V}StartZone{suffix}\",\n"
            "        goal_zone=None,\n"
            "        start_toast=None,\n"
            "        complete_toast=None,\n"
            "        gold=None,\n"
            "        complete_flag=None,\n"
            "        on_trigger_start=None,\n"
            "        on_trigger_goal=None,\n"
            f"        intro_quest_id=\"{spec.quest_prefix}_variant_{v}_intro\",\n"
            f"        intro_flag=\"{spec.quest_prefix}_variant_{v}_intro_complete\",\n"
            f"        choice_a_quest_id=\"{spec.quest_prefix}_variant_{v}_choice_a\",\n"
            f"        choice_b_quest_id=\"{spec.quest_prefix}_variant_{v}_choice_b\",\n"
            f"        choice_a_start_zone=\"Variant{V}ChoiceAZone{suffix}\",\n"
            f"        choice_b_start_zone=\"Variant{V}ChoiceBZone{suffix}\",\n"
            f"        choice_a_goal_zone=\"Variant{V}GoalAZone{suffix}\",\n"
            f"        choice_b_goal_zone=\"Variant{V}GoalBZone{suffix}\",\n"
            f"        choice_a_complete_flag=\"{spec.quest_prefix}_variant_{v}_choice_a_complete\",\n"
            f"        choice_b_complete_flag=\"{spec.quest_prefix}_variant_{v}_choice_b_complete\",\n"
            f"        choice_gold={float(spec.gold):.1f},\n"
            "        choice_a_start_toast=\"Choice: Path A - Secure the Cache\",\n"
            "        choice_b_start_toast=\"Choice: Path B - Secure the Cache\",\n"
            "        choice_a_complete_toast=\"Choice: Path A - Complete\",\n"
            "        choice_b_complete_toast=\"Choice: Path B - Complete\",\n"
            "    ),\n"
        )

    assert spec.kind == "puzzle_lite"
    return (
        "    GoldenSliceVariantCase(\n"
        f"        variant=\"{spec.case_variant}\",\n"
        "        kind=\"puzzle_lite\",\n"
        f"        preset=\"{spec.preset_name}\",\n"
        f"        world=\"{spec.world_path}\",\n"
        f"        scene=\"{spec.scene_path}\",\n"
        "        quest_id=None,\n"
        "        stage_id=None,\n"
        f"        start_zone=\"Variant{V}StartZone{suffix}\",\n"
        f"        goal_zone=\"Variant{V}GoalZone{suffix}\",\n"
        "        start_toast=None,\n"
        "        complete_toast=None,\n"
        "        gold=None,\n"
        "        complete_flag=None,\n"
        f"        on_trigger_start=\"variant_{v}{suffix}_start\",\n"
        f"        on_trigger_goal=\"variant_{v}{suffix}_goal\",\n"
        f"        puzzle_unlock_event=\"{spec.quest_prefix}_variant_{v}_unlock\",\n"
        f"        puzzle_unlocked_flag=\"{spec.quest_prefix}_variant_{v}_unlocked\",\n"
        f"        puzzle_quest_id=\"{spec.quest_prefix}_variant_{v}_switch\",\n"
        "        puzzle_start_toast=\"Switch: Flip the Switch\",\n"
        "        puzzle_complete_toast=\"Switch: Gate Unlocked\",\n"
        f"        goal_quest_id=\"{spec.quest_prefix}_variant_{v}_route\",\n"
        f"        goal_complete_flag=\"{spec.quest_prefix}_variant_{v}_route_complete\",\n"
        "        goal_start_toast=\"Switch: Reach the Exit\",\n"
        "        goal_complete_toast=\"Switch: Complete\",\n"
        f"        goal_gold={float(spec.gold):.1f},\n"
        "    ),\n"
    )


def _upsert_variant_contract_case(
    spec: ScaffoldSpec,
    *,
    base_dir: Path,
    dry_run: bool,
    planned: list[tuple[str, str]],
) -> None:
    path = base_dir / "tests/_variant_contracts.py"
    if not path.exists():
        raise ValueError("tests/_variant_contracts.py not found in current directory.")
    text = path.read_text(encoding="utf-8")

    if f"variant=\"{spec.case_variant}\"" in text:
        return

    marker = "GOLDEN_SLICE_VARIANT_CASES"
    start_idx = text.find(marker)
    if start_idx < 0:
        raise ValueError("Unable to locate GOLDEN_SLICE_VARIANT_CASES in tests/_variant_contracts.py.")
    open_idx = text.find("(", start_idx)
    if open_idx < 0:
        raise ValueError("Unable to locate opening '(' for GOLDEN_SLICE_VARIANT_CASES.")
    close_idx = text.find("\n)\n", open_idx)
    if close_idx < 0:
        raise ValueError("Unable to locate closing ')' for GOLDEN_SLICE_VARIANT_CASES.")

    body = text[open_idx + 1 : close_idx + 1]
    blocks = _extract_case_blocks(body)
    variants = [variant for variant, _ in blocks]

    new_key = _variant_sort_key(spec.case_variant)
    insert_at = len(blocks)
    for i, existing in enumerate(variants):
        if _variant_sort_key(existing) > new_key:
            insert_at = i
            break

    new_block = _render_case_block(spec)
    new_blocks = list(blocks)
    new_blocks.insert(insert_at, (spec.case_variant, new_block))
    new_body = "".join(block_text for _variant, block_text in new_blocks)

    updated = text[: open_idx + 1] + new_body + text[close_idx + 1 :]
    if updated == text:
        return
    if dry_run:
        planned.append((path.as_posix(), f"would insert case variant '{spec.case_variant}'"))
        return
    path.write_text(updated, encoding="utf-8")


def _extract_case_blocks(body: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    idx = 0
    needle = "GoldenSliceVariantCase("
    while True:
        start = body.find(needle, idx)
        if start < 0:
            break
        start = body.rfind("\n", 0, start) + 1
        end = _scan_balanced_call_end(body, start)
        block = body[start:end]
        m = re.search(r'variant=\"([^\"]+)\"', block)
        if not m:
            raise ValueError("Failed to parse variant=... in a GoldenSliceVariantCase block.")
        blocks.append((m.group(1), block))
        idx = end
    if not blocks:
        raise ValueError("No GoldenSliceVariantCase blocks found in GOLDEN_SLICE_VARIANT_CASES.")
    return blocks


def _scan_balanced_call_end(text: str, start: int) -> int:
    i = start
    parens = 0
    in_str: str | None = None
    escaped = False
    seen_open = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in {"'", '"'}:
                in_str = ch
            elif ch == "(":
                parens += 1
                seen_open = True
            elif ch == ")":
                parens -= 1
                if seen_open and parens == 0:
                    i += 1
                    while i < len(text) and text[i] in {" ", "\t"}:
                        i += 1
                    if i < len(text) and text[i] == ",":
                        i += 1
                    if i < len(text) and text[i] == "\n":
                        i += 1
                    return i
        i += 1
    raise ValueError("Failed to find end of GoldenSliceVariantCase(...) block.")
