from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.paths import get_content_roots, resolve_path
from engine.tilemap_brush import validate_brush as validate_brush_or_raise


@dataclass(frozen=True)
class BrushSummary:
    pack_id: str
    id: str
    w: int
    h: int
    mask_tile: int
    path: str


@dataclass(frozen=True)
class BrushIssue:
    path: str
    code: str
    detail: str


def iter_brush_paths(*, pack_id: str | None = None) -> list[str]:
    """Return repo-relative brush JSON paths under packs/*/brushes/*.json."""
    roots = list(get_content_roots())
    found: set[str] = set()
    for root in roots:
        packs_dir = Path(root) / "packs"
        if not packs_dir.exists():
            continue
        for pack_dir in sorted([p for p in packs_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
            if pack_id and pack_dir.name != pack_id:
                continue
            brushes_dir = pack_dir / "brushes"
            if not brushes_dir.exists():
                continue
            for path in sorted([p for p in brushes_dir.glob("*.json") if p.is_file()], key=lambda p: p.name):
                try:
                    rel = path.resolve().relative_to(Path(root).resolve()).as_posix()
                except Exception:
                    rel = path.as_posix()
                found.add(rel)
    return sorted(found)


def load_brush(path: str) -> dict[str, Any]:
    """Load and normalize a brush JSON (raises on invalid)."""
    resolved = resolve_path(path)
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return validate_brush_or_raise(raw)


def validate_brush(brush_payload: Any) -> list[str]:
    """Return deterministic validation errors (empty means ok)."""
    errors: list[str] = []
    if not isinstance(brush_payload, dict):
        return ["brush.root_type"]

    brush_id = brush_payload.get("id")
    if not isinstance(brush_id, str) or not brush_id.strip():
        errors.append("brush.id.required")

    w = brush_payload.get("w")
    h = brush_payload.get("h")
    if not isinstance(w, int) or w <= 0:
        errors.append("brush.w.positive_int")
    if not isinstance(h, int) or h <= 0:
        errors.append("brush.h.positive_int")

    mask_tile = brush_payload.get("mask_tile", -1)
    if not isinstance(mask_tile, int):
        errors.append("brush.mask_tile.int")

    tiles = brush_payload.get("tiles")
    if not isinstance(tiles, list):
        errors.append("brush.tiles.array")
        return sorted(set(errors))

    if isinstance(h, int) and h > 0 and len(tiles) != h:
        errors.append("brush.tiles.rows_length")

    if isinstance(w, int) and w > 0:
        for row_idx, row in enumerate(tiles):
            if not isinstance(row, list):
                errors.append(f"brush.tiles[{row_idx}].array")
                continue
            if len(row) != w:
                errors.append(f"brush.tiles[{row_idx}].cols_length")
            for col_idx, value in enumerate(row):
                if not isinstance(value, int):
                    errors.append(f"brush.tiles[{row_idx}][{col_idx}].int")

    return sorted(set(errors))


def pick_brush_layer_id(brush_payload: Any, requested_layer_id: str | None) -> str:
    """Brushes are single-layer; this is a label used by preview output."""
    if isinstance(requested_layer_id, str) and requested_layer_id.strip():
        return requested_layer_id.strip()
    return "tiles"


def render_brush_layer_ascii(
    brush_payload: Any,
    *,
    layer_id: str,
    tile_filter: int | None,
) -> list[str]:
    """Render a brush as ASCII (mask/default '.') using deterministic row-major ordering."""
    _ = layer_id  # label only; brushes are single-layer today
    normalized = validate_brush_or_raise(brush_payload)
    w = int(normalized["w"])
    h = int(normalized["h"])
    mask_tile = int(normalized["mask_tile"])
    tiles: list[list[int]] = normalized["tiles"]

    lines: list[str] = []
    for y in range(h):
        row = tiles[y]
        chars: list[str] = []
        for x in range(w):
            value = int(row[x])
            if tile_filter is not None:
                chars.append("#" if value == int(tile_filter) else ".")
            else:
                chars.append("." if value == mask_tile else "#")
        lines.append("".join(chars))
    return lines


def summarize_brush(*, brush: dict[str, Any], rel_path: str) -> BrushSummary:
    parts = str(rel_path).replace("\\", "/").split("/")
    pack_id = parts[1] if len(parts) >= 3 and parts[0] == "packs" else ""
    return BrushSummary(
        pack_id=pack_id,
        id=str(brush.get("id") or ""),
        w=int(brush.get("w") or 0),
        h=int(brush.get("h") or 0),
        mask_tile=int(brush.get("mask_tile") or 0),
        path=str(rel_path).replace("\\", "/"),
    )

