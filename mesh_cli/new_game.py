"""
CLI command: ``mesh_cli new-game``

Creates a deterministic initial save payload for a fresh campaign start.

The payload is built from scratch (no GUI/window required), validated
through the existing save schema pipeline, and written atomically.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engine.game_state_controller import GameState
from engine.persistence_io import (
    SAVE_FORMAT_VERSION,
    dumps_json_deterministic,
    write_json_atomic,
)
from engine.rng_service import RNGService
from engine.save_runtime.constants import SLOT_META_VERSION, SNAPSHOT_VERSION
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION, validate_save

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CAMPAIGN = "mini_campaign_01"
DEFAULT_SEED = 42

# Maps campaign id → starting scene path.
_CAMPAIGN_START_SCENES: dict[str, str] = {
    "mini_campaign_01": "scenes/town_schedule_01.json",
}


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_new_game_payload(
    *,
    campaign: str = DEFAULT_CAMPAIGN,
    scene: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Build a deterministic, validated new-game save payload.

    The payload mirrors the structure produced by
    ``engine.save_runtime.payloads.build_slot_payload`` so it can be loaded
    by the normal save-manager path.

    Parameters
    ----------
    campaign:
        Campaign identifier.  Used to look up the starting scene and to
        set the ``campaign.started`` flag.
    scene:
        Override starting scene path.  When *None*, the campaign's default
        starting scene is used.
    seed:
        RNG seed stored in the payload.  Defaults to ``DEFAULT_SEED`` (42)
        for deterministic reproducibility.
    """
    resolved_scene = scene or _CAMPAIGN_START_SCENES.get(campaign)
    if resolved_scene is None:
        raise ValueError(
            f"Unknown campaign '{campaign}' and no --scene override provided"
        )

    resolved_seed = seed if seed is not None else DEFAULT_SEED

    # --- Game state (mirrors GameState defaults) ---
    game_state = GameState(
        flags={"campaign.started": True},
    )
    game_state_dict = game_state.snapshot()
    game_state_dict["quests"] = {}          # no active quests yet

    # --- RNG state (deterministic from seed) ---
    rng = RNGService()
    rng.seed(resolved_seed)
    rng_state = rng.get_state()

    # --- Assemble full payload ---
    payload: dict[str, Any] = {
        # Format / schema versions
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": SAVE_SCHEMA_VERSION,
        "version": SNAPSHOT_VERSION,

        # Scene identification
        "scene_id": resolved_scene,
        "scene_path": resolved_scene,
        "world_file": None,
        "world_id": None,
        "spawn_zone_id": None,

        # Top-level snapshot fields
        "gold": 0,
        "flags": sorted(
            k for k, v in game_state.flags.items() if v
        ),

        # Nested game state
        "game_state": game_state_dict,

        # v2 blocks (empty for new game)
        "saved_entities": {"schema_version": 1, "entities": []},
        "saved_quests": {"schema_version": 1, "quests": {}},

        # Meta
        "meta": {
            "slot": "new_game",
            "scene_path": resolved_scene,
            "timestamp": "1970-01-01T00:00:00",
            "version": SLOT_META_VERSION,
        },

        # Campaign & RNG provenance
        "campaign": campaign,
        "rng_seed": resolved_seed,
        "rng_state": rng_state,
    }

    # Validate through the standard pipeline
    validate_save(payload)
    return payload


# ---------------------------------------------------------------------------
# CLI entry-points
# ---------------------------------------------------------------------------

def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``new-game`` command."""
    parser = subparsers.add_parser(
        "new-game",
        help="Create a deterministic new-game save payload.",
        description=(
            "Generates a fresh save file for a campaign start.  "
            "The output is deterministic: same arguments always produce "
            "byte-identical JSON."
        ),
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to write the save JSON file.",
    )
    parser.add_argument(
        "--campaign",
        default=DEFAULT_CAMPAIGN,
        help=f"Campaign identifier (default: {DEFAULT_CAMPAIGN}).",
    )
    parser.add_argument(
        "--scene",
        default=None,
        help="Override starting scene path.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=f"RNG seed (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an existing file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="print_json",
        help="Print the payload to stdout as well.",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the ``new-game`` command."""
    out_path = Path(args.out)
    campaign: str = args.campaign
    scene_override: str | None = args.scene
    seed: int | None = args.seed
    force: bool = args.force
    print_json: bool = args.print_json

    # Guard: refuse to overwrite without --force
    if out_path.exists() and not force:
        print(
            f"[Mesh][NewGame] Error: '{out_path}' already exists.  "
            f"Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    # Build payload
    try:
        payload = build_new_game_payload(
            campaign=campaign,
            scene=scene_override,
            seed=seed,
        )
    except (ValueError, Exception) as exc:
        print(f"[Mesh][NewGame] Error: {exc}", file=sys.stderr)
        return 1

    # Write atomically
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_path, payload)
    print(f"[Mesh][NewGame] Saved to {out_path}")

    # Optionally echo to stdout
    if print_json:
        sys.stdout.write(dumps_json_deterministic(payload))

    return 0
