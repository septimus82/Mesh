from __future__ import annotations

from typing import Any, Literal

Anchor = Literal["tl", "center"]


def validate_brush(brush: Any) -> dict[str, Any]:
    if not isinstance(brush, dict):
        raise TypeError("brush must be an object")

    brush_id = brush.get("id")
    if not isinstance(brush_id, str) or not brush_id.strip():
        raise ValueError("brush.id must be a non-empty string")

    w = brush.get("w")
    h = brush.get("h")
    if not isinstance(w, int) or w <= 0:
        raise ValueError("brush.w must be a positive int")
    if not isinstance(h, int) or h <= 0:
        raise ValueError("brush.h must be a positive int")

    mask_tile = brush.get("mask_tile", -1)
    if not isinstance(mask_tile, int):
        raise ValueError("brush.mask_tile must be an int when provided")

    tiles = brush.get("tiles")
    if not isinstance(tiles, list):
        raise ValueError("brush.tiles must be an array")
    if len(tiles) != h:
        raise ValueError(f"brush.tiles must have {h} rows, got {len(tiles)}")

    normalized_rows: list[list[int]] = []
    for row_idx, row in enumerate(tiles):
        if not isinstance(row, list):
            raise ValueError(f"brush.tiles[{row_idx}] must be an array")
        if len(row) != w:
            raise ValueError(f"brush.tiles[{row_idx}] must have {w} cols, got {len(row)}")
        normalized_row: list[int] = []
        for col_idx, value in enumerate(row):
            if not isinstance(value, int):
                raise ValueError(f"brush.tiles[{row_idx}][{col_idx}] must be an int")
            normalized_row.append(int(value))
        normalized_rows.append(normalized_row)

    return {
        "id": brush_id.strip(),
        "w": int(w),
        "h": int(h),
        "mask_tile": int(mask_tile),
        "tiles": normalized_rows,
    }


def apply_brush(
    tiles: list[int],
    *,
    width: int,
    height: int,
    x: int,
    y: int,
    brush: dict[str, Any],
    anchor: Anchor = "tl",
    clip: bool = False,
) -> list[int]:
    w = int(width)
    h = int(height)
    if w <= 0 or h <= 0:
        raise ValueError("width/height must be > 0")
    expected_len = w * h
    if len(tiles) != expected_len:
        raise ValueError(f"tiles expected {expected_len} entries, got {len(tiles)}")

    normalized = validate_brush(brush)
    bw = int(normalized["w"])
    bh = int(normalized["h"])
    mask_tile = int(normalized["mask_tile"])
    brush_tiles: list[list[int]] = normalized["tiles"]

    anchor_value = str(anchor or "").strip().lower()
    if anchor_value not in {"tl", "center"}:
        raise ValueError("anchor must be 'tl' or 'center'")

    origin_x = int(x)
    origin_y = int(y)
    if anchor_value == "center":
        origin_x = int(x) - (bw // 2)
        origin_y = int(y) - (bh // 2)

    out = list(tiles)

    for row in range(bh):
        for col in range(bw):
            value = int(brush_tiles[row][col])
            if value == mask_tile:
                continue
            tx = origin_x + col
            ty = origin_y + row
            if tx < 0 or ty < 0 or tx >= w or ty >= h:
                if clip:
                    continue
                raise IndexError(f"brush write out of bounds at ({tx}, {ty}) in {w}x{h}")
            idx = ty * w + tx
            out[idx] = value

    return out
