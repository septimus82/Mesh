#!/usr/bin/env python3
"""Import RMMZ map passability into a Mesh scene tilemap (collision layer)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.persistence_io import write_json_atomic
from engine.tooling.rmmz_passability import (
    apply_tilemap_to_scene,
    mesh_tilemap_from_rmmz_map,
    summarize_rmmz_passability,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import RPG Maker MZ map ground/collision into a Mesh scene tilemap.",
    )
    parser.add_argument(
        "--map",
        required=True,
        help="Path to RMMZ MapNNN.json (e.g. data/Map002.json)",
    )
    parser.add_argument(
        "--tilesets",
        help="Path to Tilesets.json (default: Tilesets.json next to the map file)",
    )
    parser.add_argument(
        "--scene",
        help="Mesh scene JSON to update in place",
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=48,
        help="Mesh tile size in pixels (default: 48 to match RMMZ grid)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print passability summary without writing files",
    )
    args = parser.parse_args(argv)

    map_path = Path(args.map)
    summary = summarize_rmmz_passability(
        map_path,
        tilesets_path=args.tilesets,
        tile_size=int(args.tile_size),
    )
    print(
        "[Mesh][RMMZ] {map}: {width}x{height} @ {tile_size}px "
        "({pixel_w}x{pixel_h} px) — blocked={blocked}, open={open}".format(
            map=summary["map"],
            width=summary["width"],
            height=summary["height"],
            tile_size=summary["tile_size_px"],
            pixel_w=summary["pixel_coverage"][0],
            pixel_h=summary["pixel_coverage"][1],
            blocked=summary["blocked_cells"],
            open=summary["open_cells"],
        )
    )
    print(
        f"[Mesh][RMMZ] tileset #{summary['tileset_id']} ({summary['tileset_name']})"
    )

    if args.summary_only:
        return 0

    if not args.scene:
        print("[Mesh][RMMZ] Error: pass --scene to write imported collision tiles")
        return 2

    scene_path = Path(args.scene)
    scene_payload = json.loads(scene_path.read_text(encoding="utf-8"))
    if not isinstance(scene_payload, dict):
        print(f"[Mesh][RMMZ] Error: scene must be a JSON object: {scene_path}")
        return 1

    tilemap = mesh_tilemap_from_rmmz_map(
        map_path,
        tilesets_path=args.tilesets,
        tile_size=int(args.tile_size),
    )
    updated = apply_tilemap_to_scene(scene_payload, tilemap)
    write_json_atomic(scene_path, updated)
    blocked = sum(1 for value in tilemap["tile_layers"][0]["tiles"] if value)
    print(
        f"[Mesh][RMMZ] Wrote {blocked} blocked cells to {scene_path} "
        f"({tilemap['width']}x{tilemap['height']} @ {tilemap['tilewidth']}px)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
