from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import get_content_roots


@dataclass(frozen=True, slots=True)
class StampSummary:
    pack_id: str
    id: str
    w: int
    h: int
    layer_ids: list[str]
    entity_count: int
    path: str


@dataclass(frozen=True, slots=True)
class StampIssue:
    path: str
    code: str
    detail: str


def _norm_rel_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _extract_pack_id(rel_path: str) -> str:
    parts = [p for p in str(rel_path).split("/") if p]
    if len(parts) >= 3 and parts[0] == "packs" and parts[2] == "stamps":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "packs":
        return parts[1]
    return "unknown"


def iter_stamp_paths(*, pack_id: str | None = None) -> list[str]:
    """Return relative stamp paths under packs/*/stamps/*.json (forward slashes)."""
    wanted_pack = str(pack_id).strip() if isinstance(pack_id, str) and str(pack_id).strip() else None
    results: set[str] = set()
    for root in get_content_roots():
        root_path = Path(root)
        packs_dir = root_path / "packs"
        if not packs_dir.exists():
            continue
        for stamp_path in packs_dir.glob("*/*"):
            # cheap guard: only traverse packs/<id>/stamps
            if not stamp_path.is_dir() or stamp_path.name != "stamps":
                continue
            pack = stamp_path.parent.name
            if wanted_pack is not None and pack != wanted_pack:
                continue
            for candidate in stamp_path.glob("*.json"):
                try:
                    rel = candidate.relative_to(root_path)
                except Exception:
                    rel = candidate
                results.add(_norm_rel_path(rel))
    return sorted(results)


def load_stamp(path: str) -> dict[str, Any]:
    p = Path(str(path))
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("stamp JSON root must be an object")
    return payload


def _stamp_dims(stamp: dict[str, Any]) -> tuple[int | None, int | None]:
    w = stamp.get("w", stamp.get("width"))
    h = stamp.get("h", stamp.get("height"))
    if not isinstance(w, int) or not isinstance(h, int):
        return None, None
    return int(w), int(h)


def summarize_stamp(stamp: dict[str, Any], *, rel_path: str) -> StampSummary:
    stamp_id = str(stamp.get("id") or "").strip()
    w, h = _stamp_dims(stamp)
    if w is None or h is None:
        w = 0
        h = 0

    layer_ids: set[str] = set()
    tiles_value = stamp.get("tiles")
    if isinstance(tiles_value, list):
        for entry in tiles_value:
            if isinstance(entry, dict):
                lid = entry.get("layer_id")
                if isinstance(lid, str) and lid.strip():
                    layer_ids.add(lid.strip())

    tile_layers_value = stamp.get("tile_layers")
    if isinstance(tile_layers_value, list):
        for entry in tile_layers_value:
            if isinstance(entry, dict):
                lid = entry.get("layer_id")
                if isinstance(lid, str) and lid.strip():
                    layer_ids.add(lid.strip())

    entities_value = stamp.get("entities")
    entity_count = len(entities_value) if isinstance(entities_value, list) else 0

    rel_path_norm = _norm_rel_path(Path(str(rel_path)))
    return StampSummary(
        pack_id=_extract_pack_id(rel_path_norm),
        id=stamp_id,
        w=int(w),
        h=int(h),
        layer_ids=sorted(layer_ids),
        entity_count=int(entity_count),
        path=rel_path_norm,
    )


def validate_stamp(
    stamp: dict[str, Any],
    *,
    rel_path: str,
    prefab_ids: set[str],
) -> list[StampIssue]:
    issues: list[StampIssue] = []
    rel_path_norm = _norm_rel_path(Path(str(rel_path)))

    stamp_id = stamp.get("id")
    if not isinstance(stamp_id, str) or not stamp_id.strip():
        issues.append(StampIssue(rel_path_norm, "stamp.missing_id", "id must be a non-empty string"))

    w, h = _stamp_dims(stamp)
    if w is None or h is None or w <= 0 or h <= 0:
        issues.append(StampIssue(rel_path_norm, "stamp.invalid_dims", "w/width and h/height must be positive ints"))
        w = None
        h = None

    for key in ("tilewidth", "tileheight"):
        value = stamp.get(key)
        if value is not None and (not isinstance(value, int) or int(value) <= 0):
            issues.append(StampIssue(rel_path_norm, "stamp.invalid_tile_size", f"{key} must be a positive int"))

    # Tile rect entries (current stamp schema) OR tile_layers full grids (optional).
    tiles_value = stamp.get("tiles", [])
    if tiles_value is not None and not isinstance(tiles_value, list):
        issues.append(StampIssue(rel_path_norm, "stamp.tiles.invalid", "tiles must be an array when provided"))
        tiles_value = []

    if isinstance(tiles_value, list):
        for idx, entry in enumerate(tiles_value):
            if not isinstance(entry, dict):
                issues.append(StampIssue(rel_path_norm, "stamp.tiles.entry_type", f"tiles[{idx}] must be an object"))
                continue
            lid = entry.get("layer_id")
            if not isinstance(lid, str) or not lid.strip():
                issues.append(StampIssue(rel_path_norm, "stamp.tiles.missing_layer_id", f"tiles[{idx}].layer_id missing"))
            for f in ("x", "y", "w", "h", "tile"):
                if not isinstance(entry.get(f), int):
                    issues.append(StampIssue(rel_path_norm, "stamp.tiles.invalid_field", f"tiles[{idx}].{f} must be int"))
            x0_raw = entry.get("x")
            y0_raw = entry.get("y")
            rw_raw = entry.get("w")
            rh_raw = entry.get("h")
            if (
                w is not None
                and h is not None
                and isinstance(x0_raw, int)
                and isinstance(y0_raw, int)
                and isinstance(rw_raw, int)
                and isinstance(rh_raw, int)
            ):
                x0 = x0_raw
                y0 = y0_raw
                rw = rw_raw
                rh = rh_raw
                if rw <= 0 or rh <= 0:
                    issues.append(StampIssue(rel_path_norm, "stamp.tiles.invalid_rect", f"tiles[{idx}] w/h must be > 0"))
                elif x0 < 0 or y0 < 0 or x0 + rw > int(w) or y0 + rh > int(h):
                    issues.append(StampIssue(rel_path_norm, "stamp.tiles.out_of_bounds", f"tiles[{idx}] rect out of stamp bounds"))

    tile_layers_value = stamp.get("tile_layers")
    if tile_layers_value is not None:
        if not isinstance(tile_layers_value, list):
            issues.append(StampIssue(rel_path_norm, "stamp.tile_layers.invalid", "tile_layers must be an array when provided"))
        else:
            if w is not None and h is not None:
                expected = int(w) * int(h)
            else:
                expected = None
            for idx, entry in enumerate(tile_layers_value):
                if not isinstance(entry, dict):
                    issues.append(StampIssue(rel_path_norm, "stamp.tile_layers.entry_type", f"tile_layers[{idx}] must be an object"))
                    continue
                lid = entry.get("layer_id")
                if not isinstance(lid, str) or not lid.strip():
                    issues.append(StampIssue(rel_path_norm, "stamp.tile_layers.missing_layer_id", f"tile_layers[{idx}].layer_id missing"))
                tiles = entry.get("tiles")
                if not isinstance(tiles, list) or any(not isinstance(v, int) for v in tiles):
                    issues.append(StampIssue(rel_path_norm, "stamp.tile_layers.invalid_tiles", f"tile_layers[{idx}].tiles must be int array"))
                elif expected is not None and len(tiles) != expected:
                    issues.append(StampIssue(rel_path_norm, "stamp.tile_layers.tiles_length", f"tile_layers[{idx}].tiles expected {expected}, got {len(tiles)}"))

    # Entity prefab + id uniqueness (use id_suffix as required stamp identity).
    entities_value = stamp.get("entities", [])
    if entities_value is not None and not isinstance(entities_value, list):
        issues.append(StampIssue(rel_path_norm, "stamp.entities.invalid", "entities must be an array when provided"))
        entities_value = []

    if isinstance(entities_value, list):
        seen_suffixes: set[str] = set()
        for idx, entry in enumerate(entities_value):
            if not isinstance(entry, dict):
                issues.append(StampIssue(rel_path_norm, "stamp.entities.entry_type", f"entities[{idx}] must be an object"))
                continue
            prefab_id = entry.get("prefab_id")
            if not isinstance(prefab_id, str) or not prefab_id.strip():
                issues.append(StampIssue(rel_path_norm, "stamp.entities.missing_prefab", f"entities[{idx}].prefab_id missing"))
            else:
                pid = prefab_id.strip()
                if pid not in prefab_ids:
                    issues.append(StampIssue(rel_path_norm, "stamp.entities.unknown_prefab", f"entities[{idx}] prefab_id not found: {pid}"))

            suffix = entry.get("id_suffix")
            if not isinstance(suffix, str) or not suffix.strip():
                issues.append(StampIssue(rel_path_norm, "stamp.entities.missing_id_suffix", f"entities[{idx}].id_suffix missing"))
            else:
                sfx = suffix.strip()
                if sfx in seen_suffixes:
                    issues.append(StampIssue(rel_path_norm, "stamp.entities.duplicate_id_suffix", f"duplicate id_suffix: {sfx}"))
                seen_suffixes.add(sfx)

    issues.sort(key=lambda issue: (issue.path, issue.code, issue.detail))
    return issues


def pick_stamp_layer_id(stamp: dict[str, Any], requested_layer_id: str | None) -> str:
    requested = str(requested_layer_id or "").strip() or None

    ordered: list[str] = []
    seen: set[str] = set()

    tile_layers_value = stamp.get("tile_layers")
    if isinstance(tile_layers_value, list):
        for entry in tile_layers_value:
            if not isinstance(entry, dict):
                continue
            lid = entry.get("layer_id")
            if isinstance(lid, str) and lid.strip():
                value = lid.strip()
                if value not in seen:
                    ordered.append(value)
                    seen.add(value)

    tiles_value = stamp.get("tiles")
    if isinstance(tiles_value, list):
        for entry in tiles_value:
            if not isinstance(entry, dict):
                continue
            lid = entry.get("layer_id")
            if isinstance(lid, str) and lid.strip():
                value = lid.strip()
                if value not in seen:
                    ordered.append(value)
                    seen.add(value)

    if requested is not None:
        if requested in seen:
            return requested
        raise KeyError(requested)

    if ordered:
        return ordered[0]
    raise KeyError("<no_layers>")


def render_stamp_layer_ascii(
    stamp: dict[str, Any],
    *,
    layer_id: str,
    tile_filter: int | None,
) -> list[str]:
    w, h = _stamp_dims(stamp)
    if w is None or h is None or w <= 0 or h <= 0:
        raise ValueError("missing_or_invalid_dims")

    lid = str(layer_id or "").strip()
    if not lid:
        raise ValueError("missing_layer_id")

    tiles: list[int] | None = None

    tile_layers_value = stamp.get("tile_layers")
    if isinstance(tile_layers_value, list):
        for entry in tile_layers_value:
            if not isinstance(entry, dict):
                continue
            entry_lid = entry.get("layer_id")
            if isinstance(entry_lid, str) and entry_lid.strip() == lid:
                candidate = entry.get("tiles")
                if not isinstance(candidate, list) or any(not isinstance(v, int) for v in candidate):
                    raise ValueError("invalid_tiles")
                if len(candidate) != int(w) * int(h):
                    raise ValueError("tiles_length_mismatch")
                tiles = [int(v) for v in candidate]
                break

    if tiles is None:
        # Build a grid from rect entries.
        tiles = [0] * (int(w) * int(h))
        tiles_value = stamp.get("tiles", [])
        if tiles_value is None:
            tiles_value = []
        if not isinstance(tiles_value, list):
            raise ValueError("invalid_tiles")

        saw_layer = False
        for entry in tiles_value:
            if not isinstance(entry, dict):
                continue
            entry_lid = entry.get("layer_id")
            if not isinstance(entry_lid, str) or entry_lid.strip() != lid:
                continue
            saw_layer = True
            x0 = entry.get("x")
            y0 = entry.get("y")
            rw = entry.get("w")
            rh = entry.get("h")
            t = entry.get("tile")
            if not (isinstance(x0, int) and isinstance(y0, int) and isinstance(rw, int) and isinstance(rh, int) and isinstance(t, int)):
                raise ValueError("invalid_tiles")
            if int(rw) <= 0 or int(rh) <= 0:
                raise ValueError("invalid_tiles")
            if int(x0) < 0 or int(y0) < 0 or int(x0) + int(rw) > int(w) or int(y0) + int(rh) > int(h):
                raise ValueError("tiles_out_of_bounds")
            for yy in range(int(y0), int(y0) + int(rh)):
                row_start = int(yy) * int(w)
                for xx in range(int(x0), int(x0) + int(rw)):
                    tiles[row_start + int(xx)] = int(t)

        if not saw_layer:
            raise KeyError(lid)

    if tile_filter is not None:
        target = int(tile_filter)
    else:
        target = None

    lines: list[str] = []
    for y in range(int(h)):
        row = []
        base = int(y) * int(w)
        for x in range(int(w)):
            v = int(tiles[base + int(x)])
            if target is None:
                row.append("#" if v != 0 else ".")
            else:
                row.append("#" if v == target else ".")
        lines.append("".join(row))
    return lines
