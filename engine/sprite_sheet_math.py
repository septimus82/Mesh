from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SpriteSheetSliceSpec:
    sheet_width: int
    sheet_height: int
    frame_width: int
    frame_height: int
    margin: int = 0
    spacing: int = 0
    columns: int | None = None
    rows: int | None = None


def iter_sprite_sheet_frame_boxes(spec: SpriteSheetSliceSpec) -> list[tuple[int, int, int, int]]:
    """Return PIL-style crop boxes (left, top, right, bottom) for each frame.

    Index order matches `engine.animation.SpriteSheetCache._slice_frames`: row-major with row 0
    starting at the bottom of the sheet (so frame 0 is bottom-left).
    """
    width = int(spec.sheet_width)
    height = int(spec.sheet_height)
    frame_w = int(spec.frame_width)
    frame_h = int(spec.frame_height)
    margin = max(0, int(spec.margin))
    spacing = max(0, int(spec.spacing))

    if width <= 0 or height <= 0 or frame_w <= 0 or frame_h <= 0:
        return []

    max_x = width - margin
    max_y = height - margin
    if max_x <= margin or max_y <= margin:
        return []

    boxes: list[tuple[int, int, int, int]] = []
    max_cols = int(spec.columns) if isinstance(spec.columns, int) and spec.columns > 0 else None
    max_rows = int(spec.rows) if isinstance(spec.rows, int) and spec.rows > 0 else None

    row = 0
    y = margin
    while (max_rows is None or row < max_rows) and (y + frame_h) <= max_y:
        col = 0
        x = margin
        while (max_cols is None or col < max_cols) and (x + frame_w) <= max_x:
            top = height - (y + frame_h)
            boxes.append((int(x), int(top), int(x + frame_w), int(top + frame_h)))
            x += frame_w + spacing
            col += 1
        y += frame_h + spacing
        row += 1
        if row > 10_000:
            break
    return boxes


def frame_index_to_box(spec: SpriteSheetSliceSpec, index: int) -> tuple[int, int, int, int] | None:
    if not isinstance(index, int):
        try:
            index = int(index)
        except (TypeError, ValueError):
            return None
    boxes = iter_sprite_sheet_frame_boxes(spec)
    if index < 0 or index >= len(boxes):
        return None
    return boxes[index]


def parse_anim_spec(value: Any) -> tuple[str, int, int, float] | None:
    """Parse `name:start-end:fps`."""
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) != 3:
        return None
    name = parts[0].strip()
    if not name:
        return None
    range_part = parts[1].strip()
    fps_part = parts[2].strip()
    if "-" not in range_part:
        return None
    a, b = range_part.split("-", 1)
    try:
        start = int(a)
        end = int(b)
        fps = float(fps_part)
    except (TypeError, ValueError):
        return None
    return name, start, end, fps
