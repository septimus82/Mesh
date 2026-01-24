"""Authoring commands for Gameplay & Entities."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.tooling import scaffold, project_index
from engine.tooling.plan_types import Action, Plan
from engine.tooling.plan_executor import PlanExecutor
from mesh_cli import scene as scene_commands

def handle(args: argparse.Namespace) -> int:
    if args.command == "new-npc":
        return _handle_new_npc(args)
    if args.command == "place-npc":
        return _handle_place_npc(args)
    if args.command == "new-quest":
        return _handle_new_quest(args)
    if args.command == "new-behaviour":
        return _handle_new_behaviour(args)
    if args.command == "add-puzzle":
        return _handle_add_puzzle(args)
    return 1

def register(subparsers: argparse._SubParsersAction) -> None:
    # New NPC
    new_npc_parser = subparsers.add_parser("new-npc", help="Create a new NPC")
    new_npc_parser.add_argument("role", help="NPC role/name")
    new_npc_parser.add_argument("--into", required=True, help="Scene path")
    new_npc_parser.add_argument("--x", type=float, default=0.0, help="X coordinate")
    new_npc_parser.add_argument("--y", type=float, default=0.0, help="Y coordinate")

    # Place NPC
    place_npc_parser = subparsers.add_parser("place-npc", help="Place an NPC into a scene")
    place_npc_parser.add_argument("role", help="NPC role/name")
    place_npc_parser.add_argument("--into", required=True, help="Scene path")
    place_npc_parser.add_argument("--x", type=float, default=0.0, help="X coordinate")
    place_npc_parser.add_argument("--y", type=float, default=0.0, help="Y coordinate")

    # New Quest
    new_quest_parser = subparsers.add_parser("new-quest", help="Create a new quest")
    new_quest_parser.add_argument("name", help="Quest name")
    new_quest_parser.add_argument("--target", help="Target entity/location")

    # New Behaviour
    new_behaviour_parser = subparsers.add_parser("new-behaviour", help="Create a new behaviour script")
    new_behaviour_parser.add_argument("name", help="Behaviour name")

    # Add Puzzle
    add_puzzle_parser = subparsers.add_parser("add-puzzle", help="Add a puzzle to a scene")
    add_puzzle_parser.add_argument("--scene-path", required=True, help="Scene path")
    add_puzzle_parser.add_argument("--prefix", required=True, help="ID prefix")
    add_puzzle_parser.add_argument("--switch-x", type=float, required=True, help="Switch X")
    add_puzzle_parser.add_argument("--switch-y", type=float, required=True, help="Switch Y")
    add_puzzle_parser.add_argument("--door-x", type=float, required=True, help="Door X")
    add_puzzle_parser.add_argument("--door-y", type=float, required=True, help="Door Y")
    add_puzzle_parser.add_argument("--reward-x", type=float, required=True, help="Reward X")
    add_puzzle_parser.add_argument("--reward-y", type=float, required=True, help="Reward Y")
    add_puzzle_parser.add_argument("--item", required=True, help="Reward item ID")
    add_puzzle_parser.add_argument("--gold", type=int, default=0, help="Reward gold amount")

def _handle_new_npc(args: argparse.Namespace) -> int:
    """Create a new NPC."""
    return 0 if scaffold.create_npc(args.role, args.into, args.x, args.y) else 1

def _handle_place_npc(args: argparse.Namespace) -> int:
    """Place an NPC into a scene using a plan."""
    actions = [
        Action(
            type="add_npc",
            args={
                "scene_path": args.into,
                "role": args.role,
                "x": args.x,
                "y": args.y,
                "name": f"{args.role.capitalize()}"
            },
            description=f"Add {args.role} NPC to {args.into}"
        )
    ]

    plan = Plan(
        wizard="place-npc",
        version=1,
        inputs={"scene": args.into, "role": args.role},
        actions=actions
    )

    executor = PlanExecutor()
    try:
        executor.execute(plan)
        print(f"Successfully placed NPC {args.role} in {args.into}")
        return 0
    except Exception as e:
        print(f"Error placing NPC: {e}")
        return 1

def _handle_new_quest(args: argparse.Namespace) -> int:
    """Create a new quest entry."""
    try:
        scaffold.create_quest(args.name, args.target)
        return 0
    except Exception as e:
        print(f"[Mesh][CLI] Error creating quest: {e}")
        return 1

def _handle_new_behaviour(args: argparse.Namespace) -> int:
    """Create a new behaviour script."""
    try:
        scaffold.create_behaviour(args.name)
        print(f"[Mesh][CLI] Created behaviour '{args.name}'")
        # Re-index to include the new file
        project_index.main([])
        return 0
    except Exception as e:
        print(f"[Mesh][CLI] Error creating behaviour: {e}")
        return 1

def _handle_add_puzzle(args: argparse.Namespace) -> int:
    """Add a puzzle to a scene using a plan."""
    actions = [
        Action(
            type="add_puzzle_switch_door",
            args={
                "scene_path": args.scene_path,
                "id_prefix": args.prefix,
                "switch": {"x": args.switch_x, "y": args.switch_y},
                "door": {"x": args.door_x, "y": args.door_y},
                "reward": {
                    "x": args.reward_x,
                    "y": args.reward_y,
                    "item_id": args.item,
                    "gold": args.gold
                }
            },
            description=f"Add puzzle to {args.scene_path}"
        )
    ]

    plan = Plan(
        wizard="add-puzzle",
        version=1,
        inputs={"scene": args.scene_path},
        actions=actions
    )

    executor = PlanExecutor()
    try:
        executor.execute(plan)
        print(f"Successfully added puzzle to {args.scene_path}")
        return 0
    except Exception as e:
        print(f"Error adding puzzle: {e}")
        return 1

def _sanitize_entity_id_token(token: str) -> str:
    """Sanitize a string for use in an entity ID."""
    return "".join(c for c in token if c.isalnum() or c == "_")

