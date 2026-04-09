"""Side-effect-free argument preview for structured command-palette commands."""
from __future__ import annotations

from typing import Any

from engine import command_palette_registry_defs as _defs


_PARSER_BY_COMMAND_ID: dict[str, str] = {
    "selection.align": "_parse_align_args",
    "selection.distribute": "_parse_distribute_args",
    "selection.snap_to_grid": "_parse_snap_args",
    "selection.nudge": "_parse_nudge_args",
    "selection.rotate": "_parse_rotate_args",
    "planes.toggle_repeat": "_parse_planes_toggle_repeat_args",
    "planes.select": "_parse_planes_select_args",
    "planes.move_to": "_parse_planes_move_to_args",
}

_SUGGESTIONS_BY_COMMAND_ID: dict[str, tuple[str, ...]] = {
    "selection.align": (
        *tuple(_defs._ALIGN_SIMPLE_MAP.keys()),
        "axis=x|mode=left|reference=primary",
        "axis=x|mode=center|reference=primary",
        "axis=x|mode=right|reference=primary",
        "axis=y|mode=top|reference=primary",
        "axis=y|mode=middle|reference=primary",
        "axis=y|mode=bottom|reference=primary",
    ),
    "selection.distribute": (
        *tuple(_defs._DISTRIBUTE_SIMPLE_MAP.keys()),
        "axis=x|mode=gap|reference=group",
        "axis=x|mode=center|reference=group",
        "axis=y|mode=gap|reference=group",
        "axis=y|mode=center|reference=group",
    ),
    "selection.snap_to_grid": (
        *tuple(_defs._SNAP_SIMPLE_MAP.keys()),
        "16",
        "32",
        "step=16|axes=xy|mode=nearest",
        "step=16|axes=xy|mode=floor",
        "step=16|axes=xy|mode=ceil",
        "step=16|axes=x|mode=nearest",
        "step=16|axes=y|mode=nearest",
    ),
    "selection.nudge": (
        *tuple(_defs._NUDGE_DIR_MAP.keys()),
        "left x3",
        "right x3 step=16",
        "dx=1|dy=0|count=1|step=16",
        "dx=0|dy=1|count=1|step=16",
    ),
    "selection.rotate": (
        *tuple(_defs._ROTATE_SIMPLE_MAP.keys()),
        "deg=90|about=self",
        "deg=90|about=group",
        "deg=180|about=primary",
    ),
    "planes.move_up": ("up", "down"),
    "planes.move_down": ("up", "down"),
    "planes.move_to": ("top", "bottom", "last", "0", "1", "2", "index=0", "index=1", "index=2"),
    "planes.toggle_repeat": ("x", "y", "both", "axis=x", "axis=y", "axis=both"),
    "planes.toggle_repeat_x": ("x", "y", "both"),
    "planes.toggle_repeat_y": ("x", "y", "both"),
    "planes.select": ("prev", "next", "mode=prev", "mode=next", "plane_id=plane_001"),
    "planes.select_prev": ("prev", "next"),
    "planes.select_next": ("prev", "next"),
}


def _format_float(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return format(number, "g")


def _format_parse_error(result: dict[str, Any]) -> str:
    reason = str(result.get("reason") or "invalid_arg").strip() or "invalid_arg"
    token = result.get("token")
    value = result.get("value")
    if isinstance(token, str) and token.strip():
        return f"{reason}: {token.strip()}"
    if isinstance(value, str) and value.strip():
        return f"{reason}: {value.strip()}"
    return reason


def _build_preview_text(command_id: str, result: dict[str, Any]) -> str | None:
    if command_id in ("selection.align", "selection.distribute"):
        axis = str(result.get("axis") or "").strip()
        mode = str(result.get("mode") or "").strip()
        reference = str(result.get("reference") or "").strip()
        if axis and mode:
            ref_value = reference or ("primary" if command_id == "selection.align" else "group")
            return f"axis={axis}|mode={mode}|reference={ref_value}"
        return None
    if command_id == "selection.snap_to_grid":
        step = result.get("step")
        axes = str(result.get("axes") or "").strip()
        mode = str(result.get("mode") or "").strip()
        if step is None or not axes or not mode:
            return None
        return f"step={int(step)}|axes={axes}|mode={mode}"
    if command_id == "selection.nudge":
        dx = _format_float(result.get("dx"))
        dy = _format_float(result.get("dy"))
        count = int(result.get("count") or 0)
        step = result.get("step")
        if step is None:
            return f"dx={dx}|dy={dy}|count={count}"
        return f"dx={dx}|dy={dy}|count={count}|step={_format_float(step)}"
    if command_id == "selection.rotate":
        deg = _format_float(result.get("deg"))
        about = str(result.get("about") or "").strip() or "self"
        return f"deg={deg}|about={about}"
    if command_id == "planes.toggle_repeat":
        axes_value = result.get("axes")
        if isinstance(axes_value, tuple) and axes_value:
            return f"toggle repeat: {'+'.join(str(v) for v in axes_value)}"
        return None
    if command_id == "planes.select":
        mode = str(result.get("mode") or "").strip().lower()
        if mode in ("prev", "next"):
            return f"select plane: {mode}"
        plane_id = str(result.get("plane_id") or "").strip()
        if plane_id:
            return f"select plane: {plane_id}"
        return None
    if command_id == "planes.move_to":
        mode = str(result.get("mode") or "").strip().lower()
        if mode in ("top", "bottom", "last"):
            return f"move plane: {mode}"
        if mode == "index":
            index_raw = result.get("index")
            if isinstance(index_raw, int):
                return f"move plane: {index_raw}"
        return None
    return None


def build_arg_preview(command_id: str, raw_arg: str) -> dict[str, Any]:
    """Build a deterministic parse preview for a structured command argument.

    Unknown command IDs return an inert success payload with no preview.
    """
    parser_name = _PARSER_BY_COMMAND_ID.get(str(command_id or "").strip())
    if not parser_name:
        return {"ok": True, "preview": None, "error": None}

    try:
        from engine import command_palette_registry as registry  # noqa: PLC0415

        parser = getattr(registry, parser_name, None)
        if not callable(parser):
            return {"ok": False, "preview": None, "error": f"missing_parser:{parser_name}"}
        parsed = parser(raw_arg)
    except Exception as exc:  # noqa: BLE001  # REASON: preview parser failures should degrade to a stable error payload without breaking palette rendering
        return {"ok": False, "preview": None, "error": f"preview_exception:{type(exc).__name__}"}

    if not isinstance(parsed, dict):
        return {"ok": False, "preview": None, "error": "invalid_parse_result"}
    if not bool(parsed.get("ok")):
        return {"ok": False, "preview": None, "error": _format_parse_error(parsed)}

    preview = _build_preview_text(str(command_id), parsed)
    return {"ok": True, "preview": preview, "error": None}


def _with_contextual_plane_move_to_candidates(
    *,
    candidates: tuple[str, ...],
    context: dict[str, Any] | None,
) -> tuple[str, ...]:
    if not isinstance(context, dict):
        return candidates

    plane_count: int | None = None
    count_value = context.get("plane_count")
    if isinstance(count_value, int):
        plane_count = max(0, int(count_value))
    elif isinstance(count_value, str):
        text = count_value.strip()
        if text:
            try:
                plane_count = max(0, int(text))
            except ValueError:
                plane_count = None

    if plane_count is None:
        plane_ids = context.get("plane_ids")
        if isinstance(plane_ids, (list, tuple)):
            plane_count = len([value for value in plane_ids if isinstance(value, str) and value.strip()])

    if plane_count is None or plane_count <= 0:
        return candidates

    max_index = min(int(plane_count) - 1, 9)
    if max_index < 0:
        return candidates

    merged = list(candidates)
    for index in range(max_index + 1):
        value = f"index={index}"
        if value not in merged:
            merged.append(value)
    return tuple(merged)


def build_arg_suggestions(command_id: str, raw_arg: str, context: dict[str, Any] | None = None) -> list[str]:
    """Return deterministic side-effect-free suggestions for structured args."""
    command_key = str(command_id or "").strip()
    candidates = _SUGGESTIONS_BY_COMMAND_ID.get(command_key)
    if not candidates:
        return []
    if command_key == "planes.move_to":
        candidates = _with_contextual_plane_move_to_candidates(candidates=candidates, context=context)

    query = str(raw_arg or "").strip().lower()
    if not query:
        return list(candidates)

    starts_with: list[str] = []
    contains: list[str] = []
    for candidate in candidates:
        low = candidate.lower()
        if low.startswith(query):
            starts_with.append(candidate)
        elif query in low:
            contains.append(candidate)
    return starts_with + contains
